"""`mark ask <id> [file]`: questions with choices for the human in the board chat.

A board chat turn is `claude -p`, which has no AskUserQuestion. So the session pipes the same JSON
that tool takes into `mark ask` and ends its turn: 1-4 questions, each with a `question`, a short
`header`, 2-4 `options` (`label`, `description`) and `multiSelect`. The board shows them as a form
under the chat; the human's answers go back as their next chat message, plain text like any other.

JSON comes on stdin (a heredoc) or from a file, for permission modes that refuse a heredoc with
JSON in it. Like `mark propose` it is only a help: bad input saves nothing, says why, exits 0, and
the questions stay in the chat as text. Saved as `<state>/locks/ask-<id>.json` (gitignored); the
next human message deletes it (`chat.start`), so a form never outlives the turn that asked.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TextIO

from .config import MarkConfig

MAX_QUESTIONS = 4
MAX_OPTIONS = 4
LIMITS = {"question": 300, "header": 30, "label": 80, "description": 300}


def path(cfg: MarkConfig, ticket_id: str) -> Path:
    return cfg.state_dir / "locks" / f"ask-{ticket_id}.json"


def clear(cfg: MarkConfig, ticket_id: str) -> None:
    path(cfg, ticket_id).unlink(missing_ok=True)


def _text(value: object, limit: int) -> str:
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def _question(raw: object) -> dict | None:
    """One question as the board shows it, or None when it is not a choice question."""
    if not isinstance(raw, dict) or not (question := _text(raw.get("question"), LIMITS["question"])):
        return None
    options = raw.get("options") if isinstance(raw.get("options"), list) else []
    options = [{"label": label, "description": _text(o.get("description"), LIMITS["description"])}
               for o in options if isinstance(o, dict) and (label := _text(o.get("label"), LIMITS["label"]))]
    if len(options) < 2:
        return None
    return {"question": question, "header": _text(raw.get("header"), LIMITS["header"]),
            "multiSelect": raw.get("multiSelect") is True, "options": options[:MAX_OPTIONS]}


def save(cfg: MarkConfig, ticket_id: str, inp: TextIO, file: str | None = None) -> tuple[str, dict]:
    """Read the questions from `file` or `inp` and save the valid ones. Returns an i18n key and its params."""
    base = {"id": ticket_id}
    if file is None and inp.isatty():  # nothing piped in: reading would wait for a keyboard nobody uses
        return "ask.ignored", {**base, "why": "no JSON on stdin"}
    try:
        data = json.loads(Path(file).read_text(encoding="utf-8") if file else inp.read())
    except (ValueError, OSError) as exc:
        return "ask.ignored", {**base, "why": f"not valid JSON: {exc}"}
    raw = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return "ask.ignored", {**base, "why": 'expected {"questions": [...]}'}
    questions = [q for q in map(_question, raw) if q][:MAX_QUESTIONS]
    if not questions:
        return "ask.ignored", {**base, "why": "no question has a text and two options"}
    p = path(cfg, ticket_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"questions": questions}, ensure_ascii=False, indent=2), encoding="utf-8")
    return "ask.saved", {**base, "n": len(questions), "dropped": len(raw) - len(questions)}


def load(cfg: MarkConfig, ticket_id: str) -> dict | None:
    try:
        data = json.loads(path(cfg, ticket_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("questions"), list) else None
