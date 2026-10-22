#!/usr/bin/env bash
# App self-test: the unit tests of the plain JS modules (src/*.test.js). Components are
# checked on the simulator by design QA and the end-to-end flows.
set -euo pipefail
node --test src/*.test.js
