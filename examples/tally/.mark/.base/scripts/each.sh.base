#!/usr/bin/env bash
# Shipped by Mark (written by `mark init`, updated by /mark:upgrade). Do not edit: change
# the entry point in the module instead.
#
#   bash scripts/each.sh <entry> required|optional <module dir>...
#
# Runs <module>/<entry> from inside each module, with this checkout's .env exported (its
# ports among them). A module directory that does not exist yet is skipped. A module that
# exists without the entry fails when the entry is required and is skipped when it is optional.
set -euo pipefail
entry=$1 need=$2
shift 2
cd "$(dirname "$0")/.."
if [ -f .env ]; then set -a; . ./.env; set +a; fi
ran=0 seen=" "
for dir in "$@"; do
  case "$seen" in *" $dir "*) continue ;; esac
  seen="$seen$dir "
  if [ ! -d "$dir" ]; then
    echo "skip $dir/: not created yet"
    continue
  fi
  if [ ! -f "$dir/$entry" ]; then
    if [ "$need" = required ]; then
      echo "$dir/$entry is missing: every module provides one (see CLAUDE.md, Layout)" >&2
      exit 1
    fi
    echo "skip $dir/: no $entry"
    continue
  fi
  echo "== $dir/$entry"
  (cd "$dir" && bash "./$entry")
  ran=$((ran + 1))
done
if [ "$ran" -eq 0 ]; then echo "no module has $entry yet: nothing ran"; fi
