#!/usr/bin/env bash
# Start the server in the background on BACKEND_PORT (from .env; default 8000) and wait
# until it answers. It serves the frontend too. stop.sh stops it.
set -euo pipefail
port=${BACKEND_PORT:-8000}
python3 server.py --port "$port" > .server.log 2>&1 &
echo $! > .server.pid
for _ in $(seq 50); do
  if curl -fs "http://127.0.0.1:$port/api/todos" > /dev/null; then
    echo "todo: http://127.0.0.1:$port/"
    exit 0
  fi
  sleep 0.1
done
echo "server did not answer on port $port; see backend/.server.log" >&2
exit 1
