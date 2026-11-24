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
from .. import e2e, globs, human
from .write import cli_only_rules, home_block, scope_block, worktree_block

_SEPARATORS = ("&&", "||", ";", "|", "\n")


def _segments(command: str) -> list[str]:
    """Simple commands of a command line: split at `&&`, `||`, `;`, `|` and newlines outside
    quotes, heredoc bodies dropped, `\\`-newline continuations joined."""
    text, out, start, i, quote = _strip_heredocs(command), [], 0, 0, ""
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 1
            elif c == quote:
                quote = ""
        elif c in "'\"":
            quote = c
        elif c == "\\":
            i += 1
        else:
            sep = next((x for x in _SEPARATORS if text.startswith(x, i)), None)
            if sep:
                out.append(text[start:i])
                start = i + len(sep)
                i = start
                continue
        i += 1
    out.append(text[start:])
    return [seg.replace("\\\n", " ") for seg in out]


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
    for segment in _segments(command):
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
    return any(r.lstrip("+").split(":")[-1] in (main, f"refs/heads/{main}")
               or r.lstrip("+") == "HEAD" and branch == main for r in refs[1:])


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
        if env.role and sub == "commit" and branch == main:
            return env.t("guard.bash.commit_main", who=env.role)
        # From any branch: `git push origin HEAD:main` in a ticket worktree lands work too.
        if env.role and sub == "push" and _pushes_main(args, branch, main):
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


# Shell writes: `> f`, `>> f`, `tee f`, `touch f`, `sed/perl/ruby -i … f`, `cp/mv … dest`. Quoted text is
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
    elif cmd in ("sed", "perl", "ruby") and any(w == "--in-place" or w.startswith("--in-place=")
                                                or re.match(r"^-[a-zA-Z0-9]*i", w) for w in words[1:]):
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
    thread is held only to the files the `mark` CLI alone writes (gates, status, reviews...) and to
    the roles' artifacts in ticket dirs."""
    command = str(env.tool_input.get("command") or "")
    if ">" not in command and not re.search(r"\b(tee|touch|sed|perl|ruby|cp|mv)\b", command):
        return None
    for here, segment, words, values in _commands(command, env.cwd):
        for target in _shell_targets(here, segment, words, values):
            loc = env.locate(target)
            if why := home_block(env, loc.path):
                return env.t("guard.bash.shell_write", rel=str(loc.path), why=why)
            if loc.rel is None:
                continue
            if env.role is None:
                hit = any(globs.match(g, loc.rel) for g in cli_only_rules(env))
                why = env.t("guard.scope_cli", rel=loc.rel) if hit else None
                # A role's artifact in a ticket dir (verdict.md, design-qa.md...) carries anchors the
                # engine trusts; the main thread may not forge it through the shell either.
                if why is None and env.ticket_of_rel(loc.rel):
                    why = scope_block(env, loc)
            else:
                why = scope_block(env, loc) or worktree_block(env, loc) or _tests_block(env, loc.rel)
            if why:
                return env.t("guard.bash.shell_write", rel=loc.rel, why=why)
    return None


# --------------------------------------------------------------------------
# Consult sessions (the board's read-only free talk): full Bash, but only inside a
# disposable worktree. `consult.py` marks the process with MARK_CONSULT_ROOT.
# --------------------------------------------------------------------------

CONSULT_ROOT_ENV = "MARK_CONSULT_ROOT"
GIT_READ = frozenset({
    "log", "show", "diff", "diff-tree", "diff-index", "diff-files", "status", "blame",
    "rev-parse", "rev-list", "ls-files", "ls-tree", "grep", "shortlog", "describe",
    "cat-file", "for-each-ref", "show-ref", "merge-base", "name-rev", "whatchanged",
    "help", "version", "count-objects", "check-ignore", "check-attr", "check-ref-format",
    "var", "cherry", "range-diff", "verify-commit", "verify-tag", "fsck",
})
_GIT_WRITE_OPTIONS = ("--output", "--ext-diff")


def _written(here: Path | None, segment: str, words: list[str], values: dict[str, str]) -> list[Path]:
    """Paths this simple command would write, as far as static parsing can tell. Wider than
    `_shell_targets`: destructive commands count too, because a consult may use them."""
    def full(word: str) -> Path | None:
        path = expand(word, values)
        if path is None or (here is None and not os.path.isabs(path)):
            return None
        return Path(os.path.realpath(path if here is None else os.path.join(here, path)))

    raw: list[str] = list(_REDIRECT.findall(_QUOTED.sub("''", segment)))
    cmd = os.path.basename(words[0]) if words else ""
    args = [w for w in words[1:] if not w.startswith("-")]
    if cmd in ("tee", "touch", "rm", "rmdir", "mkdir", "truncate", "unlink", "shred",
               "mkfifo", "mknod", "install", "ln"):
        raw += args
    elif cmd in ("chmod", "chown"):
        raw += args[1:]  # the mode/owner is not a path
    elif cmd in ("cp", "mv") and len(args) >= 2:
        *srcs, dest = args
        dest_dir = (f := full(dest)) is not None and f.is_dir()
        raw += [os.path.join(dest, os.path.basename(s)) for s in srcs] if dest_dir else [dest]
        if cmd == "mv":
            raw += srcs
    elif cmd in ("sed", "perl", "ruby") and any(
            w == "--in-place" or w.startswith("--in-place=")
            or re.match(r"^-[a-zA-Z0-9]*i", w) for w in words[1:]):
        raw += [a for a in args if (f := full(a)) and f.is_file()]
    elif cmd == "dd":
        raw += [w.split("=", 1)[1] for w in words[1:] if w.startswith("of=")]
    elif cmd == "find" and any(w in ("-delete", "-exec", "-execdir", "-ok", "-okdir",
                                     "-fprint", "-fprintf", "-fls") for w in words[1:]):
        raw += args[:1]  # the search root; -exec's own command is beyond static parsing
    elif cmd == "curl":
        raw += [words[i + 2] for i, w in enumerate(words[1:])
                if w in ("-o", "--output") and i + 2 < len(words)]
        raw += [w.split("=", 1)[1] for w in words[1:] if w.startswith("--output=")]
    elif cmd == "wget":
        raw += [words[i + 2] for i, w in enumerate(words[1:])
                if w in ("-O", "--output-document") and i + 2 < len(words)]
        raw += [w.split("=", 1)[1] for w in words[1:] if w.startswith("--output-document=")]
    return [p for w in raw if w and not w.startswith("/dev/") and (p := full(w)) is not None]


def _git_args(words: list[str]) -> list[str] | None:
    """git's arguments after its global options, or None if this is not a git call."""
    if not words or os.path.basename(words[0]) != "git":
        return None
    args = words[1:]
    while args and args[0].startswith("-"):
        if args[0] in ("-C", "-c", "--git-dir", "--work-tree", "--namespace") and len(args) > 1:
            args = args[2:]
        else:
            args = args[1:]
    return args


def consult_guard(env: Env) -> str | None:
    """A board consult session (`consult.py`) writes only inside its disposable worktree, changes
    no git or ticket state, and never runs `mark`. The real checkout is read-only for it."""
    root = os.environ.get(CONSULT_ROOT_ENV)
    if not root:
        return None
    sandbox = Path(os.path.realpath(root))
    if not sandbox.is_dir():
        return env.t("guard.consult.no_sandbox")
    command = str(env.tool_input.get("command") or "")
    for here, segment, words, values in _commands(command, env.cwd):
        if not words:
            continue
        name = os.path.basename(words[0])
        if name == "mark":
            return env.t("guard.consult.mark")
        if name == "git":
            args = _git_args(words) or []
            if args and (args[0] not in GIT_READ
                         or any(a.startswith(_GIT_WRITE_OPTIONS) for a in args[1:])):
                return env.t("guard.consult.git")
        for path in _written(here, segment, words, values):
            if path != sandbox and not path.is_relative_to(sandbox):
                return env.t("guard.consult.write", root=str(sandbox), path=str(path))
    return None


# `mark` subcommands that change ticket state. Subagents report outcomes in
# their result; the orchestrator records them.
MARK_WRITES = frozenset({"set", "approve", "reject", "void", "claim", "commit", "dispatch", "unlock", "merge", "propose", "ask",
                         "upgrade", "general", "init"})


def mark_guard(env: Env) -> str | None:
    command = str(env.tool_input.get("command") or "")
    tokens = f"{env.cfg.state_rel}/locks/human"
    if tokens in command or "locks/human" in command:
        return env.t("guard.bash.human_tokens", dir=tokens)
    if env.role is None or "mark" not in command:
        return None
    for segment in _segments(command):
        try:
            words = shlex.split(segment)
        except ValueError:
            continue
        while words and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0]):
            words = words[1:]
        if len(words) > 1 and os.path.basename(words[0]) == "mark" and words[1] in MARK_WRITES:
            return env.t("guard.bash.mark_cli", who=env.role, sub=words[1])
    return None


CLAUDE_NAMES = frozenset({"claude", "claude-code"})
_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "fish"})


def runs_claude(command: str, depth: int = 0) -> bool:
    """Whether the command starts the Claude Code CLI: any word naming it (`claude`, a path to it,
    `npx @anthropic-ai/claude-code`, `script -q /dev/null claude`, `$(claude ...)`), also inside
    `sh -c` / `eval` strings. A plain mention like `grep claude` counts too; better a refused
    search than a missed call."""
    for segment in _segments(command):
        try:
            words = shlex.split(segment)
        except ValueError:
            continue
        for i, word in enumerate(words):
            if os.path.basename(word.lstrip("$(`")).rstrip(")`") in CLAUDE_NAMES:
                return True
            inner = (i > 0 and words[i - 1] == "-c" and os.path.basename(words[0]) in _SHELLS) \
                or (words[0] == "eval" and i > 0)
            if inner and depth < 3 and runs_claude(word, depth + 1):
                return True
    return False


def claude_guard(env: Env) -> str | None:
    """A nested `claude -p "/mark:approve 0012"` would fire UserPromptSubmit in a session the model
    started. `human.attended` already refuses tokens there; this also keeps the model from running
    a Claude session (e.g. an interactive one under a pseudo-terminal) it was not asked to."""
    if runs_claude(str(env.tool_input.get("command") or "")):
        return env.t("guard.bash.claude_cli")
    return None


def wait_guard(env: Env) -> str | None:
    """In a headless session (`claude -p`: the board's chat or runner) nobody comes back for a
    background task, and a running one keeps the session from ever ending: no `mark wait`."""
    command = str(env.tool_input.get("command") or "")
    if "wait" not in command or human.attended():
        return None
    for _, _, words, _ in _commands(command, env.cwd):
        if os.path.basename(words[0]) == "mark" and words[1:2] == ["wait"] and "--stop" not in words:
            return env.t("guard.bash.headless_wait")
    return None


PRE_BASH = [consult_guard, claude_guard, mark_guard, wait_guard, git_guard, shell_write_guard]
