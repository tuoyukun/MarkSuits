#!/usr/bin/env bash
# Frontend self-test: syntax check of every JS module, then the unit tests (src/*.test.js).
set -euo pipefail
find src -name '*.js' -print0 | xargs -0 -n1 node --check
node --test src/*.test.js
