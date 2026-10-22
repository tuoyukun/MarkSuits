"""General mode: a change that belongs to no ticket (docs, prompts, config), on a throwaway lane.

`mark general new` cuts `chore/general-<stamp>` from main with its own worktree. The main
thread edits there (write scopes still keep code paths to coder-impl), commits, then
`mark general merge <branch>` lands it through the same regression and fast-forward as a
ticket and removes the lane. No ticket, no status, no subagents. A failed merge keeps the
lane, so the work and the regression log stay where the human can look. `mark general drop
<branch>` removes a lane that will not land; it refuses to discard work unless `--force`.
"""
from __future__ import annotations

import time
from pathlib import Path

from . import globs, merge
from .config import MarkConfig
from .flow import FlowError, provision
from .gitutil import current_branch, dirty_paths, git, has_remote, ref_exists, worktrees

PREFIX = "chore/general-"

Notes = list[tuple[str, dict]]


def _require_git(cfg: MarkConfig) -> None:
    if git(["rev-parse", "--git-dir"], cfg.root)[0] != 0:
        raise FlowError("merge.no_git")


def new(cfg: MarkConfig) -> tuple[str, Path, Notes]:
    """Create the lane branch from the latest main and its worktree, provisioned by `[worktree] setup`."""
    _require_git(cfg)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    branch = PREFIX + stamp
    wt = cfg.root / cfg.worktree_dir / f"general-{stamp}"
    base = cfg.main_branch
    if has_remote(cfg.root):
        git(["fetch", "-q", "origin", base], cfg.root)
        base = f"origin/{base}"
    if git(["branch", branch, base], cfg.root)[0] != 0:
        raise FlowError("flow.iso.branch_failed", branch=branch, base=base)
    if git(["worktree", "add", "-q", str(wt), branch], cfg.root)[0] != 0:
        git(["branch", "-q", "-D", branch], cfg.root)  # just created, no commits: safe
        raise FlowError("flow.iso.worktree_failed", wt=str(wt), branch=branch)
    try:
        notes = provision(cfg, wt, branch, f"general-{stamp}")
    except FlowError:
        git(["branch", "-q", "-D", branch], cfg.root)  # provision removed the worktree; no commits yet
        raise
    return branch, wt, notes


def merge_lane(cfg: MarkConfig, branch: str) -> Notes:
    _require_git(cfg)
    if not branch.startswith(PREFIX):
        raise FlowError("general.not_lane", branch=branch, prefix=PREFIX)
    wt = next((p for p, b in worktrees(cfg.root) if b == branch), None)
    if wt is None:
        raise FlowError("general.no_lane", branch=branch)
    on = current_branch(cfg.root)
    if on and on != cfg.main_branch:
        raise FlowError("flow.not_main", branch=on, main=cfg.main_branch)
    dirty = dirty_paths(wt, ".")
    if dirty:
        raise FlowError("general.dirty", wt=str(wt), files="\n".join(f"  - {p}" for p in dirty[:10]))
    if git(["rev-list", "--count", f"{cfg.main_branch}..{branch}"], cfg.root)[1] == "0":
        raise FlowError("general.empty", branch=branch)
    control = _control_files(cfg, branch)
    if control:
        raise FlowError("general.control", files="\n".join(f"  - {f}" for f in control))
    marked = _conflict_markers(cfg, branch)
    if marked:
        raise FlowError("general.markers", wt=str(wt), files="\n".join(f"  - {f}" for f in marked))
    conflict = FlowError("general.conflict", branch=branch, wt=str(wt))
    notes = merge.land(cfg, wt, branch, branch.removeprefix("chore/"), conflict)
    return notes + merge.cleanup(cfg, wt, branch)


def _control_files(cfg: MarkConfig, branch: str) -> list[str]:
    """Workflow state the lane changes: gates, ticket status, reviews, locks. Only the `mark` CLI
    writes those, on main; a lane carrying them would land a decision nobody made. Template
    copies (`.mark/.base/`) are fine: `mark upgrade` writes them in its lane."""
    from .guards.write import cli_only_globs
    rules = [g for g in cli_only_globs(cfg.state_rel) if not g.startswith(".mark/.base")]
    rules.append(f"{cfg.state_rel}/locks/**")
    out = git(["diff", "--name-only", "--no-renames", f"{cfg.main_branch}...{branch}"], cfg.root)[1]
    return [f for f in out.splitlines() if any(globs.match(g, f) for g in rules)]


def _conflict_markers(cfg: MarkConfig, branch: str) -> list[str]:
    """Files whose lines added on the lane include conflict markers (left by `mark upgrade`)."""
    out = git(["diff", "-U0", f"{cfg.main_branch}...{branch}"], cfg.root)[1]
    files: list[str] = []
    current = ""
    for line in out.splitlines():
        if line.startswith("+++ "):
            current = line[len("+++ b/"):]
        elif line.startswith(("+<<<<<<< ", "+>>>>>>> ")) and current not in files:
            files.append(current)
    return files


def drop(cfg: MarkConfig, branch: str, force: bool = False) -> Notes:
    """Remove a lane (worktree, local and remote branch) without landing it."""
    _require_git(cfg)
    if not branch.startswith(PREFIX):
        raise FlowError("general.not_lane", branch=branch, prefix=PREFIX)
    if not ref_exists(cfg.root, f"refs/heads/{branch}"):
        raise FlowError("general.no_branch", branch=branch)
    wt = next((p for p, b in worktrees(cfg.root) if b == branch), None)
    if not force:
        dirty = len(dirty_paths(wt, ".")) if wt else 0
        ahead = git(["rev-list", "--count", f"{cfg.main_branch}..{branch}"], cfg.root)[1] or "0"
        if dirty or ahead != "0":
            raise FlowError("general.unsaved", branch=branch, commits=ahead, files=dirty)
    return merge.cleanup(cfg, wt, branch, force=True)
