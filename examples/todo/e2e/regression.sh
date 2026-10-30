#!/usr/bin/env bash
# Black-box regression: the core-flow regression journeys in regression/. Playwright starts its own server on a
# per-checkout port (playwright.config.js).
set -euo pipefail
exec npx playwright test regression
