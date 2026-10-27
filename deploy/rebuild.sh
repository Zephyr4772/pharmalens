#!/bin/bash
# Catalog rebuild cycle: the server's live database comes down, build_core runs on the laptop (needs the 1.3 GB
# source datasets in data/sources), and the result goes back. The server is stopped throughout so no write is lost;
# the previous server database is kept as data/pharmalens.duckdb.pre-rebuild for rollback.
# Usage (Git Bash, repo root): deploy/rebuild.sh
set -euo pipefail
HOST=${PHARMALENS_HOST:-azureuser@srv1}
KEY=${PHARMALENS_KEY:-~/.ssh/azure_srv}
export TEMP='D:\pharmacopy\tmp' TMP='D:\pharmacopy\tmp' PYTHONIOENCODING=utf-8
cfree() { powershell -NoProfile -c "[math]::Round((Get-PSDrive C).Free/1GB,1)"; }
[ "$(cfree | cut -d. -f1)" -ge 5 ] || { echo "C: has under 5 GB free; not starting"; exit 1; }

echo "== stopping server and fetching its database"
# "[b]ackfill" keeps pkill from matching this very command line; the one-off container folds the WAL into the file
ssh -i "$KEY" "$HOST" 'pkill -f "[b]ackfill.sh" || true; cd /srv/pharmalens && docker compose stop >/dev/null 2>&1 \
  && docker run --rm -v /srv/pharmalens/data:/app/data pharmalens:latest python -c "import duckdb; c = duckdb.connect(\"/app/data/pharmalens.duckdb\"); c.execute(\"CHECKPOINT\"); c.close()" \
  && sudo chown azureuser: data/pharmalens.duckdb* && cp data/pharmalens.duckdb data/pharmalens.duckdb.pre-rebuild && gzip -1 -c data/pharmalens.duckdb > /tmp/db.gz'
ssh -i "$KEY" "$HOST" 'ls -la /srv/pharmalens/data/ | grep duckdb'
cp data/pharmalens.duckdb "data/pharmalens.duckdb.local-$(date +%Y%m%d%H%M)" 2>/dev/null || true
scp -q -i "$KEY" "$HOST:/tmp/db.gz" data/db.gz && gunzip -f -c data/db.gz > data/pharmalens.duckdb && rm data/db.gz

echo "== building (C: free $(cfree) GB)"
( cd backend && py -3 -u -W ignore -m pharmalens.pipeline.build_core ) > data/rebuild.log 2>&1 &
pid=$!
while kill -0 $pid 2>/dev/null; do
  if [ "$(cfree | cut -d. -f1)" -lt 3 ]; then
    echo "C: below 3 GB, aborting build; restarting server on its old database"; kill $pid
    ssh -i "$KEY" "$HOST" 'cd /srv/pharmalens && docker compose start >/dev/null 2>&1'; exit 1
  fi
  sleep 15
done
wait $pid || { echo "build failed (see data/rebuild.log); restarting server on its old database"; ssh -i "$KEY" "$HOST" 'cd /srv/pharmalens && docker compose start >/dev/null 2>&1'; exit 1; }
grep -E "molecules:|spacing|live references|build_seconds" data/rebuild.log
( cd backend && py -3 -W ignore -c "from pharmalens import derived, db; derived.migrate(); derived.refresh_derived(); db.get_conn().execute('CHECKPOINT'); db.close()" )

echo "== uploading and restarting"
gzip -1 -c data/pharmalens.duckdb > data/db.gz
scp -q -i "$KEY" data/db.gz "$HOST:/tmp/db.gz" && rm data/db.gz
ssh -i "$KEY" "$HOST" 'cd /srv/pharmalens && gunzip -c /tmp/db.gz > data/pharmalens.duckdb && rm /tmp/db.gz && rm -f data/pharmalens.duckdb.wal \
  && docker compose start >/dev/null 2>&1 && sleep 25 && curl -s http://127.0.0.1:8010/api/v1/healthz'
echo
