"""Tickets: one directory per ticket, one `status.md` per directory.

Layout under the project's state dir (default `.mark/`):

    features/<NNNN-slug>/status.md
    bugs/b<NNNN-slug>/status.md
    features/.numbers/<NNNN>        claim markers (gitignored)

The directory is the index: there is no global board file, because a shared
writable board conflicts on every concurrent change. Ticket id and kind come
from the path and are never repeated inside the file.

`status.md`:

    ---
    status: developing
    owner: coder-impl
    updated: 2026-01-31
    updater: orchestrator
    desc: one line, <= 200 chars
    merge-after: [0012, b0007]     (optional)
    leftover: 0                    (required from pending-merge on)
    ---

    One-line note, <= 240 chars. Process details go in log.md.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import states
from .config import MarkConfig

STATUS_FILENAME = "status.md"
NUMBERS_DIRNAME = ".numbers"
DESC_MAX = 200
NOTE_MAX = 240
MAX_PROBE = 200

BUG_PREFIX = "b"
_ID_RE = {
    states.FEATURE: re.compile(r"^(\d{4})-[a-z0-9][a-z0-9-]*$"),
    states.BUG: re.compile(rf"^{BUG_PREFIX}(\d{{4}})-[a-z0-9][a-z0-9-]*$"),
}
_NUM_FILE_RE = re.compile(r"^(\d{4})$")
_FIELD_RE = re.compile(r"^([a-z][a-z0-9_-]*):\s*(.*)$")
_REF_RE = re.compile(rf"^{BUG_PREFIX}?\d{{4}}$")

FIELD_ORDER = ("status", "owner", "updated", "updater", "desc", "merge-after", "leftover")


# --------------------------------------------------------------------------
# status.md format
# --------------------------------------------------------------------------

def parse_status(text: str) -> tuple[dict[str, str], str]:
    """Split frontmatter fields and the note. Tolerates a missing frontmatter."""
    fields: dict[str, str] = {}
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].splitlines():
                m = _FIELD_RE.match(line.strip())
                if m:
                    fields[m.group(1)] = m.group(2).strip()
            body = text[end + 4:]
    return fields, body.strip()


def format_status(fields: dict[str, str], note: str = "") -> str:
    ordered = [k for k in FIELD_ORDER if k in fields]
    ordered += sorted(k for k in fields if k not in FIELD_ORDER)
    lines = ["---", *(f"{k}: {fields[k]}" for k in ordered), "---", ""]
    if note:
        lines += [note.strip(), ""]
    return "\n".join(lines)


def parse_merge_after(raw: str) -> list[str] | None:
    """`[0012, b0007]` -> ['0012', 'b0007']; `[]` -> []; malformed -> None."""
    raw = raw.strip()
    if not (raw.startswith("[") and raw.endswith("]")):
        return None
    refs = [r.strip() for r in raw[1:-1].split(",") if r.strip()]
    if not all(_REF_RE.match(r) for r in refs):
        return None
    return refs


# --------------------------------------------------------------------------
# Locating tickets
# --------------------------------------------------------------------------

def main_root(root: Path) -> Path:
    """The main checkout for `root`, even when `root` is a git worktree.

    Ticket state, claim markers and gates are global to the repository, so
    they must be read from the main checkout. Each worktree has its own copy
    of the state dir; resolving to it would give every worktree its own
    number space. Falls back to `root` outside git or if the main checkout is
    not a Mark project.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return root
    common = out.stdout.strip()
    if out.returncode != 0 or not common:
        return root
    candidate = Path(common).resolve().parent
    if (candidate / ".mark" / "config.toml").is_file():
        return candidate
    return root


def kind_dir(cfg: MarkConfig, kind: str) -> Path:
    return cfg.state_dir / states.KIND_DIRS[kind]


def ticket_number(kind: str, ticket_id: str) -> int | None:
    m = _ID_RE[kind].match(ticket_id)
    return int(m.group(1)) if m else None


def ref_of(kind: str, ticket_id: str) -> str:
    """Short reference used in `merge-after`: '0012' or 'b0007'."""
    n = ticket_number(kind, ticket_id)
    prefix = BUG_PREFIX if kind == states.BUG else ""
    return f"{prefix}{n:04d}" if n is not None else ticket_id


@dataclass
class Ticket:
    kind: str
    id: str
    path: Path
    fields: dict[str, str] = field(default_factory=dict)
    note: str = ""
    exists: bool = True

    def get(self, name: str) -> str:
        return self.fields.get(name, "")

    @property
    def status(self) -> str:
        return self.get("status")

    @property
    def side(self) -> str:
        return states.side(self.status) if states.is_valid(self.kind, self.status) else "unknown"

    def as_dict(self) -> dict[str, object]:
        return {"kind": self.kind, "id": self.id, **self.fields, "note": self.note}


def load_ticket(cfg: MarkConfig, kind: str, ticket_id: str) -> Ticket:
    path = kind_dir(cfg, kind) / ticket_id / STATUS_FILENAME
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return Ticket(kind, ticket_id, path, exists=False)
    fields, note = parse_status(text)
    return Ticket(kind, ticket_id, path, fields, note)


def ticket_dirs(cfg: MarkConfig, kind: str) -> list[str]:
    base = kind_dir(cfg, kind)
    try:
        names = os.listdir(base)
    except OSError:
        return []
    return sorted(n for n in names if not n.startswith(".") and (base / n).is_dir())


def all_tickets(cfg: MarkConfig) -> list[Ticket]:
    """Every ticket, most recently updated first (ties: id descending)."""
    found = [load_ticket(cfg, k, t) for k in states.KINDS for t in ticket_dirs(cfg, k)]
    found.sort(key=lambda t: (t.get("updated"), t.id), reverse=True)
    return found


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Problem:
    key: str                    # i18n message key
    params: dict[str, object]


def ticket_problems(ticket: Ticket, rel: str) -> list[Problem]:
    if not ticket.exists:
        return [Problem("check.missing", {"rel": rel})]
    out: list[Problem] = []
    status = ticket.status
    if not states.is_valid(ticket.kind, status):
        out.append(Problem("check.bad_status", {"rel": rel, "status": status or "(empty)", "kind": ticket.kind}))
    desc = ticket.get("desc")
    if len(desc) > DESC_MAX:
        out.append(Problem("check.desc_long", {"rel": rel, "n": len(desc), "limit": DESC_MAX}))
    if len(ticket.note) > NOTE_MAX:
        out.append(Problem("check.note_long", {"rel": rel, "n": len(ticket.note), "limit": NOTE_MAX}))
    if not ticket.get("updated"):
        out.append(Problem("check.no_updated", {"rel": rel}))
    if status in states.LEFTOVER_REQUIRED:
        if "leftover" not in ticket.fields:
            out.append(Problem("check.no_leftover", {"rel": rel, "status": status}))
        elif not ticket.get("leftover").isdigit():
            out.append(Problem("check.bad_leftover", {"rel": rel, "value": ticket.get("leftover")}))
    if "merge-after" in ticket.fields and parse_merge_after(ticket.get("merge-after")) is None:
        out.append(Problem("check.bad_merge_after", {"rel": rel, "value": ticket.get("merge-after")}))
    return out


def check(cfg: MarkConfig) -> list[Problem]:
    problems: list[Problem] = []
    for kind in states.KINDS:
        for ticket_id in ticket_dirs(cfg, kind):
            ticket = load_ticket(cfg, kind, ticket_id)
            rel = ticket.path.relative_to(cfg.root).as_posix()
            problems.extend(ticket_problems(ticket, rel))
    return problems


# --------------------------------------------------------------------------
# Claiming a ticket number
# --------------------------------------------------------------------------

class ClaimError(Exception):
    def __init__(self, key: str, **params: object):
        super().__init__(key)
        self.key = key
        self.params = params


def slugify(text: str) -> str:
    """Free text -> kebab-case ASCII slug; falls back to a timestamp if too short."""
    s = "".join(ch for ch in text[:50].lower() if ch.isascii())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s if len(s) >= 3 else time.strftime("%Y%m%d-%H%M%S")


def used_numbers(cfg: MarkConfig, kind: str) -> set[int]:
    """Numbers already handed out: ticket directories plus claim markers."""
    base = kind_dir(cfg, kind)
    used = {n for name in ticket_dirs(cfg, kind) if (n := ticket_number(kind, name)) is not None}
    try:
        markers = os.listdir(base / NUMBERS_DIRNAME)
    except OSError:
        markers = []
    used |= {int(m.group(1)) for name in markers if (m := _NUM_FILE_RE.match(name))}
    return used


def _claim_number(cfg: MarkConfig, kind: str, ticket_hint: str) -> tuple[int, Path]:
    """Reserve a number with O_EXCL. A taken number moves on; never overwrite."""
    numbers = kind_dir(cfg, kind) / NUMBERS_DIRNAME
    numbers.mkdir(parents=True, exist_ok=True)
    n = max(used_numbers(cfg, kind) or {0}) + 1
    payload = json.dumps({
        "id": ticket_hint, "pid": os.getpid(), "host": socket.gethostname(),
        "at": _dt.datetime.now().isoformat(timespec="seconds"),
    }) + "\n"
    for _ in range(MAX_PROBE):
        marker = numbers / f"{n:04d}"
        try:
            fd = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            n += 1
            continue
        try:
            os.write(fd, payload.encode("utf-8"))
        finally:
            os.close(fd)
        return n, marker
    raise ClaimError("claim.exhausted", n=MAX_PROBE, path=str(numbers))


def claim(cfg: MarkConfig, kind: str, desc: str, slug: str | None = None,
          today: str | None = None) -> Ticket:
    """Atomically reserve a number, create the ticket dir and its first status.md.

    Order matters: reserve number (O_EXCL) -> pick a free slug within that
    number -> mkdir. If anything fails after the reservation, the marker is
    removed so the number is not burned.
    """
    if kind not in states.KINDS:
        raise ValueError(f"kind must be one of {states.KINDS}, got {kind!r}")
    desc = " ".join(desc.split())
    if len(desc) > DESC_MAX:
        raise ClaimError("claim.desc_long", n=len(desc), limit=DESC_MAX)
    slug = slugify(slug or desc)
    prefix = BUG_PREFIX if kind == states.BUG else ""
    n, marker = _claim_number(cfg, kind, f"{prefix}{slug}")
    try:
        base = kind_dir(cfg, kind)
        for i in range(MAX_PROBE):
            ticket_id = f"{prefix}{n:04d}-{slug if i == 0 else f'{slug}-{i + 1}'}"
            try:
                (base / ticket_id).mkdir()
            except FileExistsError:
                continue
            break
        else:
            raise ClaimError("claim.exhausted", n=MAX_PROBE, path=str(base))
        initial = states.INITIAL[kind]
        fields = {
            "status": initial,
            "owner": states.ROLE_FOR_STATUS[kind][initial],
            "updated": today or _dt.date.today().isoformat(),
            "updater": "orchestrator",
            "desc": desc,
        }
        path = base / ticket_id / STATUS_FILENAME
        path.write_text(format_status(fields), encoding="utf-8")
        return Ticket(kind, ticket_id, path, fields)
    except BaseException:
        try:
            marker.unlink()
        except OSError:
            pass
        raise
