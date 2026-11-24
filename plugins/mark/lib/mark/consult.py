"""Board consult: free talk with Claude about a project, read-only, in a disposable worktree.

Unlike a ticket's chat (`chat.py`), a consult opens no ticket and changes no project state. Each
visit is a conversation of its own: the board resets it on entry (`reset`), which stops any turn,
drops the old log and model pin, and cuts a fresh detached worktree at the main checkout's HEAD.
Every message is one headless `claude -p` turn, resuming the visit's session, so the discussion
carries on within a visit; the next visit starts from zero.

The session gets Read/Grep/Glob/Bash and no edits or subagents: Bash runs with the worktree as
its cwd, so tests and builds are possible while the real checkout never changes. MCP servers are
off. `guards.bash.consult_guard` (the `MARK_CONSULT_ROOT` marker below) refuses shell writes
outside that worktree, git writes and `mark`, so a stray command cannot reach the real project.
This is a guardrail, not a kernel sandbox: a determined interpreter escape is possible, which is
why the prompt also says read-only.

State: `<state>/locks/chat-consult.*` (log, pid, model pin; `chat.py`) and
`<state>/locks/consult-wt/` (the worktree). Both gitignored, both removed by `reset`.

If the repository has no HEAD or git cannot cut the worktree, the visit falls back to the main
checkout with Read/Grep/Glob only (`dontAsk`), and the board says Bash is off.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from . import ask, chat
from .config import MarkConfig
from .gitutil import git

ID = "consult"
WORKTREE = "consult-wt"
ROOT_ENV = "MARK_CONSULT_ROOT"  # tells `guards.bash.consult_guard` where it may write
TOOLS = "Read,Grep,Glob,Bash"
READ_ONLY_TOOLS = "Read,Grep,Glob"
NO_MCP = '{"mcpServers":{}}'

NOTE = (
    "This is a read-only consultation on the Mark web board: the human asks about this project "
    "and reads your reply there; their next message carries the discussion on. You do not "
    "implement anything here: do not edit files, do not run `mark`, do not start another Claude "
    "session, and do not commit, push, tag or otherwise change git state. Bash runs inside a "
    "disposable copy of the repository at HEAD: read, explore and run builds or tests there if "
    "useful, but never touch paths outside it. Read-only git is fine (`git log`, `git show`, "
    "`git diff`, `git status`, `git blame`, `git rev-parse`, `git for-each-ref`). "
    "AskUserQuestion does not exist here: ask your questions as plain text in your reply and end "
    "the turn; never start `mark wait`. If the answer calls for a code change, describe it and "
    "suggest a ticket. Answer in the human's language."
)
NOTE_READ_ONLY = (
    "This is a read-only consultation on the Mark web board: the human asks about this project "
    "and reads your reply there; their next message carries the discussion on. You have only "
    "Read, Grep and Glob: no shell and no edits, so you cannot run commands, tests or builds. Do "
    "not run `mark`, do not start another Claude session, and do not change anything. Ask your "
    "questions as plain text in your reply and end the turn; never start `mark wait`. If the "
    "answer calls for a code change, describe it and suggest a ticket. Answer in the human's "
    "language."
)


def worktree(cfg: MarkConfig) -> Path:
    return cfg.state_dir / "locks" / WORKTREE


def _meta_path(cfg: MarkConfig) -> Path:
    return cfg.state_dir / "locks" / "chat-consult.meta.json"


def _meta(cfg: MarkConfig) -> dict:
    try:
        data = json.loads(_meta_path(cfg).read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _dirty(cfg: MarkConfig) -> bool:
    """Whether the main checkout has uncommitted changes: the sandbox is cut from HEAD, not them.
    The locks dir is excluded: the visit's own worktree and log live there."""
    code, out = git(["status", "--porcelain", "--", ".",
                     f":(exclude){cfg.state_rel}/locks"], cfg.root)
    return code == 0 and bool(out)


def _remove(cfg: MarkConfig) -> None:
    """Remove the visit's worktree and its registration; never touches anything else."""
    wt = worktree(cfg)
    git(["worktree", "remove", "--force", "--force", str(wt)], cfg.root)
    if wt.is_dir() and not wt.is_symlink():
        shutil.rmtree(wt, ignore_errors=True)  # a half-deleted or unregistered copy
    git(["worktree", "prune"], cfg.root)


def _cut(cfg: MarkConfig) -> bool:
    wt = worktree(cfg)
    code, _ = git(["worktree", "add", "--detach", "--force", str(wt), "HEAD"], cfg.root)
    return code == 0 and wt.is_dir()


def discard(cfg: MarkConfig) -> None:
    """Stop the turn and drop the visit: worktree, log, pid, model pin, meta and any ask file."""
    chat.stop(cfg, ID)
    _remove(cfg)
    for p in (chat.log_path(cfg, ID), chat.state_path(cfg, ID),
              chat.settings_path(cfg, ID), chat.stop_path(cfg, ID), _meta_path(cfg)):
        p.unlink(missing_ok=True)
    ask.clear(cfg, ID)


def reset(cfg: MarkConfig) -> dict[str, object]:
    """Start a new visit: a new conversation and a fresh sandbox cut from HEAD.
    Returns {"sandbox": whether Bash is available, "dirty": main has uncommitted changes}."""
    discard(cfg)
    data = {"sandbox": _cut(cfg), "dirty": _dirty(cfg)}
    meta = _meta_path(cfg)
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(json.dumps(data) + "\n")
    return data


def send(cfg: MarkConfig, text: object) -> tuple[bool, str]:
    """The human's next consult message: (started, why not)."""
    if not isinstance(text, str) or not text.strip() or len(text) > chat.TEXT_MAX:
        return False, "bad request"
    text = text.strip()
    sandbox = worktree(cfg).is_dir()
    args = ["--strict-mcp-config", "--mcp-config", NO_MCP,
            "--tools", TOOLS if sandbox else READ_ONLY_TOOLS]
    started, why = chat.start(
        cfg, "", ID, text, first=text,
        note=NOTE if sandbox else NOTE_READ_ONLY,
        cwd=worktree(cfg) if sandbox else cfg.root,
        args=args,
        mode="bypassPermissions" if sandbox else "dontAsk",
        env_extra={ROOT_ENV: str(worktree(cfg))} if sandbox else None,
    )
    return started, "" if started else f"chat.{why}"


def stop(cfg: MarkConfig) -> bool:
    return chat.stop(cfg, ID)


def view(cfg: MarkConfig) -> dict[str, object]:
    """What the board shows: the conversation, whether a turn runs, the model, whether the
    sandbox is up, whether main is dirty, and the last turn's context size."""
    out = chat.view(cfg, ID)
    out["sandbox"] = worktree(cfg).is_dir()
    out["dirty"] = bool(_meta(cfg).get("dirty"))
    out["tokens"] = _tokens(cfg)
    return out


def _tokens(cfg: MarkConfig) -> int:
    """Input tokens the last result reported (the transcript the next turn will resend)."""
    for event in reversed(chat._events(cfg, ID)):
        if isinstance(event, dict) and event.get("type") == "result":
            usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
            return sum(usage.get(k) if isinstance(usage.get(k), int) else 0 for k in
                       ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return 0
