"""Dispatch prompts: a project template filled with facts the engine has verified.

Subagents are stateless and start cold. Every fact the orchestrator already
knows (worktree, branch, which artifacts exist, what triggered this round)
goes into the prompt, so the subagent does not spend its first turns
rediscovering them.

Templates live in the project (`[paths] prompts`, default `.mark/prompts/`),
one file per scenario, e.g. `coder-impl-fix.md`:

    ---
    role: coder-impl
    outputs: handoff.md          (optional; overrides [outputs] for this scenario)
    ---
    You are the coder-impl for {{id}} ...
    {{brief}}

Placeholders are `{{name}}`; an unknown name is an error, so typos surface at
dispatch time instead of reaching a subagent. The engine always prepends the
`mark:ticket` anchor (and `mark:outputs` when the template overrides outputs).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass

from . import states
from .flow import Action, Ctx, FlowError
from .i18n import t

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
_FIELD_RE = re.compile(r"^([a-z_]+):\s*(.*)$")


@dataclass
class Template:
    role: str
    outputs: list[str] | None
    body: str


def parse_template(text: str) -> Template:
    fields: dict[str, str] = {}
    body = text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].splitlines():
                m = _FIELD_RE.match(line.strip())
                if m:
                    fields[m.group(1)] = m.group(2).strip()
            body = text[end + 4:].lstrip("\n")
    outputs = [f.strip() for f in fields["outputs"].split(",") if f.strip()] if "outputs" in fields else None
    return Template(fields.get("role", ""), outputs, body)


def load_template(ctx: Ctx, scenario: str) -> Template:
    path = ctx.cfg.prompts_dir / f"{scenario}.md"
    try:
        return parse_template(path.read_text(encoding="utf-8"))
    except OSError:
        rel = path.relative_to(ctx.main).as_posix() if path.is_relative_to(ctx.main) else str(path)
        raise FlowError("brief.no_template", path=rel, scenario=scenario) from None


def _listing(directory, skip: tuple[str, ...] = ()) -> str:
    try:
        names = sorted(n for n in os.listdir(directory) if not n.startswith(".") and n not in skip)
    except OSError:
        return ""
    return ", ".join(names)


def facts(ctx: Ctx, action: Action, outputs: list[str], prev: str, trigger: str) -> str:
    loc = ctx.cfg.locale
    none = t(loc, "brief.none")
    lines = [
        t(loc, "brief.title"),
        t(loc, "brief.worktree", wt=ctx.worktree),
        t(loc, "brief.branch", branch=ctx.branch),
        t(loc, "brief.work_dir", dir=ctx.work_dir, files=_listing(ctx.work_dir, ("status.md",)) or none),
        t(loc, "brief.state_dir", dir=ctx.state_dir, files=_listing(ctx.state_dir) or none),
        t(loc, "brief.outputs", files=", ".join(str(ctx.work_dir / f) for f in outputs) or none),
        t(loc, "brief.trigger", trigger=trigger or t(loc, "brief.first")),
        t(loc, "brief.prev", prev=prev or t(loc, "brief.no_prev")),
    ]
    if action.review:
        lines.append(t(loc, "brief.review", file=action.review,
                       rounds=", ".join(str(n) for n in action.pending_rounds),
                       refs=", ".join(action.pending_refs)))
    return "\n".join(lines)


def render(ctx: Ctx, action: Action, prev: str = "", trigger: str = "") -> str:
    if action.kind != "dispatch" or not action.scenario or not action.role:
        raise FlowError("brief.not_dispatch", id=ctx.id, kind=action.kind)
    tpl = load_template(ctx, action.scenario)
    if tpl.role != action.role:
        raise FlowError("brief.role_mismatch", scenario=action.scenario, got=tpl.role or "-",
                        want=action.role)
    outputs = tpl.outputs if tpl.outputs is not None else ctx.cfg.outputs.get(action.role, [])
    trigger = trigger or action.trigger
    values = {
        "id": ctx.id, "kind": ctx.kind, "desc": ctx.ticket.get("desc"), "status": ctx.ticket.status,
        "role": action.role, "scenario": action.scenario,
        "worktree": str(ctx.worktree), "branch": ctx.branch,
        "ticket_dir": str(ctx.work_dir), "state_ticket_dir": str(ctx.state_dir),
        "outputs": ", ".join(outputs), "trigger": trigger, "prev": prev,
        "review_file": action.review or "",
        "pending_rounds": ", ".join(str(n) for n in action.pending_rounds),
        "pending_refs": ", ".join(action.pending_refs),
        "brief": facts(ctx, action, outputs, prev, trigger),
    }
    unknown = sorted({m for m in _PLACEHOLDER_RE.findall(tpl.body) if m not in values})
    if unknown:
        raise FlowError("brief.unknown_placeholder", scenario=action.scenario, names=", ".join(unknown))
    body = _PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], tpl.body)
    if not re.search(r"\{\{\s*brief\s*\}\}", tpl.body):
        body = values["brief"] + "\n\n" + body
    head = [f"<!-- mark:ticket {states.KIND_DIRS[ctx.kind]}/{ctx.id} -->"]
    if tpl.outputs is not None:
        head.append(f"<!-- mark:outputs {','.join(outputs) or '-'} -->")
    return "\n".join(head) + "\n\n" + body.rstrip() + "\n"

