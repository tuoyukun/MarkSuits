#!/usr/bin/env bash
# Start the dev server (Metro) in the background on METRO_PORT (from .env; default 8100) and
# wait until it answers. The app then opens in Expo Go: exp://127.0.0.1:$METRO_PORT.
# stop.sh stops it.
set -euo pipefail
port=${METRO_PORT:-8100}
# Not CI=1: that turns off file watching, so the app would keep an old bundle after edits.
env -u CI npx expo start --port "$port" < /dev/null > .metro.log 2>&1 &
echo $! > .metro.pid
for _ in $(seq 120); do
  if curl -fs "http://127.0.0.1:$port/status" | grep -q running; then
    echo "app: exp://127.0.0.1:$port"
    exit 0
  fi
  sleep 0.5
done
echo "Metro did not answer on port $port; see app/.metro.log" >&2
exit 1
