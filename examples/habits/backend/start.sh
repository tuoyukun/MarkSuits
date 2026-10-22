#!/usr/bin/env bash
# Start the backend in the background on BACKEND_PORT (from .env; default 8300) and wait
# until it answers. stop.sh stops it.
set -euo pipefail
port=${BACKEND_PORT:-8300}
python3 server.py --port "$port" > .server.log 2>&1 &
echo $! > .server.pid
for _ in $(seq 50); do
  if curl -fs "http://127.0.0.1:$port/api/habits" > /dev/null; then
    echo "habits backend: http://127.0.0.1:$port/api/habits"
    exit 0
  fi
  sleep 0.1
done
echo "backend did not answer on port $port; see backend/.server.log" >&2
exit 1
