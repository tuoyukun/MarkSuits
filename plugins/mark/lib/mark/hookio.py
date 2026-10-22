"""Shared plumbing for hook entry points.

Contract every Mark hook follows:
- Read the JSON payload from stdin.
- Outside a Mark project: exit 0 silently.
- To block: print the reason to stderr and exit 2. Never use exit 1
  (it only warns and does not block).
- Unexpected engine errors fail open (exit 0) with a stderr note, except where
  a specific guard documents fail-closed behaviour.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Callable, NoReturn

from .config import ConfigError, MarkConfig, find_project_root, load_config

EXIT_ALLOW = 0
EXIT_BLOCK = 2


def normalize_agent_type(name: str | None) -> str | None:
    """Strip a plugin namespace: `mark:coder-impl` -> `coder-impl`.

    Role agents may live in the project's `.claude/agents/` (bare name) or in a
    plugin (prefixed name). Permission rules are keyed by the bare role name.
    """
    if not name:
        return None
    return name.rsplit(":", 1)[-1]


@dataclass(frozen=True)
class HookContext:
    payload: dict[str, Any]
    config: MarkConfig

    @property
    def event(self) -> str:
        return str(self.payload.get("hook_event_name", ""))

    @property
    def tool_name(self) -> str:
        return str(self.payload.get("tool_name", ""))

    @property
    def tool_input(self) -> dict[str, Any]:
        value = self.payload.get("tool_input")
        return value if isinstance(value, dict) else {}

    @property
    def agent_type(self) -> str | None:
        """Bare role name of the calling subagent; None for the main thread."""
        return normalize_agent_type(self.payload.get("agent_type"))


def block(message: str) -> NoReturn:
    print(f"[BLOCKED] {message}", file=sys.stderr)
    sys.exit(EXIT_BLOCK)


def allow() -> NoReturn:
    sys.exit(EXIT_ALLOW)


def read_payload(stream=None) -> dict[str, Any]:
    raw = (stream or sys.stdin).read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def run(handler: Callable[[HookContext], None], stream=None,
        on_config_error: Callable[[dict[str, Any], Any, ConfigError], None] | None = None) -> NoReturn:
    """Entry point wrapper: resolve the project, then hand off to `handler`.

    A broken config blocks, unless `on_config_error(payload, root, exc)` decides otherwise
    (returning allows)."""
    payload = read_payload(stream)
    root = find_project_root(payload.get("cwd"))
    if root is None:
        allow()
    try:
        config = load_config(root)
    except ConfigError as exc:
        if on_config_error is None:
            block(str(exc))
        on_config_error(payload, root, exc)
        allow()
    handler(HookContext(payload=payload, config=config))
    allow()
