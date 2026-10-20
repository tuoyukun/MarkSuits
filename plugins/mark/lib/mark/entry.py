"""Hook wiring: map a hook group to its guards and turn results into exit codes.

    python3 hooks/mark_hook.py <group>

Groups (registered in hooks/hooks.json):
  pre-write      PreToolUse  Edit|Write|MultiEdit|NotebookEdit  -> block (exit 2)
  pre-dispatch   PreToolUse  Agent|Task                         -> block (exit 2)
  pre-bash       PreToolUse  Bash                               -> block (exit 2)
  post-dispatch  PostToolUse Agent|Task                         -> bind lock, never blocks
  post-write     PostToolUse Edit|Write|MultiEdit               -> reminder (exit 2 = feedback only)
  subagent-stop  SubagentStop                                   -> keep subagent running (exit 2)

A guard that crashes fails open: the tool call proceeds and stderr says why.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from typing import NoReturn

from .guards import bash, dispatch, locks, write
from .guards.common import Env, first_block
from .hookio import EXIT_ALLOW, EXIT_BLOCK, HookContext, block, run

GROUPS = {
    "pre-write": write.PRE_WRITE,
    "pre-dispatch": dispatch.PRE_DISPATCH,
    "pre-bash": bash.PRE_BASH,
    "post-write": [dispatch.status_reminder],
    "subagent-stop": [locks.verify],
}


def notify(message: str) -> NoReturn:
    print(f"[MARK] {message}", file=sys.stderr)
    sys.exit(EXIT_BLOCK)


def _debug_log(group: str, payload: dict) -> None:
    """Append raw payloads to $MARK_DEBUG_LOG (a file path) when set. Never fails."""
    path = os.environ.get("MARK_DEBUG_LOG")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"t": time.time(), "group": group, "payload": payload}) + "\n")
    except OSError:
        pass


def handler_for(group: str):
    def handle(ctx: HookContext) -> None:
        _debug_log(group, ctx.payload)
        env = Env(ctx)
        try:
            if group == "post-dispatch":
                locks.bind(env)
                return
            message = first_block(env, GROUPS[group])
        except Exception:  # noqa: BLE001 - fail open, but say so
            print(f"[mark] internal error in {group}; allowing.\n{traceback.format_exc(limit=3)}",
                  file=sys.stderr)
            sys.exit(EXIT_ALLOW)
        if message:
            notify(message) if group == "post-write" else block(message)
    return handle


def main(argv: list[str] | None = None) -> NoReturn:
    argv = sys.argv[1:] if argv is None else argv
    group = argv[0] if argv else ""
    if group != "post-dispatch" and group not in GROUPS:
        print(f"[mark] unknown hook group {group!r}", file=sys.stderr)
        sys.exit(EXIT_ALLOW)
    run(handler_for(group))
