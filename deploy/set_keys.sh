#!/bin/bash
# Put AI, Hugging Face and FDA Data Dashboard keys into the server's private .env and restart.
# Reads a keys file with lines like:  gemini:"..."  grok:"..."  hugginface:"..."  fdauser:"you@mail"  fdakey:"..."
# (fdauser = the e-mail registered with FDA's OII Unified Logon; fdakey = the Authorization Key FDA mailed you)
# Usage (Git Bash, repo root): bash deploy/set_keys.sh /c/Users/sinha/Downloads/keys.txt
set -euo pipefail
FILE=${1:?usage: bash deploy/set_keys.sh <keys.txt>}
HOST=${PHARMALENS_HOST:-azureuser@srv1}
KEY=${PHARMALENS_KEY:-~/.ssh/azure_srv}
get() { sed -n "s/^$1:\s*\"\(.*\)\"\s*$/\1/p" "$FILE" | tr -d '\r'; }   # spaces after the colon are fine
GEMINI=$(get gemini); GROQ=$(get grok); HF=$(get hugginface); FDAU=$(get fdauser); FDAK=$(get fdakey)
[ -n "$GEMINI$GROQ" ] || { echo "no gemini/grok key found in $FILE"; exit 1; }
ssh -i "$KEY" "$HOST" "cd /srv/pharmalens && grep -v -e '^GEMINI_API_KEY=' -e '^GROQ_API_KEY=' -e '^HF_TOKEN=' -e '^FDA_DD_USER=' -e '^FDA_DD_KEY=' .env > .env.new \
  && printf 'GEMINI_API_KEY=%s\nGROQ_API_KEY=%s\nHF_TOKEN=%s\nFDA_DD_USER=%s\nFDA_DD_KEY=%s\n' '$GEMINI' '$GROQ' '$HF' '$FDAU' '$FDAK' >> .env.new && mv .env.new .env && chmod 600 .env \
  && docker compose up -d --force-recreate >/dev/null 2>&1 && sleep 25 && curl -s http://127.0.0.1:8010/api/v1/healthz && echo && docker logs pharmalens 2>&1 | grep -i 'drugden bot' | tail -1"
echo "keys stored; message your bot to try it"
