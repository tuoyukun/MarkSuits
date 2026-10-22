#!/usr/bin/env bash
# Service self-test: compile every module, then the unit tests (test_*.py).
set -euo pipefail
python3 -m py_compile *.py
python3 -m unittest -q
