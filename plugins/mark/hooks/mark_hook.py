#!/usr/bin/env python3
"""Single entry point for every Mark hook: `mark_hook.py <group>`."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from mark.entry import main  # noqa: E402

main()
