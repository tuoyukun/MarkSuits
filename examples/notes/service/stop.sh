#!/usr/bin/env bash
# Stop the service start.sh started, if it is running.
set -euo pipefail
if [ -f .server.pid ]; then
  kill "$(cat .server.pid)" 2> /dev/null || true
  rm -f .server.pid
fi
