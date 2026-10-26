"""Orchestration logic: what happens next for a ticket, and the moves that change it.

Everything here is deterministic, so the orchestration skills stay thin: the
orchestrator asks `mark next`, dispatches what `mark dispatch` prints, and
records the outcome with `mark set`. Human decisions go through `mark approve`
and `mark reject`, which need a token from a prompt a person typed (`human`).

Ticket state lives in the main checkout on the main branch. Role artifacts
live in the ticket's worktree, so lookups check the worktree first.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import globs, human, ports, reviews, states, tickets
from .config import MarkConfig
from .i18n import t as _msg
from .gitutil import current_branch, dirty_paths, git, has_remote, patch_unique, ref_exists, worktrees

TICKET_GATE = "ticket-approved"
REQUIRED_BRIEF = {states.FEATURE: "requirement.md", states.BUG: "bug.md"}
_QA_RE = re.compile(r"<!--\s*mark:qa\s+(passed|blocked)\s*-->")
_QA_ROUND_RE = re.compile(r"<!--\s*mark:qa-round\s+(\d+)\s*-->")
QA_MAX_ROUNDS = 2  # after this many blocked design-QA rounds the human decides


class FlowError(Exception):
    """A refused operation; `key` is an i18n message key."""

    def __init__(self, key: str, **params: object):
        super().__init__(key)
        self.key = key
        self.params = params


# --------------------------------------------------------------------------
# Ticket context
# --------------------------------------------------------------------------

@dataclass
class Ctx:
    cfg: MarkConfig
    ticket: tickets.Ticket

    @property
    def kind(self) -> str:
        return self.ticket.kind

    @property
    def id(self) -> str:
        return self.ticket.id

    @property
    def main(self) -> Path:
        return self.cfg.root

    @property
    def rel_dir(self) -> str:
        return f"{self.cfg.state_rel}/{states.KIND_DIRS[self.kind]}/{self.id}"

    @property
    def state_dir(self) -> Path:
        """Ticket dir in the main checkout: status, requirement, reviews, log."""
        return self.main / self.rel_dir

    @property
    def branch(self) -> str:
        return self.cfg.branch_for(self.kind, self.id)

    @property
    def worktree(self) -> Path:
        return self.main / self.cfg.worktree_for(self.kind, self.id)

    @property
    def work_dir(self) -> Path:
        """Ticket dir in the worktree: where role artifacts are written."""
        return self.worktree / self.rel_dir

    def find(self, name: str) -> Path | None:
        for d in (self.work_dir, self.state_dir):
            if (d / name).is_file():
                return d / name
        return None

    def gate_path(self, gate: str) -> Path:
        return self.cfg.state_dir / "gates" / f"{self.id}.{gate}"

    def has_gate(self, gate: str) -> bool:
        p = self.gate_path(gate)
        return p.exists() or p.with_name(p.name + ".waived").exists()

    def review_path(self, gate: str) -> Path:
        return self.state_dir / reviews.filename(gate)


def load(cfg: MarkConfig, ref: str) -> Ctx:
    """Resolve `0012`, `0012-login`, `b0003` or `features/0012-login` to a ticket."""
    ref = ref.strip().strip("/").rsplit("/", 1)[-1]
    hits: list[tuple[str, str]] = []
    for kind in states.KINDS:
        for name in tickets.ticket_dirs(cfg, kind):
            if name == ref:
                return Ctx(cfg, tickets.load_ticket(cfg, kind, name))
            if name.startswith(ref + "-"):
                hits.append((kind, name))
    if not hits:
        raise FlowError("flow.no_ticket", ref=ref)
    if len(hits) > 1:
        raise FlowError("flow.ambiguous", ref=ref, hits=", ".join(n for _, n in hits))
    return Ctx(cfg, tickets.load_ticket(cfg, *hits[0]))


# --------------------------------------------------------------------------
# Merge order (`merge-after`)
# --------------------------------------------------------------------------

def merge_after(ticket: tickets.Ticket) -> list[str]:
    return tickets.parse_merge_after(ticket.get("merge-after") or "[]") or []


def _open_dep(cfg: MarkConfig, ref: str) -> tickets.Ticket | None:
    """The dependency if it still holds things up; None if done or unresolvable."""
    try:
        dep = load(cfg, ref).ticket
    except FlowError:
        return None
    return None if dep.status in states.TERMINAL else dep


def merge_cycle(cfg: MarkConfig, ticket: tickets.Ticket) -> list[str] | None:
    """`[A, B, A]` if unfinished `merge-after` links lead back to a ticket."""
    path: list[str] = []
    done: set[str] = set()

    def dfs(node: tickets.Ticket) -> list[str] | None:
        if node.id in path:
            return path[path.index(node.id):] + [node.id]
        if node.id in done:
            return None
        path.append(node.id)
        for ref in merge_after(node):
            dep = _open_dep(cfg, ref)
            found = dep and dfs(dep)
            if found:
                return found
        path.pop()
        done.add(node.id)
        return None

    return dfs(ticket)


def merge_blockers(cfg: MarkConfig, ticket: tickets.Ticket) -> FlowError | None:
    """Why `ticket` may not land yet. `passed` and `superseded` both satisfy `merge-after`."""
    cycle = merge_cycle(cfg, ticket)
    if cycle:
        return FlowError("merge.cycle", id=ticket.id, cycle=" -> ".join(cycle))
    waiting = []
    for ref in merge_after(ticket):
        try:
            dep = load(cfg, ref).ticket
        except FlowError as exc:   # unknown or ambiguous: never guess, block
            waiting.append(f"{ref} ({_msg(cfg.locale, exc.key, **exc.params)})")
            continue
        if dep.status not in states.TERMINAL:
            waiting.append(f"{dep.id} ({dep.status})")
    if waiting:
        return FlowError("merge.waiting", id=ticket.id, deps=", ".join(waiting))
    return None


def _today() -> str:
    return _dt.date.today().isoformat()


# --------------------------------------------------------------------------
# Locks and results written by the guards
# --------------------------------------------------------------------------

def _locks(ctx: Ctx) -> Path:
    return ctx.cfg.state_dir / "locks"


def running_roles(ctx: Ctx) -> list[str]:
    """Roles with a live lock. An unbound lock past the ghost window is a dispatch that never
    started (the dispatch guard reclaims it), so it does not count."""
    from .guards.locks import GHOST_SECONDS, read_lock
    try:
        paths = sorted(_locks(ctx).iterdir())
    except OSError:
        return []
    prefix, now = ctx.id + ".", time.time()
    roles = []
    for path in paths:
        if not (path.name.startswith(prefix) and path.name.endswith(".lock")):
            continue
        meta = read_lock(path)
        if not meta.get("agent_id") and now - float(meta.get("created", path.stat().st_mtime)) > GHOST_SECONDS:
            continue
        roles.append(path.name[len(prefix):-len(".lock")])
    return roles


def last_result(ctx: Ctx, role: str) -> dict | None:
    """The role's latest SubagentStop result, if newer than the last status change."""
    path = _locks(ctx) / f"{ctx.id}.{role}.result.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = ctx.ticket.path.stat().st_mtime
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or float(data.get("at", 0)) <= changed:
        return None
    return data


def previous_conclusion(ctx: Ctx) -> str:
    """Final report of the ticket's most recently finished agent, any role ("" if none)."""
    best: tuple[float, str] = (0.0, "")
    for path in _locks(ctx).glob(f"{ctx.id}.*.result.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and float(data.get("at", 0)) > best[0]:
            best = (float(data.get("at", 0)), str(data.get("conclusion") or ""))
    return best[1]


# --------------------------------------------------------------------------
# Next action
# --------------------------------------------------------------------------

@dataclass
class Action:
    kind: str                         # dispatch | record | merge | wait | stop | done
    message: str = ""                 # i18n key
    params: dict = field(default_factory=dict)
    role: str | None = None
    scenario: str | None = None       # prompt template name
    trigger: str = ""                 # what this dispatch responds to
    review: str | None = None         # review file with pending rounds
    pending_rounds: list[int] = field(default_factory=list)
    pending_refs: list[str] = field(default_factory=list)
    options: list[str] = field(default_factory=list)   # record: statuses to choose from

    def as_dict(self) -> dict:
        return asdict(self)


def _refs(path: Path | None, prefix: str) -> list[str]:
    if path is None:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    found = re.findall(rf"\b{prefix}-\d+\b", text)
    return sorted(set(found), key=lambda r: int(r.split("-")[1]))


def qa_result(ctx: Ctx) -> str | None:
    path = ctx.find("design-qa.md")
    if path is None:
        return None
    m = _QA_RE.findall(path.read_text(encoding="utf-8"))
    return m[-1] if m else None


def qa_round(ctx: Ctx) -> int:
    path = ctx.find("design-qa.md")
    if path is None:
        return 0
    rounds = _QA_ROUND_RE.findall(path.read_text(encoding="utf-8"))
    return max(map(int, rounds), default=1)


def _with_review(action: Action, ctx: Ctx, gates: tuple[str, ...]) -> bool:
    """Attach the first review file that has pending rounds; True if found."""
    for gate in gates:
        path = ctx.review_path(gate)
        rounds = reviews.pending(path)
        if rounds:
            action.review = str(path)
            action.pending_rounds = [r.number for r in rounds]
            action.pending_refs = [ref for r in rounds for ref in r.refs]
            action.trigger = f"{', '.join(action.pending_refs)} ({path.name})"
            return True
    return False


def _failure_trigger(ctx: Ctx) -> str:
    if qa_result(ctx) == "blocked":
        refs = _refs(ctx.find("design-qa.md"), "D")
        return f"{', '.join(refs) or 'D-?'} (design-qa.md)"
    refs = _refs(ctx.find("verdict.md"), "FAIL")
    return f"{', '.join(refs) or 'FAIL-?'} (verdict.md)"


# Every prompt template `_dispatch` can ask for, with the role it must declare.
# The project template ships one file per entry (`[paths] prompts/<scenario>.md`).
SCENARIOS: dict[str, str] = {
    "designer-initial": "designer",
    "designer-review-rework": "designer",
    "designer-rework": "designer",
    "designer-integration-qa": "designer",
    "designer-bugfix": "designer",
    "coder-plan": "coder-plan",
    "coder-plan-rework": "coder-plan",
    "fix-plan-initial": "fix-plan",
    "fix-plan-rework": "fix-plan",
    "coder-impl": "coder-impl",
    "coder-impl-fix": "coder-impl",
    "coder-impl-merge-rework": "coder-impl",
    "tester-initial": "tester",
    "tester-reverify": "tester",
}


def _dispatch(ctx: Ctx, status: str) -> Action:
    kind = ctx.kind
    role = states.ROLE_FOR_STATUS[kind][status]
    a = Action("dispatch", role=role, message="next.dispatch")
    if status == "designing" and kind == states.BUG:
        a.scenario = "designer-bugfix"
        if ctx.find("verdict.md"):
            a.trigger = _failure_trigger(ctx)
        else:
            a.trigger = "handoff.md (blocked-spec)" if ctx.find("handoff.md") else "fix-plan.md ([ui])"
    elif status == "designing":
        if _with_review(a, ctx, ("design",)):
            a.scenario = "designer-review-rework"
        elif ctx.find("verdict.md") or ctx.find("design-qa.md"):
            a.scenario, a.trigger = "designer-rework", _failure_trigger(ctx)
        else:
            a.scenario = "designer-initial"
    elif status == "planning" and kind == states.FEATURE:
        a.scenario = "coder-plan-rework" if _with_review(a, ctx, ("plan", "merge")) else "coder-plan"
    elif status == "planning":
        if _with_review(a, ctx, ("merge",)):
            a.scenario = "fix-plan-rework"
        elif ctx.find("fix-plan.md"):
            a.scenario, a.trigger = "fix-plan-rework", "handoff.md (blocked-plan)"
        else:
            a.scenario = "fix-plan-initial"
    elif status == "developing":
        a.scenario = "coder-impl"
    elif status == "design-qa":
        a.scenario = "designer-integration-qa"
    elif status == "testing":
        a.scenario = "tester-reverify" if ctx.find("verdict.md") else "tester-initial"
        if a.scenario == "tester-reverify":
            a.trigger = _failure_trigger(ctx)
    elif status == "failed-impl":
        if _with_review(a, ctx, ("merge",)):
            a.scenario = "coder-impl-merge-rework"
        else:
            a.scenario, a.trigger = "coder-impl-fix", _failure_trigger(ctx)
    a.params = {"role": role, "scenario": a.scenario, "id": ctx.id}
    return a


_STOP_KEYS = {
    "drafting": "next.drafting", "review-requirement": "next.review_requirement",
    "review-design": "next.review", "review-plan": "next.review",
    "blocked-spec": "next.blocked_spec",
    "blocked-plan": "next.blocked_plan", "blocked-unclear": "next.blocked_unclear",
}


def preview_note(ctx: Ctx) -> str:
    """Where the human opens the designer's preview at design review ("" if none)."""
    path = ctx.find("preview.html") if ctx.ticket.status == "review-design" else None
    return "\n" + _msg(ctx.cfg.locale, "next.preview", path=path) if path else ""


def next_action(ctx: Ctx, retry: bool = False) -> Action:
    t = ctx.ticket
    status, kind = t.status, t.kind
    base = {"id": ctx.id, "status": status}
    if not t.exists or not states.is_valid(kind, status):
        return Action("stop", "next.invalid", base)
    if status in states.TERMINAL:
        return Action("done", "next.done", base)
    if not ctx.has_gate(TICKET_GATE):
        return Action("stop", "next.ticket_gate", base)
    running = running_roles(ctx)
    if running:
        return Action("wait", "next.wait", {**base, "roles": ", ".join(running)}, role=running[0])
    if status == "pending-merge":
        blocked = merge_blockers(ctx.cfg, t)
        if blocked:
            return Action("stop", blocked.key, {**base, **blocked.params})
        failed = last_result(ctx, "merge")
        if failed:
            return Action("stop", "next.merge_failed", {**base, "reason": failed.get("reason", "")})
        return Action("merge", "next.merge", base)
    if status in _STOP_KEYS:
        return Action("stop", _STOP_KEYS[status], {**base, "preview": preview_note(ctx), "dir": ctx.rel_dir})

    action = _dispatch(ctx, status)
    first = ("designer-initial", "fix-plan-initial", "coder-plan" if _unstaffed(ctx, "designing") else "")
    if action.scenario in first:
        brief = REQUIRED_BRIEF[kind]
        if not (ctx.state_dir / brief).is_file():
            return Action("stop", "next.no_brief", {**base, "file": f"{ctx.rel_dir}/{brief}"})
    result = None if retry else last_result(ctx, action.role)
    if result is not None:
        options = sorted(states.TRANSITIONS[kind][status] - {"superseded"})
        params = {**base, "role": action.role, "options": " | ".join(options),
                  "reason": result.get("reason", ""), "wrapup": "", "route": ""}
        if action.role == "tester":
            params["route"] = _msg(ctx.cfg.locale, "next.record.route")
        if "pending-merge" in options:
            params["wrapup"] = _msg(ctx.cfg.locale, "next.record.wrapup", id=ctx.id)
        if result.get("result") == "PASSED":
            return Action("record", "next.record", params, role=action.role, options=options)
        return Action("stop", "next.output_failed", params, role=action.role)
    return action


# --------------------------------------------------------------------------
# Git: keep ticket state committed on main, set up worktrees
# --------------------------------------------------------------------------

def _require_main_branch(ctx: Ctx) -> None:
    branch = current_branch(ctx.main)
    if branch and branch != ctx.cfg.main_branch:
        raise FlowError("flow.not_main", branch=branch, main=ctx.cfg.main_branch)


def _is_git(ctx: Ctx) -> bool:
    return git(["rev-parse", "--git-dir"], ctx.main)[0] == 0


def commit(ctx: Ctx, message: str) -> list[str]:
    """Commit the ticket dir and its gates on main, then push. Returns notes (keys)."""
    if not _is_git(ctx):
        return []
    _require_main_branch(ctx)
    gates_dir = ctx.cfg.state_dir / "gates"
    paths = [ctx.rel_dir] if ctx.state_dir.is_dir() else []
    if gates_dir.is_dir():
        paths += [p.relative_to(ctx.main).as_posix() for p in sorted(gates_dir.glob(f"{ctx.id}.*"))]
    if not paths:
        return []
    git(["add", "-A", "--", *paths], ctx.main)
    if git(["diff", "--cached", "--quiet", "--", *paths], ctx.main)[0] == 0:
        return []
    code, _ = git(["commit", "-q", "-m", message, "--", *paths], ctx.main)
    if code != 0:
        raise FlowError("flow.commit_failed", paths=", ".join(paths))
    notes = ["flow.committed"]
    if has_remote(ctx.main):
        code, _ = git(["push", "-q", "origin", ctx.cfg.main_branch], ctx.main)
        notes.append("flow.pushed" if code == 0 else "flow.push_failed")
    return notes


SETUP_LOG_TAIL = 20


def provision(cfg: MarkConfig, wt: Path, branch: str, log_name: str) -> list[tuple[str, dict]]:
    """Run `[worktree] setup` in a worktree that was just created, then give it its ports.

    A worktree only has tracked files; the project's command adds what agents need
    (dependencies, `.env`, local config). It must exit 0 within the timeout and leave
    nothing git sees, or the new worktree is removed again: an agent never gets a
    half-provisioned checkout, and the next dispatch starts over. Ports are written after
    setup, so a setup that copies the main checkout's `.env` does not overwrite them.
    """
    notes = _run_setup(cfg, wt, branch, log_name) if cfg.worktree_setup else []
    if cfg.worktree_ports:
        try:
            got = ports.assign(cfg, wt)
        except ports.NoFreePorts:
            git(["worktree", "remove", "--force", str(wt)], cfg.root)
            raise FlowError("flow.iso.no_ports", slots=cfg.worktree_port_slots) from None
        notes.append(("flow.iso.ports", {"ports": ", ".join(f"{k}={v}" for k, v in got.items())}))
        dirty = dirty_paths(wt, ".")
        if dirty:
            git(["worktree", "remove", "--force", str(wt)], cfg.root)
            raise FlowError("flow.iso.ports_dirty", files="\n".join(f"  - {p}" for p in dirty[:10]))
    return notes


def _run_setup(cfg: MarkConfig, wt: Path, branch: str, log_name: str) -> list[tuple[str, dict]]:
    cmd = cfg.worktree_setup
    log = cfg.state_dir / "locks" / f"{log_name}.setup.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "MARK_MAIN_CHECKOUT": str(cfg.root), "MARK_BRANCH": branch}
    with log.open("w", encoding="utf-8") as fh:
        try:
            code = subprocess.run(cmd, shell=True, cwd=wt, env=env, stdout=fh, stderr=subprocess.STDOUT,
                                  timeout=cfg.worktree_setup_timeout).returncode
        # shortcut: a timeout kills the shell, not its children; use a process group if setups hang.
        except subprocess.TimeoutExpired:
            code = None
        except OSError as exc:
            fh.write(f"{exc}\n")
            code = 127
    dirty = dirty_paths(wt, ".") if code == 0 else []
    if code == 0 and not dirty:
        return [("flow.iso.setup", {"cmd": cmd})]
    git(["worktree", "remove", "--force", str(wt)], cfg.root)
    rel_log = log.relative_to(cfg.root).as_posix()
    if dirty:
        raise FlowError("flow.iso.setup_dirty", cmd=cmd, log=rel_log,
                        files="\n".join(f"  - {p}" for p in dirty[:10]))
    tail = "\n".join(log.read_text(encoding="utf-8", errors="replace").splitlines()[-SETUP_LOG_TAIL:])
    result = f"timeout {cfg.worktree_setup_timeout}s" if code is None else f"exit {code}"
    raise FlowError("flow.iso.setup_failed", cmd=cmd, result=result, log=rel_log, tail=tail)


def ensure_isolation(ctx: Ctx) -> list[tuple[str, dict]]:
    """Branch `<kind>/<id>` from main, its worktree, and its remote copy. Idempotent."""
    if not _is_git(ctx):
        return []
    done: list[tuple[str, dict]] = []
    rows = worktrees(ctx.main)
    if rows and rows[0][1] == ctx.branch:
        raise FlowError("flow.iso.in_main", branch=ctx.branch)
    remote = has_remote(ctx.main)
    main_branch = ctx.cfg.main_branch
    if not ref_exists(ctx.main, f"refs/heads/{ctx.branch}"):
        base = ctx.ticket.get("base-branch") or (f"origin/{main_branch}" if remote else main_branch)
        if remote:
            git(["fetch", "-q", "origin", main_branch], ctx.main)
        code, _ = git(["branch", ctx.branch, base], ctx.main)
        if code != 0:
            raise FlowError("flow.iso.branch_failed", branch=ctx.branch, base=base)
        done.append(("flow.iso.branch", {"branch": ctx.branch, "base": base}))
    if not any(b == ctx.branch for _, b in rows):
        code, _ = git(["worktree", "add", "-q", str(ctx.worktree), ctx.branch], ctx.main)
        if code != 0:
            raise FlowError("flow.iso.worktree_failed", wt=str(ctx.worktree), branch=ctx.branch)
        done.append(("flow.iso.worktree", {"wt": str(ctx.worktree)}))
        done += provision(ctx.cfg, ctx.worktree, ctx.branch, ctx.id)
    else:
        dirty = dirty_paths(ctx.worktree, ".")
        if dirty:
            listed = "\n".join(f"  - {p}" for p in dirty[:10])
            raise FlowError("flow.iso.dirty", wt=str(ctx.worktree), files=listed, id=ctx.id)
    if remote:
        code, _ = git(["push", "-q", "-u", "origin", ctx.branch], ctx.main)
        if code != 0:
            raise FlowError("flow.iso.push_failed", branch=ctx.branch)
    return done


# --------------------------------------------------------------------------
# Status moves
# --------------------------------------------------------------------------

def design_qa_needed(ctx: Ctx) -> bool:
    """Feature has a design and its branch touches the configured UI paths."""
    if ctx.kind != states.FEATURE or not ctx.cfg.design_qa_paths or ctx.find("design.md") is None:
        return False
    remote = has_remote(ctx.main)
    base = f"origin/{ctx.cfg.main_branch}" if remote else ctx.cfg.main_branch
    code, out = git(["diff", "--name-only", f"{base}...{ctx.branch}"], ctx.main)
    if code != 0:
        return False
    for path in out.splitlines():
        if any(globs.match(g, path) for g in ctx.cfg.design_qa_exclude):
            continue
        if any(globs.match(g, path) for g in ctx.cfg.design_qa_paths):
            return True
    return False


def _write_status(ctx: Ctx, new: str, note: str | None, extra: dict[str, str | None]) -> None:
    t = ctx.ticket
    fields = dict(t.fields)
    fields.update({"status": new, "owner": states.owner(ctx.kind, new), "updated": _today(),
                   "updater": "orchestrator", **extra})
    fields = {k: v for k, v in fields.items() if v is not None}  # None in `extra` drops a field
    body = t.note if note is None else " ".join(note.split())
    candidate = tickets.Ticket(ctx.kind, ctx.id, t.path, fields, body)
    problems = tickets.ticket_problems(candidate, ctx.rel_dir + "/status.md")
    if problems:
        raise FlowError("flow.invalid_status", problems=problems)
    t.path.write_text(tickets.format_status(fields, body), encoding="utf-8")
    ctx.ticket = candidate


def _unstaffed(ctx: Ctx, status: str) -> str | None:
    """The role a status needs when this project has no such role (no designer, say)."""
    role = states.ROLE_FOR_STATUS[ctx.kind].get(status)
    return role if role and role not in ctx.cfg.roles else None


def _move(ctx: Ctx, new: str, note: str | None, extra: dict[str, str | None] | None = None) -> str:
    old = ctx.ticket.status
    if (role := _unstaffed(ctx, new)) and new != old:
        raise FlowError("flow.no_role", new=new, role=role)
    if not states.can_move(ctx.kind, old, new):
        allowed = ", ".join(sorted(states.TRANSITIONS[ctx.kind].get(old, ()))) or "-"
        raise FlowError("flow.illegal", old=old, new=new, allowed=allowed)
    _write_status(ctx, new, note, extra or {})
    return old


AC_ANCHOR = "<!-- mark:ac -->"
OPEN_QUESTIONS_ANCHOR = "<!-- mark:open-questions -->"


def _section(text: str, anchor: str) -> str | None:
    """Text after `anchor` up to the next heading; None without the anchor."""
    at = text.find(anchor)
    if at < 0:
        return None
    return re.split(r"^#{1,6} ", text[at + len(anchor):], maxsplit=1, flags=re.M)[0]


def requirement_problems(path: Path | None) -> list[str]:
    """What keeps a requirement.md from human review: the file, an acceptance criterion,
    and an open-questions section that says only `none` (zh-CN: `无`)."""
    if path is None:
        return ["requirement.md"]
    text = path.read_text(encoding="utf-8")
    out = []
    ac = _section(text, AC_ANCHOR)
    if ac is None or not re.search(r"^\s*-\s*AC-\d+", ac, flags=re.M):
        out.append("AC-N")
    oq = _section(text, OPEN_QUESTIONS_ANCHOR)
    items = [] if oq is None else [ln.strip(" -*\t").lower() for ln in oq.splitlines()
                                   if ln.strip() and not ln.strip().startswith("<!--")]
    if oq is not None and items not in ([], ["none"], ["无"]):
        out.append("open-questions")
    return out


def set_status(ctx: Ctx, new: str, note: str | None = None, leftover: str | None = None,
               add_after: list[str] | None = None) -> str:
    """Orchestrator records an outcome. A status that waits on the human (review gates,
    `blocked-*`, `pending-merge`) is left only through `mark approve` / `mark reject` (human
    token) or `mark merge` (`passed`); `superseded` stays open to everyone."""
    if _is_git(ctx):
        _require_main_branch(ctx)
    old = ctx.ticket.status
    if old in states.HELD and new not in ("superseded", old) and not (old == states.MERGE and new == "passed"):
        raise FlowError("flow.human_gate", status=old, id=ctx.id)
    if new == "review-requirement" and old != new:
        missing = requirement_problems(ctx.find(REQUIRED_BRIEF[states.FEATURE]))
        if missing:
            raise FlowError("flow.requirement_incomplete", id=ctx.id, missing=", ".join(missing))
    if new == "testing" and old == "design-qa" and qa_result(ctx) != "passed":
        raise FlowError("flow.qa_not_passed", id=ctx.id)
    if new == "testing" and old in ("developing", "failed-impl") and design_qa_needed(ctx) \
            and qa_result(ctx) != "passed":
        raise FlowError("flow.need_design_qa", id=ctx.id)
    if old == "testing" and new == states.MERGE:
        # The verdict on disk may be last round's PASSED; only a tester run since this status counts.
        result = last_result(ctx, "tester")
        if not result or result.get("result") != "PASSED":
            raise FlowError("flow.no_tester_result", id=ctx.id)
    if old == "design-qa" and new == "failed-impl" and (n := qa_round(ctx)) >= QA_MAX_ROUNDS:
        raise FlowError("flow.qa_cap", id=ctx.id, n=n)
    if add_after:
        # Declaring a dependency is free; removing one is a human edit (no tool call writes status.md).
        bad = [r for r in add_after if tickets.parse_merge_after(f"[{r}]") is None]
        if bad:
            raise FlowError("flow.bad_merge_after", refs=", ".join(bad))
        refs = merge_after(ctx.ticket)
        refs += [r for r in add_after if r not in refs]
    if new == "passed":
        blocked = merge_blockers(ctx.cfg, ctx.ticket)
        if blocked:
            raise blocked
    if new == "passed" and _is_git(ctx) and ref_exists(ctx.main, f"refs/heads/{ctx.branch}"):
        unmerged = patch_unique(ctx.main, ctx.cfg.main_branch, f"refs/heads/{ctx.branch}")
        if unmerged:
            raise FlowError("flow.unmerged", branch=ctx.branch, n=len(unmerged), main=ctx.cfg.main_branch)
    extra = {"leftover": str(leftover)} if leftover is not None else {}
    if add_after:
        extra["merge-after"] = f"[{', '.join(refs)}]"
    return _move(ctx, new, note, extra)


# --------------------------------------------------------------------------
# Human decisions
# --------------------------------------------------------------------------

def _require_human(ctx: Ctx, verb: str, word: str | None = None) -> None:
    if not human.consume(ctx.cfg, (verb,), ctx.id, word=word):
        if word:
            raise FlowError("flow.no_human_to", id=ctx.id, to=word)
        raise FlowError("flow.no_human", verb=verb, id=ctx.id)


def _write_gate(ctx: Ctx, gate: str) -> Path:
    path = ctx.gate_path(gate)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    path.write_text(f"approved_at: {stamp}\napproved_by: human\ngate: {gate}\n", encoding="utf-8")
    return path


APPROVE = {
    # status: (gate written, review settled, default next status; None: the human must name one)
    "review-requirement": ("requirement-approved", "requirement", "designing"),
    "review-design": ("design-approved", "design", "planning"),
    "review-plan": ("plan-approved", "plan", "developing"),
    "blocked-spec": (None, None, "designing"),
    "blocked-plan": (None, None, "planning"),
    "blocked-unclear": (None, None, None),
}


@dataclass
class Outcome:
    old: str
    new: str
    gate: str | None = None
    rounds: list[int] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)
    review: str | None = None
    ui_only: bool = False


REWORK_BASE = "rework-base"
CONTRACT_ANCHORS = ("<!-- mark:props-contract -->", "<!-- mark:integration-contract -->")


def _contracts(text: str | None) -> list[str] | None:
    """The props and integration contract sections of a design.md; None if either anchor is missing."""
    if text is None:
        return None
    out = []
    for anchor in CONTRACT_ANCHORS:
        at = text.find(anchor)
        if at < 0:
            return None
        body = re.split(r"^#{1,2} ", text[at + len(anchor):], maxsplit=1, flags=re.M)[0]
        out.append(" ".join(body.split()))
    return out


def ui_only_rework(ctx: Ctx) -> bool:
    """A design rework since `rework-base` changed only the UI directory and ticket artifacts,
    and left the props and integration contracts as they were: the approved plan and the code
    around the UI still hold, so planning and implementation have nothing to redo."""
    base, ui = ctx.ticket.get(REWORK_BASE), ctx.cfg.path("ui")
    if not base or not ui or not _is_git(ctx):
        return False
    head = f"refs/heads/{ctx.branch}"
    code, out = git(["diff", "--name-only", f"{base}..{head}"], ctx.main)
    if code != 0:
        return False
    if any(not p.startswith((ui.rstrip("/") + "/", ctx.rel_dir + "/")) for p in out.splitlines()):
        return False
    design = f"{ctx.rel_dir}/design.md"
    before, after = (git(["show", f"{rev}:{design}"], ctx.main) for rev in (base, head))
    old = _contracts(before[1] if before[0] == 0 else None)
    return old is not None and old == _contracts(after[1] if after[0] == 0 else None)


def approve_targets(ctx: Ctx) -> list[str]:
    """Where `mark approve --to` may send a blocked ticket: its legal moves."""
    return sorted(s for s in states.TRANSITIONS[ctx.kind].get(ctx.ticket.status, frozenset())
                  if s != "superseded" and not _unstaffed(ctx, s))


def approve(ctx: Ctx, to: str | None = None) -> Outcome:
    """Human approval. A blocked ticket goes where the human said: `/mark:approve <id> <status>`
    puts the status in the token, and `to` must match it."""
    if _is_git(ctx):
        _require_main_branch(ctx)
    status = ctx.ticket.status
    if not ctx.has_gate(TICKET_GATE):
        if to:
            raise FlowError("flow.approve_to", id=ctx.id, status=status, to=to, allowed="-")
        _require_human(ctx, "approve")
        _write_gate(ctx, TICKET_GATE)
        return Outcome(status, status, gate=TICKET_GATE)
    if status not in APPROVE:
        raise FlowError("flow.approve_nothing", status=status, id=ctx.id)
    gate, review, new = APPROVE[status]
    if new and _unstaffed(ctx, new):
        new = "planning"  # no designer: the plan comes next, or is redone instead
    if to:
        if gate or to not in approve_targets(ctx):
            allowed = ", ".join(approve_targets(ctx)) if not gate else "-"
            raise FlowError("flow.approve_to", id=ctx.id, status=status, to=to, allowed=allowed)
        new = to
    if new is None:
        raise FlowError("flow.approve_need_to", id=ctx.id, status=status,
                        allowed=", ".join(approve_targets(ctx)))
    if not to and not gate:
        # The human named a status (`/mark:approve 0012 developing`): never take the default instead.
        named = [w for w in human.words(ctx.cfg, "approve", ctx.id) if w in approve_targets(ctx) and w != new]
        if named:
            raise FlowError("flow.approve_named", id=ctx.id, to=named[0])
    _require_human(ctx, "approve", word=to)
    extra: dict[str, str | None] = {}
    if status == "blocked-spec" and new == "designing" and ctx.kind == states.FEATURE \
            and ctx.has_gate("plan-approved") and _is_git(ctx):
        code, head = git(["rev-parse", f"refs/heads/{ctx.branch}"], ctx.main)
        extra[REWORK_BASE] = head.strip() if code == 0 else None
    ui_only = False
    if status == "review-design" and ctx.ticket.get(REWORK_BASE):
        ui_only = ui_only_rework(ctx)
        if ui_only:
            new = "design-qa" if design_qa_needed(ctx) else "testing"
        extra[REWORK_BASE] = None
    out = Outcome(status, new, gate=gate, ui_only=ui_only)
    if review:
        out.rounds = reviews.settle(ctx.review_path(review), ctx.cfg.locale)
    if gate:
        _write_gate(ctx, gate)
    _move(ctx, new, None, extra)
    return out


REJECT = {
    # status: (review file, default next status)
    "review-requirement": ("requirement", "drafting"),
    "review-design": ("design", "designing"),
    "review-plan": ("plan", "planning"),
    "pending-merge": ("merge", "failed-impl"),
}


def reject(ctx: Ctx, items: list[str], to: str | None = None) -> Outcome:
    if _is_git(ctx):
        _require_main_branch(ctx)
    status = ctx.ticket.status
    if status not in REJECT:
        raise FlowError("flow.reject_nothing", status=status, id=ctx.id)
    items = [i for i in (" ".join(x.split()) for x in items) if i]
    if not items:
        raise FlowError("flow.reject_empty")
    review, new = REJECT[status]
    if to:
        if status != "pending-merge" or to not in ("failed-impl", "planning"):
            raise FlowError("flow.reject_to", status=status, to=to)
        new = to
    _require_human(ctx, "reject")
    path = ctx.review_path(review)
    path.parent.mkdir(parents=True, exist_ok=True)
    n, refs = reviews.append_round(path, ctx.cfg.locale, ctx.id, review, items)
    _move(ctx, new, None)
    return Outcome(status, new, rounds=[n], refs=refs, review=str(path))


def open_ticket(cfg: MarkConfig, kind: str, desc: str, slug: str | None = None) -> tuple[tickets.Ticket, bool]:
    """Claim a number; approve the opening if a human typed /mark:feature or /mark:fix."""
    ticket = tickets.claim(cfg, kind, desc, slug=slug)
    verb = "feature" if kind == states.FEATURE else "fix"
    approved = human.consume(cfg, (verb,))
    if approved:
        ctx = Ctx(cfg, ticket)
        _write_gate(ctx, TICKET_GATE)
    return ticket, approved
