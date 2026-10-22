#!/usr/bin/env bash
# Frontend self-test: syntax check of every JS module (no build step, no unit tests yet).
set -euo pipefail
find src -name '*.js' -print0 | xargs -0 -n1 node --check
echo "frontend: syntax ok"
