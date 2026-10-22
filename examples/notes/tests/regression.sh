#!/usr/bin/env bash
# Black-box regression: start the service on a free per-checkout port, run every
# end-to-end test against it over HTTP, stop it. Override the port with PORT=<n>.
set -euo pipefail
port=${PORT:-$((8100 + $(printf %s "$PWD" | cksum | cut -d' ' -f1) % 800))}
python3 ../service/server.py --port "$port" > .server.log 2>&1 &
pid=$!
trap 'kill $pid 2> /dev/null || true' EXIT
for _ in $(seq 50); do
  curl -fs "http://127.0.0.1:$port/api/notes" > /dev/null && break
  sleep 0.1
done
NOTES_URL="http://127.0.0.1:$port" python3 -m unittest discover -s e2e -t . "$@"
