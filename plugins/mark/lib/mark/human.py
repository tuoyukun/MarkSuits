"""Proof that a human typed a command.

Approving a gate, rejecting at a gate and opening a ticket are human decisions.
The orchestrator runs the CLI for them, so the CLI needs evidence that a human
asked. The UserPromptSubmit hook sees the raw text a person typed (models
cannot trigger that event) and records one token per command:

    <state>/locks/human/<verb>-<time>-<pid>.json   {"verb", "arg", "rest", "at"}

`arg` is the ticket the person named and `rest` the words after it, so `mark approve --to
<status>` can check that the person chose that status. `mark approve|reject` need a token that
names the ticket; `mark claim` takes any `feature`/`fix` token (the number does not exist
yet), which is why those expire sooner. Tokens expire after TOKEN_TTL. Nobody may write that directory through the file tools (engine-fixed
write rule), and Bash commands that name it are blocked.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from .config import MarkConfig

TOKEN_TTL = {"approve": 12 * 3600, "reject": 12 * 3600, "feature": 2 * 3600, "fix": 2 * 3600}
VERBS = tuple(TOKEN_TTL)
_PROMPT_RE = re.compile(r"^\s*/(?:mark:)?(approve|reject|feature|fix)\b[ \t]*(\S*)([^\n]*)")
_TICKET_REF_RE = re.compile(r"^b?\d{4}(?:-[a-z0-9-]+)?$")


def token_dir(cfg: MarkConfig) -> Path:
    return cfg.state_dir / "locks" / "human"


def parse_prompt(prompt: str) -> tuple[str, str, list[str]] | None:
    """`/mark:approve 0012 planning` -> ('approve', '0012', ['planning']). None if not a Mark command."""
    m = _PROMPT_RE.match(prompt or "")
    if not m:
        return None
    rest = [w.strip(".,;:!?。，；：！？`'\"") for w in m.group(3).split()][:20]
    return m.group(1), m.group(2), [w for w in rest if w]


def record(cfg: MarkConfig, prompt: str, now: float | None = None) -> Path | None:
    parsed = parse_prompt(prompt)
    if parsed is None:
        return None
    verb, arg, rest = parsed
    if verb in ("feature", "fix") and _TICKET_REF_RE.match(arg):
        return None  # resuming an existing ticket opens nothing
    now = time.time() if now is None else now
    d = token_dir(cfg)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{verb}-{int(now * 1000)}-{os.getpid()}.json"
    path.write_text(json.dumps({"verb": verb, "arg": arg, "rest": rest, "at": now}) + "\n", encoding="utf-8")
    return path


def _matches(arg: str, ticket_id: str | None) -> bool:
    """A token for a ticket must name it; only `claim` (no ticket yet) takes any token."""
    if ticket_id is None:
        return True
    return bool(arg) and (ticket_id == arg or ticket_id.startswith(arg + "-"))


def words(cfg: MarkConfig, verb: str, ticket_id: str, now: float | None = None) -> list[str]:
    """The words after the ticket in the newest live `verb` token for it; nothing is used up."""
    now = time.time() if now is None else now
    try:
        names = sorted(os.listdir(token_dir(cfg)), reverse=True)
    except OSError:
        return []
    for name in names:
        try:
            data = json.loads((token_dir(cfg) / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("verb") == verb and now - float(data.get("at", 0)) <= TOKEN_TTL[verb] \
                and _matches(str(data.get("arg", "")), ticket_id):
            return [str(w) for w in data.get("rest", [])]
    return []


def consume(cfg: MarkConfig, verbs: tuple[str, ...], ticket_id: str | None = None,
            now: float | None = None, word: str | None = None) -> bool:
    """Use up the newest live token for one of `verbs` that names `ticket_id` (and, with `word`,
    whose text after the ticket contains it)."""
    now = time.time() if now is None else now
    d = token_dir(cfg)
    try:
        names = sorted(os.listdir(d), reverse=True)
    except OSError:
        return False
    for name in names:
        path = d / name
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if now - float(data.get("at", 0)) > TOKEN_TTL.get(str(data.get("verb")), 0):
            path.unlink(missing_ok=True)
            continue
        if word is not None and word not in data.get("rest", []):
            continue
        if data.get("verb") in verbs and _matches(str(data.get("arg", "")), ticket_id):
            path.unlink(missing_ok=True)
            return True
    return False
