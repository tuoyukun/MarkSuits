"""Tell the human when a newer Mark is published.

Claude Code updates plugins from a third-party marketplace only when the user turns on
auto-update for it, so `mark status` and `mark next` look up the published version at most
once a day (cached in the plugin's data dir). Any failure is silent: no network, a private
repo, a non-GitHub host. `MARK_NO_UPDATE_CHECK=1` turns the check off.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from pathlib import Path

from .upgrade import _ver

CHECK_EVERY = 24 * 3600
_PLUGIN = Path(__file__).resolve().parents[2]
_GITHUB = re.compile(r"github\.com[/:]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$")


def _fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310 - fixed https URL
        return str(json.loads(resp.read())["version"])


def _repo(source: dict) -> str | None:
    if source.get("source") == "github":
        return source.get("repo")
    m = _GITHUB.search(str(source.get("url") or ""))
    return f"{m.group(1)}/{m.group(2)}" if m else None


def newer(plugin: Path = _PLUGIN, fetch=_fetch, now: float | None = None) -> tuple[str, str] | None:
    """(marketplace, published version) when it is newer than the installed `plugin`, else None."""
    if os.environ.get("MARK_NO_UPDATE_CHECK"):
        return None
    # An installed plugin lives at <plugins>/cache/<marketplace>/<name>/<version>.
    if plugin.parents[2].name != "cache":
        return None  # --plugin-dir or a local checkout: nothing to update
    plugins, market, name = plugin.parents[3], plugin.parents[1].name, plugin.parent.name
    try:
        installed = json.loads((plugin / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
        source = json.loads((plugins / "known_marketplaces.json").read_text(encoding="utf-8"))[market]["source"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    data = Path(os.environ.get("CLAUDE_PLUGIN_DATA") or plugins / "data" / f"{name}-{market}")
    cache = data / "update-check.json"
    now = time.time() if now is None else now
    try:
        seen = json.loads(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        seen = {}
    latest = str(seen.get("latest") or "")
    if "at" not in seen or now - float(seen["at"]) >= CHECK_EVERY:
        repo = _repo(source)
        latest = ""
        if repo:
            # shortcut: assumes this repo's layout (plugins/<name>/); read marketplace.json if forks differ
            try:
                latest = fetch(f"https://raw.githubusercontent.com/{repo}/HEAD/plugins/{name}/.claude-plugin/plugin.json")
            except Exception:  # noqa: BLE001 - offline or private: say nothing
                latest = ""
        try:
            data.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"at": now, "latest": latest}), encoding="utf-8")
        except OSError:
            pass
    return (market, latest) if latest and _ver(latest) > _ver(installed) else None


INSTALL = "claude plugin marketplace add tuoyukun/MarkSuits --scope user && claude plugin install mark@marksuits --scope user"


def installed_plugin(config_dir: Path | None = None) -> str | None:
    """Version of the Mark plugin Claude Code has installed for this user, or None."""
    base = config_dir or Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    try:
        data = json.loads((base / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
        entries = [e for k, v in data["plugins"].items() if k.startswith("mark@") for e in v]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    # project-scope installs exist only inside their project; the board's sessions need the user one
    user = [e for e in entries if isinstance(e, dict) and e.get("scope") == "user"] or [e for e in entries if isinstance(e, dict)]
    return str(user[0].get("version") or "") or None if user else None


def mismatch(mark: str | None = None, plugin: str | None = None) -> dict[str, str] | None:
    """The service board (Homebrew) and the Claude plugin its sessions load are installed apart:
    {mark, plugin, cmd} saying which to update when their versions differ, else None."""
    from .scaffold import version

    mark = mark or version()
    plugin = plugin if plugin is not None else installed_plugin()
    if not plugin:
        return {"mark": mark, "plugin": "", "cmd": INSTALL}
    if plugin == mark:
        return None
    cmd = "claude plugin update mark@marksuits" if _ver(plugin) < _ver(mark) else "brew upgrade marksuits"
    return {"mark": mark, "plugin": plugin, "cmd": cmd}
