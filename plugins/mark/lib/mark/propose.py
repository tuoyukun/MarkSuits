"""`mark propose <id>`: the orchestrator's suggested choices for a gate, shown on the board.

When a ticket stops for the human (`review-*`, `blocked-*`), the orchestrator pipes a small JSON
into `mark propose`: a question and a few options, each one a ready decision (approve, maybe with
a target status and an answer; or reject with comments). The board shows them as choices.

It is a suggestion, never a step of the flow: anything wrong with it (bad JSON, an illegal target,
a status that does not wait on the human) saves nothing or drops the bad option, says why, and
exits 0. The human then decides with the plain form. Choosing an option still goes through
`mark approve|reject` with the human's token, so nothing here can decide.

Saved as `<state>/locks/propose-<id>.json` (gitignored) with the status it was made for. Any
status write deletes it (`flow._write_status`), so a proposal never outlives its stop.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TextIO

from . import flow, human
from .config import MarkConfig
from .i18n import t

MAX_OPTIONS = 6
MAX_ITEMS = 20
LIMITS = {"question": 300, "label": 80, "detail": 400, "item": 500}


def path(cfg: MarkConfig, ticket_id: str) -> Path:
    return cfg.state_dir / "locks" / f"propose-{ticket_id}.json"


def clear(cfg: MarkConfig, ticket_id: str) -> None:
    path(cfg, ticket_id).unlink(missing_ok=True)


def _text(value: object, limit: int) -> str:
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def _option(raw: object, review: bool, targets: list[str]) -> dict | None:
    """One option made legal for this stop, or None when it cannot be."""
    if not isinstance(raw, dict) or not (label := _text(raw.get("label"), LIMITS["label"])):
        return None
    verb = raw.get("verb") or "approve"
    to = raw.get("to") or ""
    if verb == "reject":
        items = raw.get("items") if isinstance(raw.get("items"), list) else []
        items = [i for i in (_text(x, LIMITS["item"]) for x in items) if i]
        if not review or not items:  # a rejection needs comments, and only a review gate takes one
            return None
        opt = {"verb": "reject", "items": items[:MAX_ITEMS]}
    elif verb == "approve":
        if not isinstance(to, str) or (to and (review or to not in targets)):
            return None
        opt = {"verb": "approve", "to": to, "answer": _text(raw.get("answer"), human.TEXT_MAX)}
    else:
        return None
    return {"label": label, "detail": _text(raw.get("detail"), LIMITS["detail"]),
            "recommended": raw.get("recommended") is True, **opt}


def save(ctx: flow.Ctx, inp: TextIO) -> tuple[str, dict]:
    """Read the proposal from `inp` and save what is legal. Returns an i18n key and its params."""
    base = {"id": ctx.id}
    status = ctx.ticket.status
    if status not in flow.APPROVE or not ctx.has_gate(flow.TICKET_GATE):
        return "propose.ignored", {**base, "why": f"`{status}` does not wait on a human decision"}
    if inp.isatty():  # nothing piped in: reading would wait for a keyboard nobody uses
        return "propose.ignored", {**base, "why": "no JSON on stdin"}
    try:
        data = json.loads(inp.read())
    except (ValueError, OSError) as exc:
        return "propose.ignored", {**base, "why": f"not valid JSON: {exc}"}
    raw = data.get("options") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return "propose.ignored", {**base, "why": 'expected {"question": ..., "options": [...]}'}
    review = bool(flow.APPROVE[status][0])
    targets = [] if review else flow.approve_targets(ctx)
    options, dropped = [], []
    for item in raw:
        opt = _option(item, review, targets)
        if opt and len(options) < MAX_OPTIONS:
            options.append(opt)
        else:
            dropped.append(_text(item.get("label"), LIMITS["label"]) if isinstance(item, dict) else "?")
    if not options:
        return "propose.ignored", {**base, "why": "no option is a legal choice here"}
    seen = False
    for o in options:  # one recommendation at most, or it says nothing
        o["recommended"], seen = o["recommended"] and not seen, seen or o["recommended"]
    p = path(ctx.cfg, ctx.id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"status": status, "question": _text(data.get("question"), LIMITS["question"]),
                             "options": options}, ensure_ascii=False, indent=2), encoding="utf-8")
    return "propose.saved", {**base, "n": len(options),
                             "dropped": ", ".join(d or "?" for d in dropped) or "-"}


def load(cfg: MarkConfig, ticket_id: str, status: str) -> dict | None:
    """The saved proposal for this ticket at this status, or None."""
    try:
        data = json.loads(path(cfg, ticket_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("status") != status:
        return None
    return {"question": data.get("question", ""), "options": data.get("options", [])}


def hint(ctx: flow.Ctx) -> str:
    """What `mark next` adds at a stop that waits on the human: how to propose ("" elsewhere)."""
    status = ctx.ticket.status
    if status not in flow.APPROVE or not ctx.has_gate(flow.TICKET_GATE):
        return ""
    if flow.APPROVE[status][0]:
        return t(ctx.cfg.locale, "next.propose_review", id=ctx.id)
    return t(ctx.cfg.locale, "next.propose_blocked", id=ctx.id,
                     targets=" | ".join(flow.approve_targets(ctx)) or "-")
