"""Guards for file writes (PreToolUse: Edit | Write | MultiEdit | NotebookEdit)."""
from __future__ import annotations

from pathlib import Path

from .. import budget, e2e, globs, states, tickets
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


def cli_only_rules(env: Env) -> list[str]:
    return cli_only_globs(env.cfg.state_rel)


def cli_only_globs(state: str) -> list[str]:
    """Files only the `mark` CLI writes (it runs as a Bash child process, which no hook sees).
    They record human decisions and ticket state, so no tool call may write them, the main
    thread's included: otherwise an orchestrator could approve its own gate."""
    return [
        ".mark/.base/**",                      # pristine template copies
        f"{state}/locks/human/**",             # proof of human commands
        f"{state}/gates/**",
        f"{state}/features/*/{STATUS_FILE}",
        f"{state}/bugs/*/{STATUS_FILE}",
        "**/review-*.md",
    ]


def builtin_rules(env: Env) -> list[tuple[str, frozenset[str]]]:
    """Invariants no project config can loosen: the workflow's own control files."""
    state = env.cfg.state_rel
    main_only = frozenset({MAIN})
    return [(glob, frozenset()) for glob in cli_only_rules(env)] + [
        (".claude/**", main_only),
        (".mark/config.toml", main_only),
        (".mark/template.toml", main_only),
        (f"{state}/locks/**", main_only),
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
            if not roles:
                return env.t("guard.scope_cli", rel=loc.rel)
            return env.t("guard.scope", who=env.who, rel=loc.rel, glob=glob, allowed=", ".join(sorted(roles)))
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


def _imported(spec: Path, text: str) -> list[str]:
    """Source of the local files a spec imports (helpers live there); unreadable ones are skipped."""
    out = []
    for rel in e2e.local_imports(text):
        base = spec.parent / rel
        for cand in (base, *(base.with_name(base.name + ext) for ext in (".ts", ".tsx", ".js", ".mjs")),
                     base / "index.ts", base / "index.js"):
            if cand.is_file():
                try:
                    out.append(cand.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError):
                    pass
                break
    return out


def _flows(loc, text: str) -> dict[str, str]:
    """{repo path: text} of the Maestro flows `text` runs, directly or further down."""
    root = loc.path.parents[len(loc.rel.split("/")) - 1]
    out: dict[str, str] = {}
    todo = e2e.flow_refs(loc.rel, text)
    while todo:
        rel = todo.pop()
        if rel in out or rel.startswith("../"):
            continue
        try:
            out[rel] = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        todo += e2e.flow_refs(rel, out[rel])
    return out


def e2e_guard(env: Env) -> str | None:
    """The tester's end-to-end tests stay black-box (`mark.e2e`)."""
    loc = _located(env)
    tests_dir = env.cfg.path("tests")
    if loc is None or env.role != "tester" or not tests_dir or not loc.rel.startswith(tests_dir + "/"):
        return None
    try:
        old_text = loc.path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        old_text = None
    new_text = _new_text(env, old_text)
    if new_text is None:
        return None
    profile = env.cfg.tests_profile
    found = e2e.problems(loc.rel, old_text, new_text, tests_dir, env.cfg.module_dirs, profile,
                         _flows(loc, new_text) if profile == "maestro" else _imported(loc.path, new_text))
    if not found:
        return None
    listed = "\n".join(f"  - {env.t(p.key)}: {p.where}" for p in found)
    return env.t("guard.e2e", rel=loc.rel, problems=listed)


def plan_text(cfg, checkout: Path, branch: str | None) -> str | None:
    """The e2e-plan source for a ticket branch (its tech-plan.md or fix-plan.md, "" when the
    plan is not written yet); None for any other branch."""
    for kind, kind_dir in states.KIND_DIRS.items():
        prefix = cfg.branch_for(kind, "")
        if branch and branch.startswith(prefix) and len(branch) > len(prefix):
            folder = checkout / cfg.state_rel / kind_dir / branch[len(prefix):]
            for name in e2e.PLAN_FILES:
                if (folder / name).is_file():
                    return (folder / name).read_text(encoding="utf-8", errors="replace")
            return ""
    return None


def journey_guard(env: Env) -> str | None:
    """A tester adds only the end-to-end tests the plan names as new; everything else extends
    an existing test."""
    loc = _located(env)
    tests_dir = env.cfg.path("tests")
    if (loc is None or env.role != "tester" or env.cfg.tests_profile == "none" or not tests_dir
            or not loc.rel.startswith(tests_dir + "/") or loc.checkout is None):
        return None
    plan = plan_text(env.cfg, loc.checkout, current_branch(loc.checkout))
    if plan is None:
        return None
    try:
        old_text = loc.path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        old_text = None
    new_text = _new_text(env, old_text)
    if new_text is None:
        return None
    profile = env.cfg.tests_profile
    elsewhere = set(e2e.suite(loc.checkout, tests_dir, profile, skip=loc.rel))
    allowed = e2e.planned_new(plan)
    extra = [title for title in e2e.added_tests(loc.rel, old_text, new_text, elsewhere, profile)
             if title not in allowed]
    if not extra:
        return None
    return env.t("guard.journey", rel=loc.rel, tests="\n".join(f"  - {x}" for x in extra),
                 planned=", ".join(sorted(allowed)) or "-",
                 index=f"{tests_dir}/{e2e.INDEX_FILE}")


PRE_WRITE = [scope_guard, worktree_guard, ticket_guard, budget_guard, e2e_guard,
             journey_guard]
