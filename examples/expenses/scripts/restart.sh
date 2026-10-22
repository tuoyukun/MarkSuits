#!/usr/bin/env bash
# Shipped by Mark. stop.sh, then start.sh.
set -e
bash "$(dirname "$0")/stop.sh"
exec bash "$(dirname "$0")/start.sh"
