#!/usr/bin/env bash
# Start the dev server (Metro) in the background on METRO_PORT (from .env; default 8100),
# with the app pointed at the backend on BACKEND_PORT, and wait until it answers. The app
# then opens in Expo Go: exp://127.0.0.1:$METRO_PORT. stop.sh stops it.
set -euo pipefail
port=${METRO_PORT:-8100}
export EXPO_PUBLIC_API_BASE="http://127.0.0.1:${BACKEND_PORT:-8300}"
CI=1 npx expo start --port "$port" > .metro.log 2>&1 &
echo $! > .metro.pid
for _ in $(seq 120); do
  if curl -fs "http://127.0.0.1:$port/status" | grep -q running; then
    echo "app: exp://127.0.0.1:$port (backend $EXPO_PUBLIC_API_BASE)"
    exit 0
  fi
  sleep 0.5
done
echo "Metro did not answer on port $port; see app/.metro.log" >&2
exit 1
