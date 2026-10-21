"""Doc budget: byte limits for the docs agents load, from `[[doc_budget]]` in config.

Every appended rule looks harmless; together they make every cold start slower. A
budget turns "add one more line" into a trade-off. Budgets belong on docs whose
length follows process complexity (CLAUDE.md, role files,
prompts, formats, thin one-shot artifacts such as fix-plan.md), not on docs whose
length follows delivered work: there the only way under a byte wall is deleting
someone else's verified record.

Rules match paths relative to the checkout, first match wins; `max_bytes = 0`
exempts a path from a broader rule. A file already over budget may still shrink:
only a write that leaves it over budget AND larger than before is refused.
"""
from __future__ import annotations

from pathlib import Path

from . import globs
from .gitutil import git

TOP_LINES = 3


def limit_for(cfg, rel: str) -> int | None:
    """Byte budget for `rel`, or None when no rule applies (or it is exempt)."""
    for rule in cfg.doc_budget:
        if globs.match(rule.glob, rel):
            return rule.max_bytes or None
    return None


def overrun(cfg, rel: str, size: int, old_size: int | None) -> int | None:
    """The limit `rel` would break at `size`; None when the write is fine."""
    limit = limit_for(cfg, rel)
    if limit is None or size <= limit or (old_size is not None and size <= old_size):
        return None
    return limit


def longest_lines(text: str) -> str:
    """The lines worth cutting first, so the author does not bisect by hand."""
    rows = sorted(((len(ln.encode("utf-8")), i, ln) for i, ln in enumerate(text.splitlines(), 1)),
                  reverse=True)[:TOP_LINES]
    return "\n".join(f"  L{i} ({n} B): {ln.strip()[:60]}" for n, i, ln in rows)


def branch_overruns(cfg, worktree: Path, base: str) -> list[str]:
    """Files `HEAD` changes against `base` that grew past their budget, as `path (size > limit)`.

    Writes through Bash never pass the pre-write guard, so the merge checks them."""
    code, out = git(["diff", "--name-only", "--no-renames", "--diff-filter=AM", base, "HEAD"], worktree)
    found = []
    for rel in out.splitlines() if code == 0 else []:
        if limit_for(cfg, rel) is None:
            continue
        try:
            size = (worktree / rel).stat().st_size
        except OSError:
            continue
        old_code, old = git(["cat-file", "-s", f"{base}:{rel}"], worktree)
        limit = overrun(cfg, rel, size, int(old) if old_code == 0 and old.isdigit() else None)
        if limit:
            found.append(f"{rel} ({size} B > {limit} B)")
    return found
