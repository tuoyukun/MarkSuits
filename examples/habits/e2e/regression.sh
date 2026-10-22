#!/usr/bin/env bash
# Black-box regression on the iOS simulator (macOS). Under the device lock: start a backend
# whose date is pinned to TODAY and the app's dev server on ports of this checkout's own,
# open the app in Expo Go, run the Maestro flows, stop both.
#   bash regression.sh                 every flow
#   bash regression.sh add-habit.yaml  selected flows
set -euo pipefail
# shortcut: one simulator serves every worktree, so runs queue on a lock; give each port slot
# its own simulator (xcrun simctl clone) when the queue gets long.
if [ -z "${HABITS_DEVICE_LOCKED:-}" ]; then
  export HABITS_DEVICE_LOCKED=1
  exec lockf "${TMPDIR:-/tmp}/habits-simulator.lock" bash "$0" "$@"
fi
cd "$(dirname "$0")"
TODAY=${TODAY:-2026-03-02}
slot=$(( $(printf %s "$PWD" | cksum | cut -d' ' -f1) % 200 ))
bport=$((8400 + slot)) mport=$((8600 + slot))

if ! xcrun simctl list devices booted | grep -q Booted; then
  device=$(xcrun simctl list devices available | grep -m1 -E '^ +iPhone' | grep -oE '[0-9A-F-]{36}')
  xcrun simctl boot "$device"
  xcrun simctl bootstatus "$device" > /dev/null
fi
if ! xcrun simctl listapps booted | grep -q host.exp.Exponent; then
  echo "Expo Go is not installed on the booted simulator: run 'cd app && npx expo start --ios' once." >&2
  exit 1
fi

pids=()
cleanup() { for p in "${pids[@]}"; do pkill -P "$p" 2> /dev/null || true; kill "$p" 2> /dev/null || true; done; }
trap cleanup EXIT
HABITS_TODAY=$TODAY python3 ../backend/server.py --port "$bport" > .backend.log 2>&1 &
pids+=($!)
(cd ../app && EXPO_PUBLIC_API_BASE="http://127.0.0.1:$bport" CI=1 exec npx expo start --port "$mport") > .metro.log 2>&1 &
pids+=($!)
for _ in $(seq 240); do
  curl -fs "http://127.0.0.1:$bport/api/habits" > /dev/null \
    && curl -fs "http://127.0.0.1:$mport/status" | grep -q running && break
  sleep 0.5
done
if [ $# -eq 0 ]; then set -- *.yaml; fi
maestro test -e METRO_PORT="$mport" "$@"
