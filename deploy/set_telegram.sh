#!/bin/bash
# Connect a Telegram bot to the server: stores the token in the server's private .env, finds your chat id
# (send the bot any message first), enables health alerts to that chat, restarts, and sends a test message.
# Usage (Git Bash, repo root): bash deploy/set_telegram.sh <bot-token>
set -euo pipefail
TOKEN=${1:?usage: bash deploy/set_telegram.sh <bot-token>}
HOST=${PHARMALENS_HOST:-azureuser@srv1}
KEY=${PHARMALENS_KEY:-~/.ssh/azure_srv}

CHAT=$(curl -s "https://api.telegram.org/bot${TOKEN}/getUpdates" | py -3 -c "
import json, sys
d = json.load(sys.stdin)
ids = [str((u.get('message') or {}).get('chat', {}).get('id')) for u in d.get('result', []) if (u.get('message') or {}).get('chat')]
print(ids[-1] if ids else '')")
if [ -z "$CHAT" ]; then echo "No chat found: send your bot any message in Telegram (e.g. 'hi'), then run this again."; exit 1; fi
echo "chat id: $CHAT"

ssh -i "$KEY" "$HOST" "cd /srv/pharmalens && grep -v -e '^TELEGRAM_BOT_TOKEN=' -e '^HEALTH_TELEGRAM_CHAT=' .env > .env.new \
  && printf 'TELEGRAM_BOT_TOKEN=%s\nHEALTH_TELEGRAM_CHAT=%s\n' '$TOKEN' '$CHAT' >> .env.new && mv .env.new .env && chmod 600 .env \
  && docker compose up -d --force-recreate >/dev/null 2>&1 && sleep 25 && curl -s http://127.0.0.1:8010/api/v1/healthz"
echo
curl -s -X POST "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$CHAT" \
  -d text="PharmaLens is connected. Health alerts will arrive here." >/dev/null && echo "test message sent"
curl -s -m 120 -X POST https://srv1.tailf3b6bc.ts.net/api/v1/admin/connectors/health_watch/run; echo
