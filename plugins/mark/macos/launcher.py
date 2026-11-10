#!/usr/bin/env python3
"""`mark` outside Claude Code: runs the Mark plugin Claude Code has installed for this user, so the
menu bar app and a terminal always get the version the plugin updates to. `mark app install`
copies this file to ~/.local/bin/mark with its own Python in the first line."""
import json
import os
import sys
from pathlib import Path


def plugin_root(config_dir=None):
    """installPath of the user-scope Mark plugin (any scope if there is none), else None."""
    base = Path(config_dir or os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    try:
        data = json.loads((base / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
        entries = [e for k, v in data["plugins"].items() if k.startswith("mark@") for e in v if isinstance(e, dict)]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    user = [e for e in entries if e.get("scope") == "user"] or entries
    path = user[0].get("installPath") if user else None
    return Path(path) if isinstance(path, str) and (Path(path) / "bin" / "mark").is_file() else None


def main():
    root = plugin_root()
    if root is None:
        sys.stderr.write("The Mark plugin is not installed for this user. Run:\n"
                         "  claude plugin marketplace add tuoyukun/MarkSuits --scope user\n"
                         "  claude plugin install mark@marksuits --scope user\n")
        return 2
    os.execv(sys.executable, [sys.executable, str(root / "bin" / "mark"), *sys.argv[1:]])


if __name__ == "__main__":
    sys.exit(main())
