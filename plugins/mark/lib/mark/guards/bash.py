"""Guards for shell commands (PreToolUse: Bash).

Static command parsing is never complete, so these guards only act on clear
git patterns and allow whenever the target cannot be determined.
"""
from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

from ..general import PREFIX as LANE_PREFIX
from ..gitutil import checkout_root, current_branch
from .common import Env

_SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\|")


def _strip_heredocs(cmd: str) -> str:
    """Drop heredoc bodies; they are data, not commands."""
    out, lines, i = [], cmd.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        m = re.search(r"<<-?\s*['\"]?(\w+)['\"]?", line)
        if m:
            end = m.group(1)
            i += 1
            while i < len(lines) and lines[i].strip() != end:
                i += 1
        i += 1
    return "\n".join(out)


def git_calls(command: str, cwd: Path) -> list[tuple[Path, list[str]]]:
    """[(directory the git call runs in, git args after global options)]."""
    calls: list[tuple[Path, list[str]]] = []
    here = cwd
    for segment in _SEGMENT_SPLIT.split(_strip_heredocs(command)):
        try:
            words = shlex.split(segment)
        except ValueError:
            continue
        while words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):
            words = words[1:]  # env assignments
        if not words:
            continue
        if words[0] == "cd" and len(words) > 1:
            here = Path(os.path.join(here, os.path.expanduser(words[1])))
            continue
        if words[0] != "git":
            continue
        args, where = words[1:], here
        while args and args[0].startswith("-"):
            if args[0] == "-C" and len(args) > 1:
                where = Path(os.path.join(where, os.path.expanduser(args[1])))
                args = args[2:]
            elif args[0] == "-c" and len(args) > 1:
                args = args[2:]
            else:
                args = args[1:]
        if args:
            calls.append((where, args))
    return calls


def _pushes_main(args: list[str], branch: str, main: str) -> bool:
    refs = [a for a in args[1:] if not a.startswith("-")]
    if len(refs) <= 1:          # `git push` / `git push origin` push the current branch
        return branch == main
    return any(r.split(":")[-1] in (main, f"refs/heads/{main}") or r == "HEAD" and branch == main
               for r in refs[1:])


def git_guard(env: Env) -> str | None:
    command = str(env.tool_input.get("command") or "")
    if "git" not in command:
        return None
    main = env.cfg.main_branch
    for where, args in git_calls(command, env.cwd):
        if not where.is_dir():
            continue
        branch = current_branch(where)
        sub = args[0]
        if env.role and branch == main:
            if sub == "commit":
                return env.t("guard.bash.commit_main", who=env.role)
            if sub == "push" and _pushes_main(args, branch, main):
                return env.t("guard.bash.push_main", who=env.role)
        if sub == "merge" and branch == main and checkout_root(where) == env.main:
            refs = [a for a in args[1:] if not a.startswith("-")]
            ticket_ref = next((r for r in refs if r.removeprefix("origin/").startswith(("feature/", "bug/"))), None)
            if ticket_ref:
                return env.t("guard.bash.merge_main", ref=ticket_ref, main=main)
            lane_ref = next((r for r in refs if r.removeprefix("origin/").startswith(LANE_PREFIX)), None)
            if lane_ref:
                return env.t("guard.bash.merge_lane", ref=lane_ref, main=main)
        if sub in ("checkout", "switch"):
            names = [a for a in args[1:] if not a.startswith("-")]
            ticket_branch = next((n for n in names if n.startswith(("feature/", "bug/"))), None)
            if ticket_branch and checkout_root(where) == env.main:
                kind, _, ticket_id = ticket_branch.partition("/")
                return env.t("guard.bash.checkout_main", branch=ticket_branch,
                             wt=env.cfg.worktree_for(kind, ticket_id))
    return None


# `mark` subcommands that change ticket state. Subagents report outcomes in
# their result; the orchestrator records them.
MARK_WRITES = frozenset({"set", "approve", "reject", "claim", "commit", "dispatch", "unlock", "merge", "upgrade"})


def mark_guard(env: Env) -> str | None:
    command = str(env.tool_input.get("command") or "")
    tokens = f"{env.cfg.state_rel}/locks/human"
    if tokens in command or "locks/human" in command:
        return env.t("guard.bash.human_tokens", dir=tokens)
    if env.role is None or "mark" not in command:
        return None
    for segment in _SEGMENT_SPLIT.split(_strip_heredocs(command)):
        try:
            words = shlex.split(segment)
        except ValueError:
            continue
        while words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):
            words = words[1:]
        if len(words) > 1 and os.path.basename(words[0]) == "mark" and words[1] in MARK_WRITES:
            return env.t("guard.bash.mark_cli", who=env.role, sub=words[1])
    return None


PRE_BASH = [mark_guard, git_guard]
