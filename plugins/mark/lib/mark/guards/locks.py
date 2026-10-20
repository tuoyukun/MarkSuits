"""Dispatch locks: one live subagent per (ticket, role).

Lifecycle:
  PreToolUse  Agent  -> acquire(): create `<id>.<role>.lock` (O_EXCL) with required outputs
  PostToolUse Agent  -> bind():    record agent_id
  SubagentStop       -> verify():  check outputs, write result, release

Event order depends on how the agent runs. Background agents: PostToolUse
(binds agent_id) comes long before SubagentStop. Foreground agents:
SubagentStop comes first, so verify() falls back to the single unbound lock
of the stopping role, and the later bind() finds no lock and does nothing.

A lock without agent_id older than GHOST_SECONDS is a dispatch that never
started (another hook or the permission system rejected it) and is reclaimed.
A bound lock is never reclaimed by age: subagents can legitimately run for
hours. If a session died, a human releases it with `mark unlock`.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from ..gitutil import worktrees
from .common import Env, Target

GHOST_SECONDS = 90
_OUTPUTS_RE = re.compile(r"mark:outputs[\s=:]+([A-Za-z0-9_.,/-]+)")


def locks_dir(env: Env) -> Path:
    return env.cfg.state_dir / "locks"


def lock_path(env: Env, target: Target, role: str) -> Path:
    return locks_dir(env) / f"{target.id}.{role}.lock"


def read_lock(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def acquire(env: Env, target: Target, role: str) -> str | None:
    path = lock_path(env, target, role)
    path.parent.mkdir(parents=True, exist_ok=True)
    rel = path.relative_to(env.main).as_posix() if path.is_relative_to(env.main) else str(path)
    if path.exists():
        meta = read_lock(path)
        age = int(time.time() - float(meta.get("created", path.stat().st_mtime)))
        if not meta.get("agent_id"):
            if age <= GHOST_SECONDS:
                return env.t("guard.dedup.pending", role=role, id=target.id, age=age)
            path.unlink(missing_ok=True)
        else:
            return env.t("guard.dedup.running", role=role, id=target.id, age=age // 60,
                         agent=meta["agent_id"], lock=rel)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return env.t("guard.dedup.race", role=role, id=target.id)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"ticket": target.id, "kind": target.kind, "role": role,
                   "created": time.time(), "required": required_outputs(env, role)}, fh)
        fh.write("\n")
    return None


def required_outputs(env: Env, role: str) -> list[str]:
    """`mark:outputs a.md,b.md` in the prompt overrides the role default."""
    text = f"{env.tool_input.get('prompt', '')}\n{env.tool_input.get('description', '')}"
    m = _OUTPUTS_RE.search(text)
    if m:
        return [f for f in m.group(1).split(",") if f and f != "-"]
    return list(env.cfg.outputs.get(role, []))


def bind(env: Env) -> None:
    role = env.dispatch_role
    if role not in env.cfg.roles:
        return
    response = env.ctx.payload.get("tool_response")
    if not isinstance(response, dict):
        return
    agent_id = response.get("agentId") or response.get("agent_id")
    target = env.target()
    if not agent_id or not isinstance(target, Target):
        return
    path = lock_path(env, target, role)
    meta = read_lock(path)
    if not meta:
        return
    meta["agent_id"] = str(agent_id)
    _write(path, meta)


def _all_locks(env: Env) -> list[tuple[Path, dict]]:
    try:
        names = sorted(os.listdir(locks_dir(env)))
    except OSError:
        return []
    return [(locks_dir(env) / n, read_lock(locks_dir(env) / n)) for n in names if n.endswith(".lock")]


def find_for_stop(env: Env, agent_id: str, role: str | None) -> tuple[Path, dict] | None:
    """The lock bound to `agent_id`, else the only unbound lock of `role`."""
    rows = _all_locks(env)
    for path, meta in rows:
        if meta.get("agent_id") == agent_id:
            return path, meta
    unbound = [(p, m) for p, m in rows if not m.get("agent_id") and m.get("role") == role]
    if len(unbound) == 1:
        path, meta = unbound[0]
        meta["agent_id"] = agent_id
        return path, meta
    return None


def candidate_dirs(env: Env, meta: dict) -> list[Path]:
    """Ticket dir in the main checkout and in every worktree."""
    from .. import states
    rel = f"{env.cfg.state_rel}/{states.KIND_DIRS.get(meta.get('kind', ''), 'features')}/{meta.get('ticket', '')}"
    roots = [p for p, _ in worktrees(env.main)] if env.is_git else []
    if env.main not in roots:
        roots.insert(0, env.main)
    return [r / rel for r in roots]


def record(path: Path, agent_id: str, result: str, reason: str) -> None:
    result_path = path.with_name(path.name.removesuffix(".lock") + ".result.json")
    _write(result_path, {"agent_id": agent_id, "result": result, "reason": reason,
                         "at": time.time()})


def verify(env: Env) -> str | None:
    """SubagentStop. A message keeps the subagent running to fix its output."""
    agent_id = str(env.ctx.payload.get("agent_id") or "")
    found = find_for_stop(env, agent_id, env.role) if agent_id else None
    if found is None:
        return None
    path, meta = found
    required = [f for f in meta.get("required", []) if f]
    dirs = candidate_dirs(env, meta)
    if not required or any(all((d / f).is_file() for f in required) for d in dirs):
        record(path, agent_id, "PASSED", "outputs present")
        path.unlink(missing_ok=True)
        return None
    if env.ctx.payload.get("stop_hook_active"):
        # Already asked once; blocking again would loop. Release and report.
        record(path, agent_id, "FAILED", "missing outputs: " + ", ".join(required))
        path.unlink(missing_ok=True)
        return None
    _write(path, meta)  # keep the agent_id bound while it fixes its output
    primary = next((d for d in dirs if d.is_dir()), dirs[0])
    missing = "\n".join(f"  - {primary / f}" for f in required if not (primary / f).is_file())
    checked = "\n".join(f"  - {d}" for d in dirs[:6])
    return env.t("guard.output.missing", role=meta.get("role", "?"), missing=missing, checked=checked)


def release(env: Env, ticket_id: str, role: str) -> bool:
    path = locks_dir(env) / f"{ticket_id}.{role}.lock"
    if not path.exists():
        return False
    path.unlink()
    return True
