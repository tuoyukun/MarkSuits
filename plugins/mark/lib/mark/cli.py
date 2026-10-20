"""`mark` command line: ticket claim and status view.

Exit codes: 0 ok, 1 check found problems or claim failed, 2 usage or setup error.
Commands always act on the main checkout, so they give the same answer from
any worktree.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TextIO

from . import states, tickets
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
        return t(loc, "status.empty")
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
    slug = None
    if "--slug" in args:
        i = args.index("--slug")
        if i + 1 >= len(args):
            err.write(t(cfg.locale, "cli.usage") + "\n")
            return 2
        slug = args[i + 1]
        args = args[:i] + args[i + 2:]
    if len(args) != 2 or args[0] not in states.KINDS or not args[1].strip():
        err.write(t(cfg.locale, "cli.usage") + "\n")
        return 2
    try:
        ticket = tickets.claim(cfg, args[0], args[1], slug=slug)
    except tickets.ClaimError as exc:
        reason = t(cfg.locale, exc.key, **exc.params)
        err.write(t(cfg.locale, "claim.failed", error=reason) + "\n")
        return 1
    except OSError as exc:
        err.write(t(cfg.locale, "claim.failed", error=exc) + "\n")
        return 1
    out.write(t(cfg.locale, "claim.ok", id=ticket.id) + "\n")
    return 0


def main(argv: list[str] | None = None, cwd: Path | None = None,
         out: TextIO | None = None, err: TextIO | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    out = out or sys.stdout
    err = err or sys.stderr
    if not argv or argv[0] in ("-h", "--help", "help"):
        out.write(t("en", "cli.usage") + "\n")
        return 0 if argv else 2
    cfg = _load(cwd or Path.cwd(), err)
    if cfg is None:
        return 2
    command, rest = argv[0], argv[1:]
    if command == "status":
        return cmd_status(cfg, rest, out)
    if command == "claim":
        return cmd_claim(cfg, rest, out, err)
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
