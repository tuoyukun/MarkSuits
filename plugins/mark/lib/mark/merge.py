"""Automated merge: `mark merge <id>` takes a ticket from `pending-merge` to `passed`.

1. Checks: status, the tester's `<!-- mark:verdict PASSED -->`, `merge-after` tickets
   passed or superseded (no cycle), clean worktree, main checkout on main.
2. In the worktree: merge the latest main into the ticket branch (conflict: abort),
   then refuse docs the branch grew past `[[doc_budget]]`, end-to-end tests its plan does
   not name as new, and a `JOURNEYS.md` that does not list exactly the tests there are.
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
from pathlib import Path

from . import budget, e2e, flow
from .flow import Ctx, FlowError
from .gitutil import dirty_paths, git, has_remote, ref_exists, worktrees
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


def _regression(cfg, worktree: Path, log_name: str, notes: Notes) -> None:
    cmd = cfg.merge_regression
    if not cmd:
        notes.append(("merge.no_regression", {}))
        return
    log = cfg.state_dir / "locks" / f"{log_name}.merge.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as fh:
        code = subprocess.run(cmd, shell=True, cwd=worktree, stdout=fh,
                              stderr=subprocess.STDOUT).returncode
    if code != 0:
        tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-LOG_TAIL:])
        raise FlowError("merge.red", cmd=cmd, code=code, log=log.relative_to(cfg.root).as_posix(), tail=tail)
    notes.append(("merge.green", {"cmd": cmd}))


def _suite_at(cfg, worktree: Path, ref: str, tests_dir: str) -> set[str]:
    """Test titles in the spec files at `ref` (the base the branch was merged with)."""
    code, out = git(["ls-tree", "-r", "--name-only", ref, "--", tests_dir], worktree)
    titles: set[str] = set()
    for rel in out.splitlines() if code == 0 else []:
        if "node_modules/" in rel or not e2e._SPEC.search(rel):
            continue
        ok, text = git(["show", f"{ref}:{rel}"], worktree)
        if ok == 0:
            titles |= {b.title for b in e2e.extract_tests(text)}
    return titles


def _journeys(cfg, worktree: Path, base: str, plan: str | None) -> None:
    """The branch adds only the end-to-end tests its plan names as new, and JOURNEYS.md lists
    exactly the tests there are. `plan` None: a general lane, no plan to hold it to."""
    tests_dir = cfg.path("tests")
    if cfg.tests_profile != "playwright" or not tests_dir:
        return
    now = e2e.suite(worktree, tests_dir)
    if plan is not None:
        extra = sorted(set(now) - _suite_at(cfg, worktree, base, tests_dir) - e2e.planned_new(plan))
        if extra:
            raise FlowError("merge.journey_unplanned", tests="\n".join(f"  - {x}" for x in extra))
    index_path = worktree / tests_dir / e2e.INDEX_FILE
    listed = e2e.indexed(index_path.read_text(encoding="utf-8")) if index_path.is_file() else set()
    missing, stale = sorted(set(now) - listed), sorted(listed - set(now))
    if missing or stale:
        raise FlowError("merge.journey_index", index=f"{tests_dir}/{e2e.INDEX_FILE}",
                        missing="\n".join(f"  - {x}" for x in missing) or "  -",
                        stale="\n".join(f"  - {x}" for x in stale) or "  -")


def land(cfg, worktree: Path, branch: str, log_name: str, conflict: FlowError,
         plan: str | None = None) -> Notes:
    """Merge the latest main into `branch` (in its worktree), run the regression there,
    fast-forward main and push it. Main is untouched unless every step passes. `plan`: the
    ticket's plan text, which names the end-to-end tests the branch may add."""
    notes: Notes = []
    main, main_branch = cfg.root, cfg.main_branch
    base = main_branch
    if has_remote(main):
        if git(["fetch", "-q", "origin", main_branch], main)[0] != 0:
            raise FlowError("merge.fetch_failed", main=main_branch)
        base = f"origin/{main_branch}"

    if git(["merge", "-q", "--no-edit", base], worktree)[0] != 0:
        git(["merge", "--abort"], worktree)
        conflict.params["base"] = base
        raise conflict
    over = budget.branch_overruns(cfg, worktree, base)
    if over:
        raise FlowError("merge.budget", files="\n".join(f"  - {f}" for f in over))
    _journeys(cfg, worktree, base, plan)
    _regression(cfg, worktree, log_name, notes)

    before = git(["rev-parse", "HEAD"], main)[1]
    if git(["merge", "-q", "--ff-only", branch], main)[0] != 0:
        raise FlowError("merge.ff_failed", main=main_branch, branch=branch)
    if has_remote(main) and git(["push", "-q", "origin", main_branch], main)[0] != 0:
        git(["reset", "-q", "--keep", before], main)
        raise FlowError("merge.push_failed", main=main_branch)
    notes.append(("merge.landed", {"branch": branch, "main": main_branch}))
    return notes


def cleanup(cfg, worktree: Path | None, branch: str, force: bool = False) -> Notes:
    """Remove the remote branch, worktree and local branch. Never fails: the work is on main
    (or, with `force`, the caller has decided to discard it)."""
    notes: Notes = []
    main = cfg.root
    # Remote first: `branch -d` checks the upstream, which lacks the merge commit.
    if ref_exists(main, f"refs/remotes/origin/{branch}") and \
            git(["push", "-q", "origin", "--delete", branch], main)[0] != 0:
        notes.append(("merge.kept_remote", {"branch": branch}))
    if worktree is not None and \
            git(["worktree", "remove", *(["--force"] if force else []), str(worktree)], main)[0] != 0:
        notes.append(("merge.kept_worktree", {"wt": str(worktree)}))
    elif git(["branch", "-q", "-D" if force else "-d", branch], main)[0] != 0:
        notes.append(("merge.kept_branch", {"branch": branch}))
    return notes


def _merge(ctx: Ctx) -> Notes:
    _precheck(ctx)
    conflict = FlowError("merge.conflict", id=ctx.id, branch=ctx.branch)
    plan = next((p.read_text(encoding="utf-8", errors="replace")
                 for p in map(ctx.find, e2e.PLAN_FILES) if p is not None), "")
    notes = land(ctx.cfg, ctx.worktree, ctx.branch, ctx.id, conflict, plan)
    flow.set_status(ctx, "passed")
    notes += [(key, {}) for key in flow.commit(ctx, f"{ctx.id}: merged, pending-merge -> passed")]
    return notes + cleanup(ctx.cfg, ctx.worktree, ctx.branch)
