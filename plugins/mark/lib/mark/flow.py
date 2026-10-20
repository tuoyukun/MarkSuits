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
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import globs, human, reviews, states, tickets
from .config import MarkConfig
from .gitutil import current_branch, dirty_paths, git, has_remote, patch_unique, ref_exists, worktrees

TICKET_GATE = "ticket-approved"
REQUIRED_BRIEF = {states.FEATURE: "requirement.md", states.BUG: "bug.md"}
_QA_RE = re.compile(r"<!--\s*mark:qa\s+(passed|blocked)\s*-->")


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


def _today() -> str:
    return _dt.date.today().isoformat()


# --------------------------------------------------------------------------
# Locks and results written by the guards
# --------------------------------------------------------------------------

def _locks(ctx: Ctx) -> Path:
    return ctx.cfg.state_dir / "locks"


def running_roles(ctx: Ctx) -> list[str]:
    try:
        names = sorted(p.name for p in _locks(ctx).iterdir())
    except OSError:
        return []
    prefix = ctx.id + "."
    return [n[len(prefix):-len(".lock")] for n in names if n.startswith(prefix) and n.endswith(".lock")]


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


# --------------------------------------------------------------------------
# Next action
# --------------------------------------------------------------------------

@dataclass
class Action:
    kind: str                         # dispatch | record | wait | stop | done
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


def _dispatch(ctx: Ctx, status: str) -> Action:
    kind = ctx.kind
    role = states.ROLE_FOR_STATUS[kind][status]
    a = Action("dispatch", role=role, message="next.dispatch")
    if status == "designing":
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
    "review-design": "next.review", "review-plan": "next.review",
    "pending-merge": "next.merge", "blocked-spec": "next.blocked_spec",
    "blocked-plan": "next.blocked_plan", "blocked-unclear": "next.blocked_unclear",
}


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
    if status in _STOP_KEYS:
        return Action("stop", _STOP_KEYS[status], base)

    action = _dispatch(ctx, status)
    if action.scenario in ("designer-initial", "fix-plan-initial"):
        brief = REQUIRED_BRIEF[kind]
        if not (ctx.state_dir / brief).is_file():
            return Action("stop", "next.no_brief", {**base, "file": f"{ctx.rel_dir}/{brief}"})
    result = None if retry else last_result(ctx, action.role)
    if result is not None:
        options = sorted(states.TRANSITIONS[kind][status] - {"superseded"})
        params = {**base, "role": action.role, "options": " | ".join(options),
                  "reason": result.get("reason", "")}
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

def _owner(kind: str, status: str) -> str:
    if status in states.AGENT:
        return states.ROLE_FOR_STATUS[kind].get(status, "-")
    return "human" if status in states.HUMAN else "-"


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


def _write_status(ctx: Ctx, new: str, note: str | None, extra: dict[str, str]) -> None:
    t = ctx.ticket
    fields = dict(t.fields)
    fields.update({"status": new, "owner": _owner(ctx.kind, new), "updated": _today(),
                   "updater": "orchestrator", **extra})
    body = t.note if note is None else " ".join(note.split())
    candidate = tickets.Ticket(ctx.kind, ctx.id, t.path, fields, body)
    problems = tickets.ticket_problems(candidate, ctx.rel_dir + "/status.md")
    if problems:
        raise FlowError("flow.invalid_status", problems=problems)
    t.path.write_text(tickets.format_status(fields, body), encoding="utf-8")
    ctx.ticket = candidate


def _move(ctx: Ctx, new: str, note: str | None, extra: dict[str, str] | None = None) -> str:
    old = ctx.ticket.status
    if not states.can_move(ctx.kind, old, new):
        allowed = ", ".join(sorted(states.TRANSITIONS[ctx.kind].get(old, ()))) or "-"
        raise FlowError("flow.illegal", old=old, new=new, allowed=allowed)
    _write_status(ctx, new, note, extra or {})
    return old


def set_status(ctx: Ctx, new: str, note: str | None = None, leftover: str | None = None) -> str:
    """Orchestrator records an outcome. Human gates are not movable from here."""
    if _is_git(ctx):
        _require_main_branch(ctx)
    old = ctx.ticket.status
    if old in ("review-design", "review-plan") and new != "superseded":
        raise FlowError("flow.human_gate", status=old, id=ctx.id)
    if new == "testing" and old in ("developing", "failed-impl") and design_qa_needed(ctx) \
            and qa_result(ctx) != "passed":
        raise FlowError("flow.need_design_qa", id=ctx.id)
    if new == "passed" and _is_git(ctx) and ref_exists(ctx.main, f"refs/heads/{ctx.branch}"):
        unmerged = patch_unique(ctx.main, ctx.cfg.main_branch, f"refs/heads/{ctx.branch}")
        if unmerged:
            raise FlowError("flow.unmerged", branch=ctx.branch, n=len(unmerged), main=ctx.cfg.main_branch)
    extra = {"leftover": str(leftover)} if leftover is not None else {}
    return _move(ctx, new, note, extra)


# --------------------------------------------------------------------------
# Human decisions
# --------------------------------------------------------------------------

def _require_human(ctx: Ctx, verb: str) -> None:
    if not human.consume(ctx.cfg, (verb,), ctx.id):
        raise FlowError("flow.no_human", verb=verb, id=ctx.id)


def _write_gate(ctx: Ctx, gate: str) -> Path:
    path = ctx.gate_path(gate)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    path.write_text(f"approved_at: {stamp}\napproved_by: human\ngate: {gate}\n", encoding="utf-8")
    return path


APPROVE = {
    # status: (gate written, review settled, next status)
    "review-design": ("design-approved", "design", "planning"),
    "review-plan": ("plan-approved", "plan", "developing"),
    "blocked-spec": (None, None, "designing"),
    "blocked-plan": (None, None, "planning"),
}


@dataclass
class Outcome:
    old: str
    new: str
    gate: str | None = None
    rounds: list[int] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)
    review: str | None = None


def approve(ctx: Ctx) -> Outcome:
    if _is_git(ctx):
        _require_main_branch(ctx)
    status = ctx.ticket.status
    if not ctx.has_gate(TICKET_GATE):
        _require_human(ctx, "approve")
        _write_gate(ctx, TICKET_GATE)
        return Outcome(status, status, gate=TICKET_GATE)
    if status not in APPROVE or (ctx.kind == states.BUG and status == "blocked-spec"):
        raise FlowError("flow.approve_nothing", status=status, id=ctx.id)
    gate, review, new = APPROVE[status]
    _require_human(ctx, "approve")
    out = Outcome(status, new, gate=gate)
    if review:
        out.rounds = reviews.settle(ctx.review_path(review), ctx.cfg.locale)
    if gate:
        _write_gate(ctx, gate)
    _move(ctx, new, None)
    return out


REJECT = {
    # status: (review file, default next status)
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
