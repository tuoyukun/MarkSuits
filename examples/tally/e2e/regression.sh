#!/usr/bin/env bash
# Black-box regression on the iOS simulator (macOS). Under the device lock: start the app's
# dev server on a port of this checkout's own, with a fresh storage key so the app starts
# with no counters, open it in Expo Go, run the Maestro flows, stop the server.
#   bash regression.sh                   every flow
#   bash regression.sh add-counter.yaml  selected flows
set -euo pipefail
# shortcut: one simulator serves every worktree, so runs queue on a lock; give each port slot
# its own simulator (xcrun simctl clone) when the queue gets long.
if [ -z "${TALLY_DEVICE_LOCKED:-}" ]; then
  export TALLY_DEVICE_LOCKED=1
  exec lockf "${TMPDIR:-/tmp}/tally-simulator.lock" bash "$0" "$@"
fi
cd "$(dirname "$0")"
slot=$(( $(printf %s "$PWD" | cksum | cut -d' ' -f1) % 200 ))
mport=$((8600 + slot))

if ! xcrun simctl list devices booted | grep -q Booted; then
  device=$(xcrun simctl list devices available | grep -m1 -E '^ +iPhone' | grep -oE '[0-9A-F-]{36}')
  xcrun simctl boot "$device"
  xcrun simctl bootstatus "$device" > /dev/null
fi
if ! xcrun simctl listapps booted | grep -q host.exp.Exponent; then
  echo "Expo Go is not installed on the booted simulator: run 'cd app && npx expo start --ios' once." >&2
  exit 1
fi

pid=
cleanup() { [ -z "$pid" ] || { pkill -P "$pid" 2> /dev/null || true; kill "$pid" 2> /dev/null || true; }; }
trap cleanup EXIT
(cd ../app && EXPO_PUBLIC_STORAGE_KEY="e2e-$(date +%s)-$slot" CI=1 exec npx expo start --port "$mport") > .metro.log 2>&1 &
pid=$!
for _ in $(seq 240); do
  curl -fs "http://127.0.0.1:$mport/status" | grep -q running && break
  sleep 0.5
done
if [ $# -eq 0 ]; then set -- *.yaml; fi
maestro test -e METRO_PORT="$mport" "$@"
