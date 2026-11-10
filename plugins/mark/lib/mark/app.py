"""Mark.app (the macOS menu bar app) and the `mark` launcher, built from the installed plugin.

    ~/.local/bin/mark        macos/launcher.py: runs the plugin Claude Code installed for this user
    ~/Applications/Mark.app  macos/Mark.swift compiled with swiftc; it runs `mark board --serve`
                             and, once a day, `mark app update`, then rebuilds itself and restarts
                             the board when the plugin moved

The plugin is the only copy of Mark's code, so the app, the launcher and the board's Claude
sessions never run different versions. Nothing here writes under the plugin root.
"""
from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import runner
from .upgrade import _ver

PLUGIN = Path(__file__).resolve().parents[2]
BUNDLE_ID = "com.marksuits.mark"


def app_path() -> Path:
    return Path.home() / "Applications" / "Mark.app"


def launcher_path() -> Path:
    return Path.home() / ".local" / "bin" / "mark"


def plugin_entry(config_dir: Path | None = None) -> tuple[str, dict] | None:
    """("mark@<marketplace>", entry) Claude Code installed for this user (any scope if none is user)."""
    base = config_dir or Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    try:
        data = json.loads((base / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
        entries = [(k, e) for k, v in data["plugins"].items() if k.startswith("mark@") for e in v if isinstance(e, dict)]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    user = [x for x in entries if x[1].get("scope") == "user"] or entries
    return user[0] if user else None


def write_launcher(dest: Path | None = None, python: str = sys.executable) -> Path:
    """The launcher runs on this Python: Mark needs 3.11+, and a login item's `python3` may be older."""
    dest = dest or launcher_path()
    body = (PLUGIN / "macos" / "launcher.py").read_text(encoding="utf-8").split("\n", 1)[1]
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(f"#!{python}\n{body}", encoding="utf-8")
    tmp.chmod(0o755)
    tmp.replace(dest)
    return dest


def info_plist(version: str, launcher: Path, binary: Path) -> bytes:
    return plistlib.dumps({
        "CFBundleIdentifier": BUNDLE_ID, "CFBundleName": "Mark", "CFBundleExecutable": "Mark",
        "CFBundlePackageType": "APPL", "CFBundleShortVersionString": version, "LSUIElement": True,
        "CFBundleIconFile": "Mark", "LSMinimumSystemVersion": "13.0", "MarkCLI": str(launcher), "MarkApp": str(binary)})


def build_app(version: str, dest: Path | None = None, launcher: Path | None = None, run=subprocess.run) -> tuple[bool, str]:
    """Compile Mark.app next to `dest`, then swap it in: a failed build leaves the old app. (ok, error)."""
    dest = dest or app_path()
    swiftc = shutil.which("swiftc")
    if not swiftc:
        return False, "app.no_swiftc"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".mark-app-", dir=dest.parent) as tmp:
        new = Path(tmp) / "Mark.app"
        (new / "Contents" / "MacOS").mkdir(parents=True)
        res = run([swiftc, "-O", "-module-cache-path", str(Path(tmp) / "cache"), "-o",
                   str(new / "Contents" / "MacOS" / "Mark"), str(PLUGIN / "macos" / "Mark.swift")],
                  capture_output=True, text=True)
        if res.returncode != 0:
            return False, (res.stderr or res.stdout or "swiftc failed").strip()[-2000:]
        build_icon(new / "Contents", Path(tmp) / "Mark.iconset", run)
        (new / "Contents" / "Info.plist").write_bytes(
            info_plist(version, launcher or launcher_path(), dest / "Contents" / "MacOS" / "Mark"))
        old = Path(tmp) / "old.app"
        if dest.exists():
            dest.rename(old)
        new.rename(dest)
    return True, ""


def build_icon(contents: Path, iconset: Path, run=subprocess.run) -> bool:
    """Draw the app icon with the just-built binary (`Mark --iconset`) and pack it with iconutil.
    Best effort: an app without an icon still runs."""
    (contents / "Resources").mkdir(exist_ok=True)
    try:
        return (run([str(contents / "MacOS" / "Mark"), "--iconset", str(iconset)], capture_output=True).returncode == 0
                and run(["iconutil", "-c", "icns", "-o", str(contents / "Resources" / "Mark.icns"), str(iconset)],
                        capture_output=True).returncode == 0)
    except OSError:
        return False


def update(run=subprocess.run) -> tuple[str, dict]:
    """Pull the marketplace and update the plugin: (i18n key, params). Claude Code updates a
    third-party plugin only with auto-update turned on, so the app asks once a day."""
    if os.environ.get("MARK_NO_UPDATE_CHECK"):
        return "app.update_off", {}
    claude, found = runner.find_claude(), plugin_entry()
    if not claude:
        return "app.no_claude", {}
    if not found:
        return "app.no_plugin", {}
    name, entry = found
    old = str(entry.get("version") or "")
    for cmd in (["plugin", "marketplace", "update", name.split("@", 1)[1]],
                ["plugin", "update", name, "--scope", str(entry.get("scope") or "user")]):
        res = run([claude, *cmd], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=300)
        if res.returncode != 0:
            return "app.update_failed", {"error": (res.stderr or res.stdout).strip()[-500:]}
    new = str((plugin_entry() or (name, {}))[1].get("version") or old)
    return ("app.updated" if _ver(new) > _ver(old) else "app.current"), {"old": old, "new": new}
