"""Human review files: `review-design.md`, `review-plan.md`, `review-merge.md`.

Each `/mark:reject` appends one round; `/mark:approve` marks every pending
round done. Comment ids `R-N` are numbered across rounds, never reset, so a
later comment can refer to or withdraw an earlier one. Only the main thread
writes these files (engine-fixed write rule).

The engine finds rounds by anchor, so the visible heading can be localized:

    ## Round 2 · 2026-10-20T08:30Z · pending <!-- mark:round 2 pending -->
    - R-3: the flip animation is still too slow
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from pathlib import Path

from .i18n import t

GATES = ("design", "plan", "merge")
_ROUND_RE = re.compile(r"^(?P<head>.*?)\s*<!-- mark:round (?P<n>\d+) (?P<state>pending|done) -->\s*$")
_ITEM_RE = re.compile(r"^\s*-\s*(R-(\d+))\b")


@dataclass
class Round:
    number: int
    pending: bool
    refs: list[str] = field(default_factory=list)


def filename(gate: str) -> str:
    return f"review-{gate}.md"


def parse(text: str) -> list[Round]:
    rounds: list[Round] = []
    for line in text.splitlines():
        m = _ROUND_RE.match(line)
        if m:
            rounds.append(Round(int(m.group("n")), m.group("state") == "pending"))
            continue
        item = _ITEM_RE.match(line)
        if item and rounds:
            rounds[-1].refs.append(item.group(1))
    return rounds


def read(path: Path) -> list[Round]:
    try:
        return parse(path.read_text(encoding="utf-8"))
    except OSError:
        return []


def pending(path: Path) -> list[Round]:
    return [r for r in read(path) if r.pending]


def max_ref(text: str) -> int:
    return max((int(m.group(2)) for line in text.splitlines() if (m := _ITEM_RE.match(line))), default=0)


def _heading(locale: str, n: int, at: str, state: str) -> str:
    label = t(locale, f"review.state.{state}")
    return f"## {t(locale, 'review.round', n=n)} · {at} · {label} <!-- mark:round {n} {state} -->"


def append_round(path: Path, locale: str, ticket_id: str, gate: str, items: list[str],
                 now: str | None = None) -> tuple[int, list[str]]:
    """Append a pending round; returns (round number, new refs)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = t(locale, "review.header", id=ticket_id, gate=gate) + "\n"
    rounds = parse(text)
    n = max((r.number for r in rounds), default=0) + 1
    first = max_ref(text) + 1
    at = now or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    refs = [f"R-{first + i}" for i in range(len(items))]
    block = [_heading(locale, n, at, "pending")]
    block += [f"- {ref}: {' '.join(item.split())}" for ref, item in zip(refs, items)]
    path.write_text(text.rstrip("\n") + "\n\n" + "\n".join(block) + "\n", encoding="utf-8")
    return n, refs


def settle(path: Path, locale: str) -> list[int]:
    """Mark every pending round done. Comment text is never touched."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    done: list[int] = []
    for i, line in enumerate(lines):
        m = _ROUND_RE.match(line)
        if m and m.group("state") == "pending":
            n = int(m.group("n"))
            parts = m.group("head").rsplit(" · ", 1)
            head = parts[0] if len(parts) == 2 else m.group("head")
            lines[i] = f"{head} · {t(locale, 'review.state.done')} <!-- mark:round {n} done -->"
            done.append(n)
    if done:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return done
