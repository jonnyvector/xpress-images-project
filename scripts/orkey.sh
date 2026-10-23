#!/usr/bin/env bash
# Copy the OpenRouter API key from a Fly app into .env (never printed).
# Usage: scripts/orkey.sh [fly-app-name]
set -euo pipefail
umask 077  # .env holds secrets: keep any file this script writes private

APP="${1:-xpress-visual-search}"
ENV_FILE="$(cd "$(dirname "$0")/.." && pwd)/.env"

# Fly never returns secret values from `secrets list`, only names, so find the name there...
NAME=$(fly secrets list -a "$APP" | awk 'toupper($1) ~ /OPENROUTER/ {print $1; exit}')
if [ -z "$NAME" ]; then
  echo "No OPENROUTER secret on app '$APP'. Secret names:" >&2
  fly secrets list -a "$APP" >&2
  exit 1
fi

# ...then read the value from inside a running machine.
# fly ssh can mix connection banners into stdout, so keep only the sk-or-... token.
VALUE=$(fly ssh console -a "$APP" -C "printenv $NAME" 2>/dev/null | grep -oE 'sk-or-[A-Za-z0-9_-]+' | head -1 || true)
if [ -z "$VALUE" ]; then
  echo "Found secret '$NAME' but got no sk-or-... key back (is a machine running?). .env left unchanged." >&2
  exit 1
fi

# Confirm OpenRouter accepts it before saving.
# Header via stdin so the key never appears in the process list.
if ! printf 'Authorization: Bearer %s\n' "$VALUE" | curl -sf -H @- https://openrouter.ai/api/v1/key >/dev/null; then
  echo "Key read from $APP was rejected by OpenRouter. .env left unchanged." >&2
  exit 1
fi

touch "$ENV_FILE"
grep -v '^OPENROUTER_API_KEY=' "$ENV_FILE" > "$ENV_FILE.tmp" || true
mv "$ENV_FILE.tmp" "$ENV_FILE"
echo "OPENROUTER_API_KEY=$VALUE" >> "$ENV_FILE"
echo "Saved $NAME from $APP to .env as OPENROUTER_API_KEY (${VALUE:0:8}...)"
