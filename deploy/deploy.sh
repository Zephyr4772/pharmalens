#!/bin/bash
# Ship the committed code (plus the built web UI) to the server and restart the container. Data is untouched.
# Usage (Git Bash, repo root): deploy/deploy.sh
set -euo pipefail
HOST=${PHARMALENS_HOST:-azureuser@srv1}   # over Tailscale: not limited by the home-IP firewall rule
KEY=${PHARMALENS_KEY:-~/.ssh/azure_srv}
TMP=${TMPDIR:-/d/pharmacopy/tmp}/deploy
mkdir -p "$TMP"
(cd web && npm run build >/dev/null)
git archive --format=tar --prefix=app/ HEAD -o "$TMP/app.tar"
tar -rf "$TMP/app.tar" --transform 's,^web,app/web,' web/dist
scp -q -i "$KEY" "$TMP/app.tar" "$HOST:/srv/pharmalens/app.tar"
ssh -i "$KEY" "$HOST" 'cd /srv/pharmalens && rm -rf app && tar -xf app.tar && rm app.tar && cp app/deploy/docker-compose.yml . \
  && docker compose up -d --build 2>&1 | tail -1 && sleep 25 && curl -s http://127.0.0.1:8010/api/v1/healthz'
echo
