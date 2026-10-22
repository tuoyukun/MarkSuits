#!/usr/bin/env bash
# Black-box regression: every end-to-end spec. Playwright serves the app itself on a
# per-checkout port (playwright.config.js).
set -euo pipefail
exec npx playwright test
