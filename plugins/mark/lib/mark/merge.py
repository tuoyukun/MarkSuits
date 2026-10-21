"""Automated merge: `mark merge <id>` takes a ticket from `pending-merge` to `passed`.

1. Checks: status, the tester's `<!-- mark:verdict PASSED -->`, `merge-after` tickets
   passed or superseded (no cycle), clean worktree, main checkout on main.
2. In the worktree: merge the latest main into the ticket branch (conflict: abort).
3. In the worktree: run `[merge] regression` (exit 0 = green; empty = skipped).
4. In the main checkout: fast-forward main to the branch and push it.
5. `passed`, committed and pushed; then the worktree and branch are removed.

Main only moves at step 4, and only by fast-forward, so a failure before it lands
nothing. Every failure is recorded as `locks/<id>.merge.result.json`, so `mark next`
stops for the human instead of retrying.
"""
from __future__ import annotations

import json
import re
import subprocess
import time

from . import flow
from .flow import Ctx, FlowError
from .gitutil import dirty_paths, git, has_remote, worktrees
from .i18n import t

_VERDICT_RE = re.compile(r"<!--\s*mark:verdict\s+(PASSED|FAILED)\s*-->")
LOG_TAIL = 20
ORDER_KEYS = ("merge.waiting", "merge.cycle")

Notes = list[tuple[str, dict]]


def run(ctx: Ctx) -> Notes:
    try:
        return _merge(ctx)
    except FlowError as exc:
        if exc.key not in ORDER_KEYS:  # order is re-checked by `mark next`; not a failed merge
            _record(ctx, t(ctx.cfg.locale, exc.key, **exc.params))
        raise


def _record(ctx: Ctx, reason: str) -> None:
    path = ctx.cfg.state_dir / "locks" / f"{ctx.id}.merge.result.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"at": time.time(), "result": "FAILED", "reason": reason},
                                   ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # the refusal itself still reaches the caller


def _precheck(ctx: Ctx) -> None:
    if ctx.ticket.status != "pending-merge":
        raise FlowError("merge.status", id=ctx.id, status=ctx.ticket.status)
    blocked = flow.merge_blockers(ctx.cfg, ctx.ticket)
    if blocked:
        raise blocked
    if not flow._is_git(ctx):
        raise FlowError("merge.no_git")
    flow._require_main_branch(ctx)
    verdict = ctx.find("verdict.md")
    found = _VERDICT_RE.findall(verdict.read_text(encoding="utf-8")) if verdict else []
    if not found or found[-1] != "PASSED":
        raise FlowError("merge.verdict", id=ctx.id)
    if not any(b == ctx.branch for _, b in worktrees(ctx.main)):
        raise FlowError("merge.no_worktree", id=ctx.id, branch=ctx.branch)
    dirty = dirty_paths(ctx.worktree, ".")
    if dirty:
        raise FlowError("flow.iso.dirty", wt=str(ctx.worktree), id=ctx.id,
                        files="\n".join(f"  - {p}" for p in dirty[:10]))


def _regression(ctx: Ctx, notes: Notes) -> None:
    cmd = ctx.cfg.merge_regression
    if not cmd:
        notes.append(("merge.no_regression", {}))
        return
    log = ctx.cfg.state_dir / "locks" / f"{ctx.id}.merge.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as fh:
        code = subprocess.run(cmd, shell=True, cwd=ctx.worktree, stdout=fh,
                              stderr=subprocess.STDOUT).returncode
    if code != 0:
        tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-LOG_TAIL:])
        raise FlowError("merge.red", cmd=cmd, code=code, log=log.relative_to(ctx.main).as_posix(), tail=tail)
    notes.append(("merge.green", {"cmd": cmd}))


def _merge(ctx: Ctx) -> Notes:
    _precheck(ctx)
    notes: Notes = []
    main, branch, main_branch = ctx.main, ctx.branch, ctx.cfg.main_branch
    remote = has_remote(main)
    base = main_branch
    if remote:
        if git(["fetch", "-q", "origin", main_branch], main)[0] != 0:
            raise FlowError("merge.fetch_failed", main=main_branch)
        base = f"origin/{main_branch}"

    if git(["merge", "-q", "--no-edit", base], ctx.worktree)[0] != 0:
        git(["merge", "--abort"], ctx.worktree)
        raise FlowError("merge.conflict", id=ctx.id, base=base, branch=branch)
    _regression(ctx, notes)

    before = git(["rev-parse", "HEAD"], main)[1]
    if git(["merge", "-q", "--ff-only", branch], main)[0] != 0:
        raise FlowError("merge.ff_failed", main=main_branch, branch=branch)
    if remote and git(["push", "-q", "origin", main_branch], main)[0] != 0:
        git(["reset", "-q", "--keep", before], main)
        raise FlowError("merge.push_failed", main=main_branch)
    notes.append(("merge.landed", {"branch": branch, "main": main_branch}))

    flow.set_status(ctx, "passed")
    notes += [(key, {}) for key in flow.commit(ctx, f"{ctx.id}: merged, pending-merge -> passed")]

    # Cleanup never fails the merge: the work is already on main.
    # Remote first: `branch -d` checks the upstream, which lacks the merge commit.
    if remote and git(["push", "-q", "origin", "--delete", branch], main)[0] != 0:
        notes.append(("merge.kept_remote", {"branch": branch}))
    if git(["worktree", "remove", str(ctx.worktree)], main)[0] != 0:
        notes.append(("merge.kept_worktree", {"wt": str(ctx.worktree)}))
    elif git(["branch", "-q", "-d", branch], main)[0] != 0:
        notes.append(("merge.kept_branch", {"branch": branch}))
    return notes
