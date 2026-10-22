"""Guards for shell commands (PreToolUse: Bash).

Static command parsing is never complete, so these guards only act on clear
patterns and allow whenever the target cannot be determined.
"""
from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

from ..general import PREFIX as LANE_PREFIX
from ..gitutil import checkout_root, current_branch, git
from .common import Env
from .. import e2e, globs
from .write import cli_only_rules, scope_block, worktree_block

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


_ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S)
_VAR_REF = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")


def expand(word: str, values: dict[str, str]) -> str | None:
    """`~`, `$NAME` and `${NAME}` from the command's own assignments, then the environment;
    None when the shell alone knows the result (`$(...)`, backticks, an unknown name)."""
    missing = False

    def sub(m: re.Match[str]) -> str:
        nonlocal missing
        name = m.group(1) or m.group(2)
        value = values.get(name, os.environ.get(name))
        missing = missing or value is None
        return value or ""
    out = _VAR_REF.sub(sub, word)
    return None if missing or "$" in out or "`" in out else os.path.expanduser(out)


def _commands(command: str, cwd: Path) -> list[tuple[Path | None, str, list[str], dict[str, str]]]:
    """[(directory, raw segment, words, variables set so far)] per simple command; follows
    `cd`. The directory is None after a `cd` whose target only the shell knows."""
    out: list[tuple[Path | None, str, list[str], dict[str, str]]] = []
    here: Path | None = cwd
    values: dict[str, str] = {}
    for segment in _SEGMENT_SPLIT.split(_strip_heredocs(command)):
        try:
            words = shlex.split(segment)
        except ValueError:
            continue
        sets = words[0] == "export" if words else False
        if sets:
            words = words[1:]
        while words and (m := _ASSIGN.match(words[0])):
            value = expand(m.group(2), values)
            if value is not None:   # shortcut: `A=1 cmd` also sets A for later segments; harmless for finding paths
                values[m.group(1)] = value
            else:
                values.pop(m.group(1), None)
            words = words[1:]
        if not words or sets:
            continue
        if words[0] == "cd" and len(words) > 1:
            target = expand(words[1], values)
            here = None if here is None or target is None else Path(os.path.join(here, target))
            continue
        out.append((here, segment, words, dict(values)))
    return out


def git_calls(command: str, cwd: Path) -> list[tuple[Path, list[str]]]:
    """[(directory the git call runs in, git args after global options)]."""
    calls: list[tuple[Path, list[str]]] = []
    for here, _, words, values in _commands(command, cwd):
        if words[0] != "git":
            continue
        args, where = words[1:], here
        while args and args[0].startswith("-"):
            if args[0] == "-C" and len(args) > 1:
                target = expand(args[1], values)
                where = None if where is None or target is None else Path(os.path.join(where, target))
                args = args[2:]
            elif args[0] == "-c" and len(args) > 1:
                args = args[2:]
            else:
                args = args[1:]
        if args and where is not None:
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
        lost = _discards_work(env, where, args)
        if lost:
            return lost
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


def _unsaved(where: Path, rev: str, main: str) -> int:
    """Commits on `rev` that are on no remote and not on local main."""
    code, out = git(["rev-list", "--count", rev, "--not", "--remotes", f"refs/heads/{main}", "--"], where)
    return int(out) if code == 0 and out.isdigit() else 0


def _discards_work(env: Env, where: Path, args: list[str]) -> str | None:
    """Forced worktree/branch removal that would lose uncommitted or unpushed work."""
    main = env.cfg.main_branch
    names = [a for a in args[2:] if not a.startswith("-")]
    if args[:2] == ["worktree", "remove"] and {"-f", "--force"} & set(args) and names:
        wt = Path(os.path.join(where, os.path.expanduser(names[-1])))
        if not wt.is_dir():
            return None
        if git(["status", "--porcelain"], wt)[1]:
            return env.t("guard.bash.discard_dirty", wt=names[-1])
        n = _unsaved(wt, "HEAD", main)
        if n:
            return env.t("guard.bash.discard_unpushed", ref=current_branch(wt) or names[-1], n=n)
    forced = "-D" in args or ({"-d", "--delete"} & set(args) and {"-f", "--force"} & set(args))
    if args[:1] == ["branch"] and forced:
        names = [a for a in args[1:] if not a.startswith("-")]
        for name in names:
            n = _unsaved(where, f"refs/heads/{name}", main)
            if n:
                return env.t("guard.bash.discard_unpushed", ref=name, n=n)
    return None


# Shell writes: `> f`, `>> f`, `tee f`, `touch f`, `sed -i … f`, `cp/mv … dest`. Quoted text is
# dropped first, so a quoted target is never checked (allowed, like any unclear case); so is a
# target only the shell can resolve, or a relative one after a `cd` only the shell can resolve.
_QUOTED = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")
_REDIRECT = re.compile(r"""(?:^|[^<>\d&])[\d&]?>>?\|?\s*([^\s<>&|;()`*'"]+)""")


def _shell_targets(here: Path | None, segment: str, words: list[str], values: dict[str, str]) -> list[str]:
    def full(word: str) -> str | None:
        path = expand(word, values)
        if path is None or (here is None and not os.path.isabs(path)):
            return None
        return path if here is None else os.path.join(here, path)

    found = _REDIRECT.findall(_QUOTED.sub("''", segment))
    cmd, args = os.path.basename(words[0]), [w for w in words[1:] if not w.startswith("-")]
    if cmd in ("tee", "touch"):
        found += args
    elif cmd == "sed" and any(w == "--in-place" or w.startswith("--in-place=")
                              or re.match(r"^-[a-zA-Z]*i", w) for w in words[1:]):
        found += [a for a in args if (f := full(a)) and os.path.isfile(f)]
    elif cmd in ("cp", "mv") and len(args) >= 2:
        *srcs, dest = args
        dest_dir = (f := full(dest)) is not None and os.path.isdir(f)
        found += [os.path.join(dest, os.path.basename(s)) for s in srcs] if dest_dir else [dest]
        if cmd == "mv":
            found += srcs
    return [f for w in found if w and not w.startswith("/dev/") and (f := full(w))]


def _tests_block(env: Env, rel: str) -> str | None:
    """The content rules for end-to-end tests read the text Edit/Write sends; the shell hides it."""
    tests_dir = env.cfg.path("tests")
    if env.role == "tester" and tests_dir and rel.startswith(tests_dir + "/") and e2e.is_code(rel):
        return env.t("guard.bash.tests_via_tools")
    return None


def shell_write_guard(env: Env) -> str | None:
    """Subagents may not reach paths through the shell that Edit/Write would refuse. The main
    thread is held only to the files the `mark` CLI alone writes (gates, status, reviews...)."""
    command = str(env.tool_input.get("command") or "")
    if ">" not in command and not re.search(r"\b(tee|touch|sed|cp|mv)\b", command):
        return None
    for here, segment, words, values in _commands(command, env.cwd):
        for target in _shell_targets(here, segment, words, values):
            loc = env.locate(target)
            if loc.rel is None:
                continue
            if env.role is None:
                hit = any(globs.match(g, loc.rel) for g in cli_only_rules(env))
                why = env.t("guard.scope_cli", rel=loc.rel) if hit else None
            else:
                why = scope_block(env, loc) or worktree_block(env, loc) or _tests_block(env, loc.rel)
            if why:
                return env.t("guard.bash.shell_write", rel=loc.rel, why=why)
    return None


# `mark` subcommands that change ticket state. Subagents report outcomes in
# their result; the orchestrator records them.
MARK_WRITES = frozenset({"set", "approve", "reject", "claim", "commit", "dispatch", "unlock", "merge",
                         "upgrade", "general", "init"})


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


PRE_BASH = [mark_guard, git_guard, shell_write_guard]
