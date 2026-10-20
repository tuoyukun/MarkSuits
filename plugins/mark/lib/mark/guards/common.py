"""Shared context for guards.

A guard is a function `(env) -> str | None`: it returns a block message, or
None to allow. Guards never exit or print; `mark.hooks` does that. This keeps
every guard testable as a plain function.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, Callable

from .. import states, tickets
from ..config import MAIN, ConfigError, MarkConfig, load_config
from ..gitutil import checkout_root, main_root
from ..hookio import HookContext
from ..i18n import t

Guard = Callable[["Env"], "str | None"]


@dataclass(frozen=True)
class Location:
    """Where a file path lands."""
    path: Path                 # absolute, symlinks resolved
    checkout: Path | None      # checkout root it belongs to (None: not in git)
    rel: str | None            # path relative to that checkout (or project root)
    in_main: bool              # lands in the main checkout


@dataclass(frozen=True)
class Target:
    """The ticket a dispatch is aimed at."""
    kind: str
    id: str

    @property
    def kind_dir(self) -> str:
        return states.KIND_DIRS[self.kind]


class Env:
    def __init__(self, ctx: HookContext):
        self.ctx = ctx

    # -- identity ----------------------------------------------------------
    @property
    def role(self) -> str | None:
        """Calling subagent's bare role; None for the main thread."""
        return self.ctx.agent_type

    @property
    def who(self) -> str:
        return self.role or MAIN

    @property
    def tool_input(self) -> dict[str, Any]:
        return self.ctx.tool_input

    def t(self, key: str, **params: object) -> str:
        return t(self.cfg.locale, key, **params)

    # -- project -----------------------------------------------------------
    @cached_property
    def main(self) -> Path:
        return main_root(self.ctx.config.root).resolve()

    @cached_property
    def cfg(self) -> MarkConfig:
        """Config of the main checkout (rules are global, worktrees may lag)."""
        if self.main == self.ctx.config.root.resolve():
            return self.ctx.config
        try:
            return load_config(self.main)
        except ConfigError:
            return self.ctx.config

    @cached_property
    def is_git(self) -> bool:
        return checkout_root(self.main) is not None

    @property
    def cwd(self) -> Path:
        return Path(self.ctx.payload.get("cwd") or self.main)

    # -- paths -------------------------------------------------------------
    def locate(self, file_path: str) -> Location:
        raw = file_path if os.path.isabs(file_path) else os.path.join(self.cwd, file_path)
        path = Path(os.path.realpath(raw))
        checkout = checkout_root(path) if self.is_git else None
        base = checkout or self.main
        try:
            rel = path.relative_to(base).as_posix()
        except ValueError:
            rel = None
        in_main = (checkout == self.main) if self.is_git else rel is not None
        return Location(path, checkout, rel, in_main)

    def ticket_of_rel(self, rel: str | None) -> tuple[str, str, str] | None:
        """`.mark/features/<id>/<file...>` -> (kind, id, file)."""
        if not rel:
            return None
        state = self.cfg.state_rel.split("/")
        parts = rel.split("/")
        n = len(state)
        if len(parts) < n + 3 or parts[:n] != state:
            return None
        kind = {v: k for k, v in states.KIND_DIRS.items()}.get(parts[n])
        if kind is None or parts[n + 1].startswith("."):
            return None
        return kind, parts[n + 1], "/".join(parts[n + 2:])

    def gate_path(self, ticket_id: str, gate: str) -> Path:
        return self.cfg.state_dir / "gates" / f"{ticket_id}.{gate}"

    def has_gate(self, ticket_id: str, gate: str) -> bool:
        """A gate passes if `<id>.<gate>` or the waiver `<id>.<gate>.waived` exists."""
        p = self.gate_path(ticket_id, gate)
        return p.exists() or p.with_name(p.name + ".waived").exists()

    def ticket_dir(self, target: Target) -> Path:
        return tickets.kind_dir(self.cfg, target.kind) / target.id

    # -- dispatch target ---------------------------------------------------
    @cached_property
    def dispatch_role(self) -> str | None:
        from ..hookio import normalize_agent_type
        return normalize_agent_type(self.tool_input.get("subagent_type"))

    def target(self) -> Target | str | None:
        """Ticket the dispatch prompt points at; a message string if ambiguous."""
        return extract_target(self, f"{self.tool_input.get('prompt', '')}\n"
                                    f"{self.tool_input.get('description', '')}")


_ANCHOR_RE = re.compile(r"mark:ticket[\s=:]+(features|bugs)/([A-Za-z0-9_-]+)")


def extract_target(env: Env, text: str) -> Target | str | None:
    """Find the target ticket in a dispatch prompt.

    Preferred: a language-neutral anchor `mark:ticket features/<id>` (prompt
    templates emit it, usually inside an HTML comment). Fallback: ticket dir
    paths `<state>/features/<id>/`. Any other path in the prompt is a
    reference, so anchors win when present. Several distinct targets, or a
    short id that matches several directories, is an error.
    """
    found = _ANCHOR_RE.findall(text)
    if not found:
        state = re.escape(env.cfg.state_rel)
        found = re.findall(rf"{state}/(features|bugs)/([A-Za-z0-9_-]+)", text)
    by_dir = {v: k for k, v in states.KIND_DIRS.items()}
    targets: set[Target] = set()
    for kind_dir, raw_id in found:
        kind = by_dir[kind_dir]
        resolved = canonical_id(env, kind, raw_id)
        if resolved is None:
            return env.t("guard.target.short_ambiguous", ref=raw_id)
        targets.add(Target(kind, resolved))
    if len(targets) > 1:
        listed = ", ".join(sorted(f"{x.kind_dir}/{x.id}" for x in targets))
        return env.t("guard.target.ambiguous", targets=listed)
    return next(iter(targets)) if targets else None


def canonical_id(env: Env, kind: str, raw_id: str) -> str | None:
    """`0012` -> `0012-login` when exactly one dir matches; None if several."""
    base = tickets.kind_dir(env.cfg, kind)
    if (base / raw_id).is_dir():
        return raw_id
    hits = [n for n in tickets.ticket_dirs(env.cfg, kind) if n.startswith(raw_id + "-")]
    if len(hits) > 1:
        return None
    return hits[0] if hits else raw_id


def first_block(env: Env, guards: list[Guard]) -> str | None:
    for guard in guards:
        message = guard(env)
        if message:
            return message
    return None
