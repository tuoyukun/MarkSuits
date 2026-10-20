"""Test helpers: make the plugin's `lib/` importable and build fake projects."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "mark"
sys.path.insert(0, str(PLUGIN_ROOT / "lib"))

MINIMAL_CONFIG = 'mark_schema = 1\nlocale = "zh-CN"\n'


def make_project(config_text: str | None = MINIMAL_CONFIG) -> Path:
    """Create a temp directory; write `.mark/config.toml` unless config_text is None."""
    root = Path(tempfile.mkdtemp(prefix="mark-test-"))
    if config_text is not None:
        (root / ".mark").mkdir()
        (root / ".mark" / "config.toml").write_text(config_text, encoding="utf-8")
    return root
