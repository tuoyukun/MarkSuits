"""Guards for subagent dispatch (PreToolUse: Agent | Task) and its lifecycle."""
from __future__ import annotations

from .. import tickets
from ..gitutil import (ahead_of, current_branch, dirty_paths, git, has_remote, is_ancestor,
                       patch_unique, ref_exists, worktrees)
from . import locks
from .common import Env, Target


def _pipeline_target(env: Env) -> Target | str | None:
    """Target for a pipeline dispatch; None for non-pipeline agents."""
    if env.dispatch_role not in env.cfg.roles:
        return None
    target = env.target()
    if target is None:
        return env.t("guard.target.missing", role=env.dispatch_role, state=env.cfg.state_rel)
    return target


def target_guard(env: Env) -> str | None:
    """Every pipeline dispatch names exactly one existing ticket."""
    target = _pipeline_target(env)
    if target is None or isinstance(target, str):
        return target
    if not env.ticket_dir(target).is_dir():
        return env.t("guard.target.unknown", kind=target.kind, id=target.id)
    return None


def gate_guard(env: Env) -> str | None:
    """Feature roles need their human review gate; the bug chain has none."""
    target = _pipeline_target(env)
    if not isinstance(target, Target) or target.kind == "bug":
        return None
    gate = env.cfg.gates.get(env.dispatch_role)
    if not gate or env.has_gate(target.id, gate):
        return None
    rel = env.gate_path(target.id, gate).relative_to(env.main).as_posix()
    return env.t("guard.gate", role=env.dispatch_role, id=target.id, gate=rel)


def _ticket_branches(env: Env) -> list[str]:
    code, out = git(["for-each-ref", "--format=%(refname:short)", "refs/heads/feature",
                     "refs/heads/bug"], env.main)
    return out.splitlines() if code == 0 else []


def branch_guard(env: Env) -> str | None:
    """Isolated worktree on `<kind>/<id>`, cut from main, backed up on origin."""
    target = _pipeline_target(env)
    if not isinstance(target, Target) or not env.is_git:
        return None
    branch = env.cfg.branch_for(target.kind, target.id)
    wt = env.cfg.worktree_for(target.kind, target.id)
    rows = worktrees(env.main)
    on_branch = [p for p, b in rows if b == branch]
    remote = has_remote(env.main)
    main_ref = f"origin/{env.cfg.main_branch}" if remote else env.cfg.main_branch
    if not on_branch:
        if ref_exists(env.main, f"refs/heads/{branch}"):
            return env.t("guard.branch.no_worktree", branch=branch, wt=wt)
        return env.t("guard.branch.missing", id=target.id, branch=branch, wt=wt, base=main_ref)
    if rows and on_branch[0] == rows[0][0]:
        return env.t("guard.branch.in_main", branch=branch, wt=wt)

    declared = tickets.load_ticket(env.cfg, target.kind, target.id).get("base-branch")
    for other in _ticket_branches(env):
        if other in (branch, declared):
            continue
        if is_ancestor(env.main, f"refs/heads/{other}", f"refs/heads/{branch}") and \
                patch_unique(env.main, main_ref, f"refs/heads/{other}"):
            return env.t("guard.branch.base", branch=branch, other=other, base=main_ref)

    if remote:
        if not ref_exists(env.main, f"refs/remotes/origin/{branch}"):
            return env.t("guard.branch.no_remote", branch=branch)
        unpushed = set(patch_unique(env.main, f"origin/{branch}", f"refs/heads/{branch}"))
        pending = [c for c in patch_unique(env.main, main_ref, f"refs/heads/{branch}") if c in unpushed]
        if pending:
            return env.t("guard.branch.unpushed", branch=branch, n=len(pending))
    return None


def status_commit_guard(env: Env) -> str | None:
    """Status changes on main are committed and pushed before the next dispatch."""
    target = _pipeline_target(env)
    if not isinstance(target, Target) or not env.is_git:
        return None
    if current_branch(env.main) != env.cfg.main_branch:
        return None
    rel = env.ticket_dir(target).relative_to(env.main).as_posix()
    dirty = dirty_paths(env.main, rel)
    if dirty:
        listed = "\n".join(f"  - {p}" for p in dirty[:10])
        return env.t("guard.commit.dirty", files=listed, dir=rel, id=target.id)
    main = env.cfg.main_branch
    if has_remote(env.main) and ahead_of(env.main, main, f"origin/{main}") > 0:
        return env.t("guard.commit.unpushed", main=main)
    return None


def dedup_guard(env: Env) -> str | None:
    """One live subagent per (ticket, role). Runs last: it creates the lock."""
    target = _pipeline_target(env)
    if not isinstance(target, Target):
        return None
    return locks.acquire(env, target, env.dispatch_role)


PRE_DISPATCH = [target_guard, gate_guard, branch_guard, status_commit_guard, dedup_guard]


def status_reminder(env: Env) -> str | None:
    """PostToolUse on writes: nudge to commit + push ticket state right away."""
    from .write import _located
    loc = _located(env)
    if loc is None or not env.is_git or not loc.in_main:
        return None
    hit = env.ticket_of_rel(loc.rel)
    if hit is None or current_branch(env.main) != env.cfg.main_branch:
        return None
    kind, ticket_id, _ = hit
    rel = env.ticket_dir(Target(kind, ticket_id)).relative_to(env.main).as_posix()
    if not dirty_paths(env.main, rel):
        return None
    return env.t("guard.commit.reminder", dir=rel, id=ticket_id, main=env.cfg.main_branch)
