#!/usr/bin/env bash
# Stop the dev server start.sh started, if it is running.
set -euo pipefail
if [ -f .metro.pid ]; then
  pkill -P "$(cat .metro.pid)" 2> /dev/null || true
  kill "$(cat .metro.pid)" 2> /dev/null || true
  rm -f .metro.pid
fi
