#!/usr/bin/env bash
# Shipped by Mark. White-box self-tests: each module's own lint, type check, unit tests and
# build, from its selftest.sh. `[merge] regression` runs this before regression.sh.
exec bash "$(dirname "$0")/each.sh" selftest.sh required "frontend" "backend"
