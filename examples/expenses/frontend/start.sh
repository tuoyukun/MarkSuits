#!/usr/bin/env bash
# Serve this directory as static files in the background on FRONTEND_PORT (from .env;
# default 8000) and wait until it answers. stop.sh stops it.
set -euo pipefail
port=${FRONTEND_PORT:-8000}
python3 -m http.server "$port" --bind 127.0.0.1 > .server.log 2>&1 &
echo $! > .server.pid
for _ in $(seq 50); do
  if curl -fs "http://127.0.0.1:$port/" > /dev/null; then
    echo "expenses: http://127.0.0.1:$port/"
    exit 0
  fi
  sleep 0.1
done
echo "server did not answer on port $port; see frontend/.server.log" >&2
exit 1
