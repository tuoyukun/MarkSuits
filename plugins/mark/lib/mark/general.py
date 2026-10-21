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

from . import merge
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
    conflict = FlowError("general.conflict", branch=branch, wt=str(wt))
    notes = merge.land(cfg, wt, branch, branch.removeprefix("chore/"), conflict)
    return notes + merge.cleanup(cfg, wt, branch)


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
