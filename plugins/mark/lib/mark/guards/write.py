"""Guards for file writes (PreToolUse: Edit | Write | MultiEdit | NotebookEdit)."""
from __future__ import annotations

from .. import budget, flow, globs, states, tickets
from ..config import MAIN
from ..gitutil import current_branch
from .common import Env, Location

STATUS_FILE = tickets.STATUS_FILENAME
TICKET_GATE = "ticket-approved"


def _file_path(env: Env) -> str:
    ti = env.tool_input
    return str(ti.get("file_path") or ti.get("notebook_path") or "")


def _located(env: Env) -> Location | None:
    fp = _file_path(env)
    if not fp:
        return None
    loc = env.locate(fp)
    return loc if loc.rel is not None else None


def builtin_rules(env: Env) -> list[tuple[str, frozenset[str]]]:
    """Invariants no project config can loosen: the workflow's own control files."""
    state = env.cfg.state_rel
    main_only = frozenset({MAIN})
    return [
        (".claude/**", main_only),
        (".mark/config.toml", main_only),
        (".mark/template.toml", main_only),
        (".mark/.base/**", frozenset()),             # pristine template copies: only `mark` writes them
        (f"{state}/locks/human/**", frozenset()),   # proof of human commands: nobody
        (f"{state}/gates/**", main_only),
        (f"{state}/locks/**", main_only),
        (f"{state}/features/*/{STATUS_FILE}", main_only),
        (f"{state}/bugs/*/{STATUS_FILE}", main_only),
        ("**/review-*.md", main_only),
    ]


def scope_guard(env: Env) -> str | None:
    """Role write scopes: first matching rule wins; unmatched paths are the main thread's."""
    loc = _located(env)
    return None if loc is None else scope_block(env, loc)


def scope_block(env: Env, loc: Location) -> str | None:
    """First matching rule wins. A path no rule assigns is the main thread's; pipeline roles
    may still keep working files in a ticket dir."""
    rules = builtin_rules(env) + [(r.glob, r.roles) for r in env.cfg.write_rules]
    for glob, roles in rules:
        if globs.match(glob, loc.rel):
            if env.who in roles:
                return None
            allowed = ", ".join(sorted(roles)) or "-"
            return env.t("guard.scope", who=env.who, rel=loc.rel, glob=glob, allowed=allowed)
    if env.role in env.cfg.roles and env.ticket_of_rel(loc.rel) is None:
        return env.t("guard.scope_unassigned", who=env.who, rel=loc.rel)
    return None


def worktree_guard(env: Env) -> str | None:
    """The main checkout is a state lane; real work happens in ticket worktrees."""
    loc = _located(env)
    return None if loc is None else worktree_block(env, loc)


def worktree_block(env: Env, loc: Location) -> str | None:
    if not env.is_git or loc.checkout is None or not loc.in_main:
        return None
    if env.role in env.cfg.roles:
        return env.t("guard.worktree.role", who=env.who, path=loc.path,
                     wt_dir=env.cfg.worktree_dir)
    state = env.cfg.state_rel
    lanes = [f"{state}/features/**", f"{state}/bugs/**", f"{state}/gates/**",
             f"{state}/locks/**", *env.cfg.main_writable]
    if any(globs.match(g, loc.rel) for g in lanes):
        return None
    return env.t("guard.worktree.main", rel=loc.rel, wt_dir=env.cfg.worktree_dir)


def ticket_guard(env: Env) -> str | None:
    """Opening a ticket is a human decision: no artifacts without `<id>.ticket-approved`."""
    loc = _located(env)
    hit = env.ticket_of_rel(loc.rel if loc else None)
    if hit is None:
        return None
    kind, ticket_id, name = hit
    if name == STATUS_FILE or env.has_gate(ticket_id, TICKET_GATE):
        return None
    gate = env.gate_path(ticket_id, TICKET_GATE).relative_to(env.main).as_posix()
    return env.t("guard.ticket", kind=kind, id=ticket_id, gate=gate)


def _new_text(env: Env, old: str | None) -> str | None:
    """Content the tool call would produce, or None if it cannot be predicted."""
    ti, tool = env.tool_input, env.ctx.tool_name
    if tool == "Write":
        return str(ti.get("content", ""))
    edits = ti.get("edits") if tool == "MultiEdit" else [ti] if tool == "Edit" else None
    if edits is None or old is None:
        return None
    text = old
    for e in edits:
        before, after = str(e.get("old_string", "")), str(e.get("new_string", ""))
        if not before or before not in text:
            return None  # the tool itself will reject this edit
        text = text.replace(before, after) if e.get("replace_all") else text.replace(before, after, 1)
    return text


def status_guard(env: Env) -> str | None:
    """status.md: main checkout on the main branch, valid content, legal move."""
    loc = _located(env)
    hit = env.ticket_of_rel(loc.rel if loc else None)
    if hit is None or hit[2] != STATUS_FILE:
        return None
    kind, ticket_id, _ = hit
    if env.is_git:
        if not loc.in_main:
            return env.t("guard.status.not_main", rel=loc.rel)
        branch = current_branch(env.main)
        if branch and branch != env.cfg.main_branch:
            return env.t("guard.status.branch", branch=branch, main=env.cfg.main_branch)

    try:
        old_text = loc.path.read_text(encoding="utf-8")
    except OSError:
        old_text = None
    new_text = _new_text(env, old_text)
    if new_text is None:
        return None
    fields, note = tickets.parse_status(new_text)
    ticket = tickets.Ticket(kind, ticket_id, loc.path, fields, note)
    problems = tickets.ticket_problems(ticket, loc.rel)
    if problems:
        listed = "\n".join("  - " + env.t(p.key, **p.params) for p in problems)
        return env.t("guard.status.invalid", problems=listed)

    old_fields = tickets.parse_status(old_text)[0] if old_text else {}
    old_status = old_fields.get("status", "")
    new_status = fields.get("status", "")
    if states.is_valid(kind, old_status) and not states.can_move(kind, old_status, new_status):
        allowed = ", ".join(sorted(states.TRANSITIONS[kind][old_status])) or "-"
        return env.t("guard.status.move", old=old_status, new=new_status, allowed=allowed)
    old_ticket = tickets.Ticket(kind, ticket_id, loc.path, old_fields)
    removed = sorted(set(flow.merge_after(old_ticket)) - set(flow.merge_after(ticket)))
    if removed:
        return env.t("guard.status.merge_after", refs=", ".join(removed), rel=loc.rel)
    if new_status == "passed" and old_status != "passed":
        blocked = flow.merge_blockers(env.cfg, ticket)
        if blocked:
            return env.t(blocked.key, **blocked.params)
    return None


def budget_guard(env: Env) -> str | None:
    """`[[doc_budget]]`: a write may not leave a budgeted doc over its limit and larger."""
    loc = _located(env)
    if loc is None or budget.limit_for(env.cfg, loc.rel) is None:
        return None
    try:
        old_text = loc.path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        old_text = None
    new_text = _new_text(env, old_text)
    if new_text is None:
        return None
    size = len(new_text.encode("utf-8"))
    old_size = len(old_text.encode("utf-8")) if old_text is not None else None
    limit = budget.overrun(env.cfg, loc.rel, size, old_size)
    if limit is None:
        return None
    return env.t("guard.budget", rel=loc.rel, size=size, limit=limit, cut=size - limit,
                 lines=budget.longest_lines(new_text))


PRE_WRITE = [scope_guard, worktree_guard, ticket_guard, status_guard, budget_guard]
