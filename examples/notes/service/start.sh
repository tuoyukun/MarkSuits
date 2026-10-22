#!/usr/bin/env bash
# Start the service in the background on SERVICE_PORT (from .env; default 8000) and wait
# until it answers. stop.sh stops it.
set -euo pipefail
port=${SERVICE_PORT:-8000}
python3 server.py --port "$port" > .server.log 2>&1 &
echo $! > .server.pid
for _ in $(seq 50); do
  if curl -fs "http://127.0.0.1:$port/api/notes" > /dev/null; then
    echo "notes: http://127.0.0.1:$port/api/notes"
    exit 0
  fi
  sleep 0.1
done
echo "service did not answer on port $port; see service/.server.log" >&2
exit 1
