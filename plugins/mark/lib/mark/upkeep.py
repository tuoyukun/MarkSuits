"""The board keeps Mark current.

It asks hourly whether a newer plugin is published (`updates.py`); the page shows it on the logo.
On the human's click it updates the plugin (`app.update`), rebuilds the menu bar app when there is
one, and restarts the board on the new code (`board.serve` re-executes itself). Once per plugin
version, the board then opens an upgrade lane (`upgrade.run`) in each registered project whose
template files that version changes; the human merges or drops it on the project's board.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

from . import app, general, home, scaffold, updates, upgrade
from .config import ConfigError, MarkConfig, load_config
from .flow import FlowError
from .i18n import t

CHECK_SECONDS = 3600
LANES_FILE = "upgrade-lanes.json"  # MARK_HOME: {project id: plugin version it got its lane for}
SUBJECT = "chore: upgrade Mark "   # upgrade.run's commit message


class Updater:
    """The plugin update the board offers: what is published, and the click's progress."""

    def __init__(self, touch):
        self.touch = touch  # tell every open page to reload
        self.latest, self.state, self.error = "", "", ""
        self.restart: Path | None = None  # set when the board should re-execute this `bin/mark`
        self.lock = threading.Lock()

    def view(self) -> dict[str, str]:
        return {"current": scaffold.version(), "latest": self.latest, "state": self.state, "error": self.error}

    def poll(self, stop: threading.Event, check=updates.newer) -> None:
        while True:
            found = check(every=CHECK_SECONDS)
            latest = found[1] if found else ""
            if latest != self.latest:
                self.latest = latest
                self.touch()
            if stop.wait(CHECK_SECONDS):
                return

    def start(self, busy: bool, shutdown, run=None) -> tuple[bool, str]:
        """Update in the background, then call `shutdown` so the board restarts. (started, why not)."""
        with self.lock:
            if self.state == "running":
                return False, "update.running"
            if busy:
                return False, "update.busy"
            self.state, self.error = "running", ""
        threading.Thread(target=run or self.run, args=(shutdown,), daemon=True).start()
        self.touch()
        return True, ""

    def run(self, shutdown, update=app.update, run=subprocess.run) -> None:
        key, params = update()
        target = newer_install()  # "current" too: the menu bar app may have updated the plugin already
        if not target:
            self.state, self.error = "failed", t("en", key, **params)
            self.touch()
            return
        if sys.platform == "darwin" and app.app_path().exists():
            run([sys.executable, str(target), "app", "install", "--no-open"],
                capture_output=True, stdin=subprocess.DEVNULL, timeout=600)
        self.restart = target
        shutdown()


def newer_install() -> Path | None:
    """`bin/mark` of the installed plugin when it is newer than the code running here, else None."""
    entry = app.plugin_entry()
    if not entry:
        return None
    target = Path(str(entry[1].get("installPath") or "")) / "bin" / "mark"
    newer = upgrade._ver(str(entry[1].get("version") or "")) > upgrade._ver(scaffold.version())
    return target if newer and target.is_file() else None


def is_upgrade(lane: dict) -> bool:
    return bool(lane.get("upgrade"))  # set by board.general_lanes from the lane's first commit


def open_lanes(touch, lanes) -> None:
    """Once per plugin version, an upgrade lane in each registered project it would change.
    `lanes(cfg)`: the project's open general lanes (`board.general_lanes`)."""
    path, ver = home.root() / LANES_FILE, scaffold.version()
    try:
        done = json.loads(path.read_text(encoding="utf-8"))
        done = done if isinstance(done, dict) else {}
    except (OSError, ValueError):
        done = {}
    for reg in home.projects():
        if done.get(reg["id"]) == ver:
            continue
        # once per version even when it fails: `mark status` still says the project is behind
        done[reg["id"]] = ver
        root = Path(reg["root"])
        try:
            if upgrade.stale(root):
                cfg = load_config(root)
                # shortcut: an older upgrade lane still open blocks a new one; merge or drop it first
                if not any(is_upgrade(x) for x in lanes(cfg)):
                    upgrade.run(cfg)
                    touch()
        except (FlowError, ConfigError, OSError):
            pass
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(done) + "\n", encoding="utf-8")
    except OSError:
        pass


_jobs: dict[tuple[str, str], dict[str, str]] = {}  # (project root, branch) -> {state, error}
_jobs_lock = threading.Lock()


def job(cfg: MarkConfig, branch: str) -> dict[str, str] | None:
    return _jobs.get((str(cfg.root), branch))


def busy() -> bool:
    return any(j["state"] == "running" for j in _jobs.values())


def lane_action(cfg: MarkConfig, req: dict, lanes, touch, merge=general.merge_lane) -> tuple[bool, str]:
    """Merge (in the background: it runs the regression) or drop an open upgrade lane."""
    branch, verb = req.get("branch"), req.get("verb")
    if verb not in ("merge", "drop") or not any(x.get("branch") == branch and is_upgrade(x) for x in lanes(cfg)):
        return False, "bad request"
    key = (str(cfg.root), branch)
    with _jobs_lock:
        if key in _jobs and _jobs[key]["state"] == "running":
            return False, "lane.running"
        if verb == "drop":
            try:
                general.drop(cfg, branch, force=True)
            except FlowError as exc:
                return False, t(cfg.locale, exc.key, **exc.params)
            _jobs.pop(key, None)
            return True, ""
        _jobs[key] = {"state": "running", "error": ""}

    def work() -> None:
        try:
            merge(cfg, branch)
            with _jobs_lock:
                _jobs.pop(key, None)
        except FlowError as exc:
            with _jobs_lock:
                _jobs[key] = {"state": "failed", "error": t(cfg.locale, exc.key, **exc.params)}
        except Exception as exc:  # noqa: BLE001 - keep the page from showing "merging" forever
            with _jobs_lock:
                _jobs[key] = {"state": "failed", "error": str(exc)}
        touch()

    threading.Thread(target=work, daemon=True).start()
    touch()
    return True, ""
