"""`mark` command line: tickets, status view, and the orchestration steps.

Exit codes: 0 ok, 1 refused (check failed, illegal move, missing approval...), 2 usage or setup error.
Commands always act on the main checkout, so they give the same answer from
any worktree.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import TextIO

from . import brief, flow, general, merge, states, tickets
from .config import ConfigError, MarkConfig, find_project_root, load_config
from .i18n import t


def _load(cwd: Path, err: TextIO) -> MarkConfig | None:
    root = find_project_root(cwd)
    if root is None:
        err.write(t("en", "cli.not_project", cwd=cwd) + "\n")
        return None
    try:
        cfg = load_config(tickets.main_root(root))
    except ConfigError as exc:
        err.write(t("en", "cli.config_error", error=exc) + "\n")
        return None
    return cfg


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def render(cfg: MarkConfig, items: list[tickets.Ticket], active_only: bool = False) -> str:
    loc = cfg.locale
    if not items:
        return t(loc, "status.empty") + "\n"
    groups: dict[str, list[tickets.Ticket]] = {"human": [], "agent": [], "unknown": [], "terminal": []}
    for item in items:
        groups[item.side].append(item)

    leftovers = [int(i.get("leftover")) for i in items if i.get("leftover").isdigit()]
    owed = [n for n in leftovers if n > 0]
    out = [
        t(loc, "status.title"), "",
        t(loc, "status.summary", total=len(items), human=len(groups["human"]),
          agent=len(groups["agent"]), done=len(groups["terminal"])),
        t(loc, "status.source"),
    ]
    if owed:
        out.append(t(loc, "status.leftover", total=sum(owed), tickets=len(owed)))
    out.append("")

    sections = [("human", "status.sec.human"), ("agent", "status.sec.agent"),
                ("unknown", "status.sec.unknown")]
    if not active_only:
        sections.append(("terminal", "status.sec.done"))
    for group, title_key in sections:
        rows = groups[group]
        if not rows:
            continue
        out += [f"## {t(loc, title_key)} ({len(rows)})", "", t(loc, "status.head"),
                "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |"]
        for i in rows:
            link = f"{states.KIND_DIRS[i.kind]}/{i.id}/"
            out.append(
                f"| [{i.id}]({link}) | {i.kind} | {_cell(i.get('desc'))} | `{i.status or '-'}` | "
                f"{i.get('owner') or '-'} | {i.get('updated') or '-'} | {_cell(i.note)} |"
            )
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def cmd_status(cfg: MarkConfig, args: list[str], out: TextIO) -> int:
    if "--check" in args:
        problems = tickets.check(cfg)
        if problems:
            out.write(t(cfg.locale, "check.failed") + "\n\n")
            for p in problems:
                out.write("  - " + t(cfg.locale, p.key, **p.params) + "\n")
            return 1
        out.write(t(cfg.locale, "check.ok", n=len(tickets.all_tickets(cfg))) + "\n")
        return 0
    items = tickets.all_tickets(cfg)
    if "--json" in args:
        out.write(json.dumps([i.as_dict() for i in items], ensure_ascii=False, indent=2) + "\n")
        return 0
    out.write(render(cfg, items, active_only="--active" in args))
    return 0


def cmd_claim(cfg: MarkConfig, args: list[str], out: TextIO, err: TextIO) -> int:
    opts, pos = _parse(args, {"--slug"})
    if opts is None or len(pos) != 2 or pos[0] not in states.KINDS or not pos[1].strip():
        err.write(t(cfg.locale, "cli.usage") + "\n")
        return 2
    try:
        ticket, approved = flow.open_ticket(cfg, pos[0], pos[1], slug=opts.get("--slug"))
    except tickets.ClaimError as exc:
        reason = t(cfg.locale, exc.key, **exc.params)
        err.write(t(cfg.locale, "claim.failed", error=reason) + "\n")
        return 1
    except OSError as exc:
        err.write(t(cfg.locale, "claim.failed", error=exc) + "\n")
        return 1
    out.write(t(cfg.locale, "claim.ok", id=ticket.id) + "\n")
    gate = f"{cfg.state_rel}/gates/{ticket.id}.{flow.TICKET_GATE}"
    verb = "feature" if pos[0] == states.FEATURE else "fix"
    note = t(cfg.locale, "claim.approved", verb=verb, gate=gate) if approved else \
        t(cfg.locale, "claim.unapproved", id=ticket.id)
    err.write(note + "\n")
    return 0


# --------------------------------------------------------------------------
# Orchestration commands
# --------------------------------------------------------------------------

_FLAGS = {"--json", "--retry", "--no-commit"}


def _parse(args: list[str], valued: set[str], multi: set[str] = frozenset()
           ) -> tuple[dict | None, list[str]]:
    """Tiny option parser: returns ({opt: value | [values] | True}, positionals); None on error."""
    opts: dict = {}
    pos: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in valued or a in multi:
            if i + 1 >= len(args):
                return None, pos
            if a in multi:
                opts.setdefault(a, []).append(args[i + 1])
            else:
                opts[a] = args[i + 1]
            i += 2
            continue
        if a in _FLAGS:
            opts[a] = True
        elif a.startswith("--"):
            return None, pos
        else:
            pos.append(a)
        i += 1
    return opts, pos


def _say(cfg: MarkConfig, stream: TextIO, key: str, **params: object) -> None:
    stream.write(t(cfg.locale, key, **params) + "\n")


def _fail(cfg: MarkConfig, err: TextIO, exc: flow.FlowError) -> int:
    params = dict(exc.params)
    if isinstance(params.get("problems"), list):
        params["problems"] = "\n".join("  - " + t(cfg.locale, p.key, **p.params) for p in params["problems"])
    _say(cfg, err, exc.key, **params)
    return 1


def _commit(cfg: MarkConfig, ctx: flow.Ctx, message: str, opts: dict, out: TextIO) -> int:
    if opts.get("--no-commit"):
        return 0
    notes = flow.commit(ctx, message)
    for key in notes:
        _say(cfg, out, key)
    return 1 if "flow.push_failed" in notes else 0


def cmd_next(cfg: MarkConfig, args: list[str], out: TextIO, err: TextIO) -> int:
    opts, pos = _parse(args, set())
    if opts is None or len(pos) != 1:
        _say(cfg, err, "cli.usage")
        return 2
    ctx = flow.load(cfg, pos[0])
    action = flow.next_action(ctx, retry=bool(opts.get("--retry")))
    if opts.get("--json"):
        data = {"id": ctx.id, "kind": ctx.kind, "status": ctx.ticket.status, **action.as_dict(),
                "text": t(cfg.locale, action.message, **action.params)}
        out.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    else:
        _say(cfg, out, action.message, **action.params)
    return 0


def cmd_dispatch(cfg: MarkConfig, args: list[str], out: TextIO, err: TextIO) -> int:
    opts, pos = _parse(args, {"--prev", "--trigger"})
    if opts is None or len(pos) != 1:
        _say(cfg, err, "cli.usage")
        return 2
    ctx = flow.load(cfg, pos[0])
    action = flow.next_action(ctx, retry=bool(opts.get("--retry")))
    if action.kind != "dispatch":
        _say(cfg, err, action.message, **action.params)
        return 1
    # Default: the previous agent's own final report, recorded at SubagentStop.
    prev = opts["--prev"] if "--prev" in opts else flow.previous_conclusion(ctx)
    trigger = opts.get("--trigger", "")
    brief.render(ctx, action, prev=prev, trigger=trigger)  # template errors before git side effects
    for key, params in flow.ensure_isolation(ctx):
        _say(cfg, err, key, **params)
    prompt = brief.render(ctx, action, prev=prev, trigger=trigger)
    out.write(f"subagent_type: {action.role}\n")
    out.write(f"description: {ctx.id} {action.scenario}\n")
    out.write("--- prompt ---\n")
    out.write(prompt)
    return 0


def cmd_set(cfg: MarkConfig, args: list[str], out: TextIO, err: TextIO) -> int:
    opts, pos = _parse(args, {"--note", "--leftover", "--merge-after"})
    if opts is None or len(pos) != 2:
        _say(cfg, err, "cli.usage")
        return 2
    ctx = flow.load(cfg, pos[0])
    after = [r for r in re.split(r"[\s,\[\]]+", opts.get("--merge-after", "")) if r and r != "none"]
    old = flow.set_status(ctx, pos[1], note=opts.get("--note"), leftover=opts.get("--leftover"),
                          add_after=after)
    _say(cfg, out, "set.done", id=ctx.id, old=old, new=pos[1])
    return _commit(cfg, ctx, f"{ctx.id}: {old} -> {pos[1]}", opts, out)


def cmd_approve(cfg: MarkConfig, args: list[str], out: TextIO, err: TextIO) -> int:
    opts, pos = _parse(args, set())
    if opts is None or len(pos) != 1:
        _say(cfg, err, "cli.usage")
        return 2
    ctx = flow.load(cfg, pos[0])
    res = flow.approve(ctx)
    if res.gate == flow.TICKET_GATE:
        _say(cfg, out, "approve.ticket", id=ctx.id, gate=f"{cfg.state_rel}/gates/{ctx.id}.{res.gate}")
        return _commit(cfg, ctx, f"{ctx.id}: opening approved", opts, out)
    _say(cfg, out, "approve.done", id=ctx.id, old=res.old, new=res.new)
    if res.gate:
        _say(cfg, out, "approve.gate", gate=f"{cfg.state_rel}/gates/{ctx.id}.{res.gate}")
    if res.rounds:
        _say(cfg, out, "approve.rounds", rounds=", ".join(map(str, res.rounds)))
    return _commit(cfg, ctx, f"{ctx.id}: approved {res.old} -> {res.new}", opts, out)


def cmd_reject(cfg: MarkConfig, args: list[str], out: TextIO, err: TextIO) -> int:
    opts, pos = _parse(args, {"--to"}, {"--item"})
    if opts is None or len(pos) != 1:
        _say(cfg, err, "cli.usage")
        return 2
    ctx = flow.load(cfg, pos[0])
    res = flow.reject(ctx, opts.get("--item", []), to=opts.get("--to"))
    rel = Path(res.review).relative_to(cfg.root).as_posix()
    _say(cfg, out, "reject.done", round=res.rounds[0], refs=", ".join(res.refs), file=rel,
         id=ctx.id, old=res.old, new=res.new)
    return _commit(cfg, ctx, f"{ctx.id}: rejected at {res.old} ({', '.join(res.refs)})", opts, out)


def cmd_commit(cfg: MarkConfig, args: list[str], out: TextIO, err: TextIO) -> int:
    opts, pos = _parse(args, {"-m"})
    if opts is None or len(pos) != 1:
        _say(cfg, err, "cli.usage")
        return 2
    ctx = flow.load(cfg, pos[0])
    return _commit(cfg, ctx, opts.get("-m") or f"{ctx.id}: update ticket state", {}, out)


def cmd_merge(cfg: MarkConfig, args: list[str], out: TextIO, err: TextIO) -> int:
    opts, pos = _parse(args, set())
    if opts is None or len(pos) != 1:
        _say(cfg, err, "cli.usage")
        return 2
    ctx = flow.load(cfg, pos[0])
    notes = merge.run(ctx)
    for key, params in notes:
        _say(cfg, out, key, **params)
    _say(cfg, out, "merge.done", id=ctx.id)
    return 1 if any(key == "flow.push_failed" for key, _ in notes) else 0


def cmd_general(cfg: MarkConfig, args: list[str], out: TextIO, err: TextIO) -> int:
    """`mark general new` | `merge <branch>` | `drop <branch> [--force]`: the no-ticket lane."""
    if args == ["new"]:
        branch, wt, notes = general.new(cfg)
        for key, params in notes:
            _say(cfg, out, key, **params)
        _say(cfg, out, "general.new", branch=branch, wt=wt)
        return 0
    if len(args) == 2 and args[0] == "merge":
        for key, params in general.merge_lane(cfg, args[1]):
            _say(cfg, out, key, **params)
        _say(cfg, out, "general.done", branch=args[1])
        return 0
    if len(args) in (2, 3) and args[0] == "drop" and args[2:] in ([], ["--force"]):
        for key, params in general.drop(cfg, args[1], force=args[2:] == ["--force"]):
            _say(cfg, out, key, **params)
        _say(cfg, out, "general.dropped", branch=args[1])
        return 0
    _say(cfg, err, "cli.usage")
    return 2


_PLUGIN = Path(__file__).resolve().parents[2]
RULES = {
    "orchestrator": _PLUGIN / "rules" / "orchestrator.md",
    "role": _PLUGIN / "skills" / "role-rules" / "SKILL.md",
}


def cmd_rules(args: list[str], out: TextIO, err: TextIO) -> int:
    """`mark rules [orchestrator|role]`: print a rulebook (frontmatter stripped)."""
    name = args[0] if args else "orchestrator"
    if name not in RULES or len(args) > 1:
        err.write(t("en", "cli.usage") + "\n")
        return 2
    text = RULES[name].read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:].lstrip("\n")
    out.write(text)
    return 0

COMMANDS = {"next": cmd_next, "dispatch": cmd_dispatch, "set": cmd_set, "approve": cmd_approve,
            "reject": cmd_reject, "commit": cmd_commit, "claim": cmd_claim, "merge": cmd_merge,
            "general": cmd_general}


def main(argv: list[str] | None = None, cwd: Path | None = None,
         out: TextIO | None = None, err: TextIO | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    out = out or sys.stdout
    err = err or sys.stderr
    if not argv or argv[0] in ("-h", "--help", "help"):
        out.write(t("en", "cli.usage") + "\n")
        return 0 if argv else 2
    if argv[0] == "rules":
        return cmd_rules(argv[1:], out, err)
    cfg = _load(cwd or Path.cwd(), err)
    if cfg is None:
        return 2
    command, rest = argv[0], argv[1:]
    if command == "status":
        return cmd_status(cfg, rest, out)
    if command in COMMANDS:
        try:
            return COMMANDS[command](cfg, rest, out, err)
        except flow.FlowError as exc:
            return _fail(cfg, err, exc)
    if command == "unlock" and len(rest) == 2:
        lock = cfg.state_dir / "locks" / f"{rest[0]}.{rest[1]}.lock"
        if not lock.exists():
            out.write(t(cfg.locale, "cli.unlock.none", id=rest[0], role=rest[1]) + "\n")
            return 1
        lock.unlink()
        out.write(t(cfg.locale, "cli.unlock.ok", id=rest[0], role=rest[1]) + "\n")
        return 0
    err.write(t(cfg.locale, "cli.usage") + "\n")
    return 2
