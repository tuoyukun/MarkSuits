"""Automated merge: `mark merge <id>` takes a ticket from `pending-merge` to `passed`.

1. Checks: status, the tester's `<!-- mark:verdict PASSED -->`, `merge-after` tickets
   passed or superseded (no cycle), clean worktree, main checkout on main.
2. In the worktree: merge the latest main into the ticket branch (conflict: abort),
   then refuse docs the branch grew past `[[doc_budget]]`, end-to-end tests its plan does
   not name as new, and a `JOURNEYS.md` that does not list exactly the tests there are.
3. In the worktree: run `[merge] regression` (exit 0 = green; empty = skipped). Skipped too
   when `mark regress` recorded it green on the same code: nothing but ticket docs changed
   since, main included.
4. In the main checkout: fast-forward main to the branch and push it.
5. `passed`, committed and pushed; then the worktree and branch are removed.

Main only moves at step 4, and only by fast-forward, so a failure before it lands
nothing. Every failure is recorded as `locks/<id>.merge.result.json`, so `mark next`
stops for the human instead of retrying.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from . import budget, e2e, flow, reviews, states
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
        # `conclusion`: the next dispatch hands the failure to the role that fixes it.
        path.write_text(json.dumps({"at": time.time(), "result": "FAILED", "reason": reason, "conclusion": reason},
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


def _run_regression(cfg, worktree: Path, log: Path) -> tuple[int, dict]:
    """Run `[merge] regression` in `worktree`, output to `log`; (exit code, params for a red message)."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as fh:
        code = subprocess.run(cfg.merge_regression, shell=True, cwd=worktree, stdout=fh,
                              stderr=subprocess.STDOUT).returncode
    tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-LOG_TAIL:])
    return code, {"cmd": cfg.merge_regression, "code": code, "log": log.relative_to(cfg.root).as_posix(),
                  "tail": tail}


def _regression(cfg, worktree: Path, log_name: str, notes: Notes) -> None:
    cmd = cfg.merge_regression
    if not cmd:
        notes.append(("merge.no_regression", {}))
        return
    code, params = _run_regression(cfg, worktree, cfg.state_dir / "locks" / f"{log_name}.merge.log")
    if code != 0:
        raise FlowError("merge.red", **params)
    notes.append(("merge.green", {"cmd": cmd}))


def _green_path(cfg, ticket_id: str) -> Path:
    return cfg.state_dir / "locks" / f"{ticket_id}.regress.json"


def _snapshot(worktree: Path) -> str | None:
    """Tree id of the worktree's files as they are now, committed or not (ignored files aside)."""
    with tempfile.TemporaryDirectory() as d:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(d) / "index")}
        for args in (["add", "-A"], ["write-tree"]):
            p = subprocess.run(["git", "-C", str(worktree), *args], env=env, capture_output=True, text=True)
            if p.returncode != 0:
                return None
    return p.stdout.strip() or None


def _same_code(cfg, worktree: Path, tree: str) -> bool:
    """HEAD matches `tree` outside the ticket dirs (verdicts, status: main moves with them)."""
    skip = [f":(exclude){cfg.state_rel}/{d}" for d in states.KIND_DIRS.values()]
    return bool(tree) and git(["diff", "--quiet", tree, "HEAD", "--", ".", *skip], worktree)[0] == 0


def regress(ctx: Ctx) -> Notes:
    """`mark regress <id>`: run the merge regression in the ticket's worktree as it is now. Green
    records the code it ran on, and `mark merge` skips its own run while the code is the same."""
    cfg = ctx.cfg
    if not cfg.merge_regression:
        return [("merge.no_regression", {})]
    if not ctx.worktree.is_dir():
        raise FlowError("merge.no_worktree", id=ctx.id, branch=ctx.branch)
    green = _green_path(cfg, ctx.id)
    green.unlink(missing_ok=True)
    tree = _snapshot(ctx.worktree)  # before the run: what it tested, whatever the run writes
    code, params = _run_regression(cfg, ctx.worktree, cfg.state_dir / "locks" / f"{ctx.id}.regress.log")
    if code != 0:
        raise FlowError("regress.red", **params)
    if tree:
        green.write_text(json.dumps({"tree": tree, "cmd": cfg.merge_regression, "at": time.time()}),
                         encoding="utf-8")
    return [("regress.green", {"cmd": cfg.merge_regression})]


def _tested(ctx: Ctx) -> dict | None:
    try:
        return json.loads(_green_path(ctx.cfg, ctx.id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _suite_at(cfg, worktree: Path, ref: str, tests_dir: str) -> set[str]:
    """Test titles in the spec files at `ref` (the base the branch was merged with)."""
    code, out = git(["ls-tree", "-r", "--name-only", ref, "--", tests_dir], worktree)
    titles: set[str] = set()
    for rel in out.splitlines() if code == 0 else []:
        if "node_modules/" in rel or not e2e.holds_tests(rel, cfg.tests_profile):
            continue
        ok, text = git(["show", f"{ref}:{rel}"], worktree)
        if ok == 0:
            titles |= {b.title for b in e2e.tests_in(rel, text, cfg.tests_profile)}
    return titles


def _journeys(cfg, worktree: Path, base: str, plan: str | None) -> None:
    """The branch adds only the end-to-end tests its plan names as new, and JOURNEYS.md lists
    exactly the tests there are. `plan` None: a general lane, no plan to hold it to."""
    tests_dir = cfg.path("tests")
    if cfg.tests_profile == "none" or not tests_dir:
        return
    now = e2e.suite(worktree, tests_dir, cfg.tests_profile)
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
         plan: str | None = None, tested: dict | None = None) -> Notes:
    """Merge the latest main into `branch` (in its worktree), run the regression there,
    fast-forward main and push it. Main is untouched unless every step passes. `plan`: the
    ticket's plan text, which names the end-to-end tests the branch may add. `tested`: the
    `mark regress` record; its green stands while the code it ran on is unchanged."""
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
    if tested and cfg.merge_regression and tested.get("cmd") == cfg.merge_regression \
            and _same_code(cfg, worktree, str(tested.get("tree", ""))):
        notes.append(("merge.reused", {"cmd": cfg.merge_regression}))
    else:
        _regression(cfg, worktree, log_name, notes)

    before = git(["rev-parse", "HEAD"], main)[1]
    if git(["merge", "-q", "--ff-only", branch], main)[0] != 0:
        raise FlowError("merge.ff_failed", main=main_branch, branch=branch)
    if has_remote(main) and git(["push", "-q", "origin", main_branch], main)[0] != 0:
        git(["reset", "-q", "--keep", before], main)
        raise FlowError("merge.push_failed", main=main_branch)
    notes.append(("merge.landed", {"branch": branch, "main": main_branch}))
    return notes


REMOVE_TRIES = 3
REMOVE_WAIT = 5.0


def _remove_worktree(main: Path, worktree: Path, force: bool) -> str:
    """Remove a worktree; "" on success, else the last error. Retries: right after the regression,
    a dev server or bundler it started may still write into the tree while git deletes it. A
    failed `--force` can leave git's record gone and the directory half deleted; then (only when
    forcing) the directory itself goes."""
    error = ""
    for attempt in range(REMOVE_TRIES):
        if attempt:
            time.sleep(REMOVE_WAIT)
        if not worktree.exists():
            break
        if any(p.resolve() == worktree.resolve() for p, _ in worktrees(main)):
            p = subprocess.run(["git", "-C", str(main), "worktree", "remove", *(["--force"] if force else []),
                                str(worktree)], capture_output=True, text=True)
            if p.returncode == 0:
                return ""
            error = ((p.stderr or p.stdout or "").strip().splitlines() or [f"exit {p.returncode}"])[-1]
        elif force:
            try:
                shutil.rmtree(worktree)
            except OSError as exc:
                error = str(exc)
        else:
            return error or "not a registered worktree"
    git(["worktree", "prune"], main)
    return "" if not worktree.exists() else error


def cleanup(cfg, worktree: Path | None, branch: str, force: bool = False) -> Notes:
    """Remove the remote branch, worktree and local branch. Never fails: the work is on main
    (or, with `force`, the caller has decided to discard it)."""
    notes: Notes = []
    main = cfg.root
    # Remote first: `branch -d` checks the upstream, which lacks the merge commit.
    if ref_exists(main, f"refs/remotes/origin/{branch}") and \
            git(["push", "-q", "origin", "--delete", branch], main)[0] != 0:
        notes.append(("merge.kept_remote", {"branch": branch}))
    error = _remove_worktree(main, worktree, force) if worktree is not None else ""
    if error:
        notes.append(("merge.kept_worktree", {"wt": str(worktree), "error": error}))
    elif git(["branch", "-q", "-D" if force else "-d", branch], main)[0] != 0:
        notes.append(("merge.kept_branch", {"branch": branch}))
    return notes


def _merge(ctx: Ctx) -> Notes:
    _precheck(ctx)
    conflict = FlowError("merge.conflict", id=ctx.id, branch=ctx.branch)
    plan = next((p.read_text(encoding="utf-8", errors="replace")
                 for p in map(ctx.find, e2e.PLAN_FILES) if p is not None), "")
    notes = land(ctx.cfg, ctx.worktree, ctx.branch, ctx.id, conflict, plan, _tested(ctx))
    # The work is on main now: force past regression output, and clean up even if bookkeeping fails.
    try:
        flow.set_status(ctx, "passed")
        reviews.settle(ctx.review_path("merge"), ctx.cfg.locale)  # the merge answered every reject round
        notes += [(key, {}) for key in flow.commit(ctx, f"{ctx.id}: merged, pending-merge -> passed")]
    finally:
        notes += cleanup(ctx.cfg, ctx.worktree, ctx.branch, force=True)
    return notes


def discard(ctx: Ctx) -> Notes:
    """Remove a superseded ticket's worktree and branches, naming the tip so it can be recovered."""
    if not flow._is_git(ctx) or not ref_exists(ctx.main, f"refs/heads/{ctx.branch}"):
        return []
    sha = git(["rev-parse", "--short", ctx.branch], ctx.main)[1]
    wt = next((p for p, b in worktrees(ctx.main) if b == ctx.branch), None)
    return [("merge.discarded", {"branch": ctx.branch, "sha": sha})] + cleanup(ctx.cfg, wt, ctx.branch, force=True)
