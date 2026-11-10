"""New-project wizard on the board's home page: `/mark:init`, talked through in the board chat.

The human gives a directory (a full path; made if missing, its parent must exist) and says what
they are building. The board runs the same headless chat turns as a ticket's (`chat.py`), in that
directory, the first one `/mark:init <their text>`: the skill proposes the answers and stops, the
human confirms or corrects in the next message, then it runs `mark init` and fills in CLAUDE.md.
Once `.mark/config.toml` is there the project is registered (`home.py`) and gets a board.

State, per wizard: `MARK_HOME/wizards/<wid>/wizard.json` {dir, started}, and the chat's own files
under `MARK_HOME/wizards/<wid>/locks/`. Discarding a wizard deletes only that; never the directory.
"""
from __future__ import annotations

import json
import secrets
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from . import chat, home

TICKET = "init"  # the chat's files are chat-init.*
NOTE = (
    "This is a headless session: you are talking with the human through the Mark web board's "
    "new-project wizard, not a terminal. They read your reply there and answer in their next "
    "message. AskUserQuestion does not exist here and there is no ticket yet, so `mark ask` does "
    "not work: ask everything, choices included, as plain text (a short numbered list works). "
    "When you need the human, end your turn."
)


@dataclass(frozen=True)
class Spot:
    """What `chat.py` reads from a MarkConfig, for a directory that is not a Mark project yet."""
    root: Path
    state_dir: Path
    board_permission_mode: str = "auto"


def base() -> Path:
    return home.root() / "wizards"


def _read(wid: object) -> dict | None:
    if not isinstance(wid, str) or not wid.isalnum():
        return None
    try:
        data = json.loads((base() / wid / "wizard.json").read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("dir"), str) else None


def spot(wid: str) -> Spot | None:
    data = _read(wid)
    return Spot(Path(data["dir"]), base() / wid) if data else None


def all_wizards() -> list[tuple[str, dict]]:
    try:
        ids = sorted(p.name for p in base().iterdir())
    except OSError:
        return []
    return [(wid, data) for wid in ids if (data := _read(wid))]


def target(d: object) -> tuple[Path | None, str]:
    """The directory to set up, or (None, why not)."""
    if not isinstance(d, str) or not d.strip() or len(d) > 4096:
        return None, "bad request"
    path = Path(d.strip()).expanduser()
    if not path.is_absolute():
        return None, "home.absolute"
    path = Path(*path.parts)  # drop a trailing slash
    if path.exists() and not path.is_dir():
        return None, "home.notDir"
    if not path.exists() and not path.parent.is_dir():
        return None, "home.noParent"
    if (path / ".mark" / "config.toml").is_file():
        return None, "home.isMark"
    return path.resolve(), ""


def start(req: dict) -> tuple[bool, str, str]:
    """Start a wizard: (ok, why not, wid). The same directory again continues its wizard."""
    path, why = target(req.get("dir"))
    text = req.get("text")
    if path is None:
        return False, why, ""
    if not isinstance(text, str) or not text.strip() or len(text) > chat.TEXT_MAX:
        return False, "bad request", ""
    wid = next((w for w, data in all_wizards() if data["dir"] == str(path)), None)
    if wid is None:
        wid = secrets.token_hex(5)
        (base() / wid).mkdir(parents=True)
        (base() / wid / "wizard.json").write_text(json.dumps({"dir": str(path), "started": time.time()}) + "\n")
    path.mkdir(exist_ok=True)
    ok, why = send(wid, text)
    return ok, why, wid


def send(wid: str, text: object) -> tuple[bool, str]:
    s = spot(wid)
    if s is None or not isinstance(text, str) or not text.strip() or len(text) > chat.TEXT_MAX:
        return False, "bad request"
    text = text.strip()
    started, why = chat.start(s, "", TICKET, text, first=f"/mark:init {text}", note=NOTE)
    return started, "" if started else f"chat.{why}"


def stop(wid: str) -> bool:
    s = spot(wid)
    return s is not None and chat.stop(s, TICKET)


def discard(wid: str) -> bool:
    """Forget a wizard that is not running; the directory stays as it is."""
    s = spot(wid)
    if s is None or chat.running(s, TICKET):
        return False
    shutil.rmtree(base() / wid)
    return True


def project(s: Spot) -> str:
    """The board id once the directory is a Mark project (registering it), else ""."""
    return home.add(s.root) if (s.root / ".mark" / "config.toml").is_file() else ""


def view(wid: str) -> dict | None:
    s = spot(wid)
    if s is None:
        return None
    return {**chat.view(s, TICKET), "id": wid, "dir": str(s.root), "path": home.short(s.root), "project": project(s)}


def cards() -> list[dict[str, object]]:
    """Wizards for the home page: those still setting up, or still talking after setup."""
    out = []
    for wid, data in all_wizards():
        s = Spot(Path(data["dir"]), base() / wid)
        live = chat.running(s, TICKET) is not None
        pid = project(s)
        if live or not pid:
            out.append({"id": wid, "dir": data["dir"], "path": home.short(s.root), "name": s.root.name, "running": live, "project": pid,
                        "started": data.get("started")})
    return out


def signature() -> tuple:
    """Changes when any wizard's chat does (the home page then reloads)."""
    sig = []
    for wid, data in all_wizards():
        for f in (base() / wid / "locks").glob("chat-*"):
            try:
                st = f.stat()
                sig.append((str(f), st.st_mtime_ns, st.st_size))
            except OSError:
                pass
        sig.append((data["dir"], (Path(data["dir"]) / ".mark" / "config.toml").is_file()))
    return tuple(sig)
