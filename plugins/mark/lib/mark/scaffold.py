"""Project scaffold: render the template that ships with the plugin into a project.

Only project files live here (config, CLAUDE.md, .gitignore, .mark/README.md); role agents,
prompts and formats are built into the plugin (see `defaults.py`).

The template lives in `template/common/` plus `template/<locale>/`. A file ending in `.tmpl`
has every `{{ answer }}` filled in and loses the suffix; every other file is copied as it is
(dispatch prompts keep their own `{{placeholder}}`s for `mark dispatch`).

`mark init` writes the result into a git repository, records the answers in
`.mark/template.toml` and keeps the file exactly as written under `.mark/.base/<path>.base`,
which a later upgrade merges against. An existing CLAUDE.md is kept (the project owns it),
an existing .gitignore only gains the lines it lacks, any other existing file is a conflict.
"""
from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .config import find_project_root
from .flow import FlowError
from .gitutil import current_branch, git, has_remote

_PLUGIN = Path(__file__).resolve().parents[2]
TEMPLATE = _PLUGIN / "template"
LOCALES = ("en", "zh-CN")
PROFILES = ("web-fullstack",)
RECORD = ".mark/template.toml"
BASE_DIR = ".mark/.base"
KEPT = {"CLAUDE.md"}           # kept as it is when the project already has one
MERGED = {".gitignore"}        # gains the missing lines when the project already has one

# Answer keys in the order `mark init` reports them; defaults are filled by `resolve`.
KEYS = ("project_name", "locale", "profile", "main_branch", "frontend_dir", "backend_dir",
        "ui_dir", "tests_dir", "regression_cmd", "worktree_setup")
DIR_KEYS = ("frontend_dir", "backend_dir", "ui_dir", "tests_dir")
_VAR = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def version() -> str:
    return json.loads((_PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]


def resolve(given: dict[str, str], root: Path) -> dict[str, str]:
    """Fill defaults and validate; raises FlowError on a bad answer."""
    unknown = sorted(set(given) - set(KEYS))
    if unknown:
        raise FlowError("init.unknown_answer", keys=", ".join(unknown))
    a = {k: v.strip() for k, v in given.items()}
    a.setdefault("project_name", root.name)
    a.setdefault("locale", "en")
    a.setdefault("profile", PROFILES[0])
    a.setdefault("main_branch", current_branch(root) or "main")
    a.setdefault("frontend_dir", "frontend")
    a.setdefault("backend_dir", "backend")
    a.setdefault("ui_dir", f"{a['frontend_dir'].rstrip('/')}/src/ui")
    a.setdefault("tests_dir", "tests")
    a.setdefault("regression_cmd", "")
    a.setdefault("worktree_setup", "")
    if a["locale"] not in LOCALES:
        raise FlowError("init.bad_choice", answer="locale", value=a["locale"], choices=", ".join(LOCALES))
    if a["profile"] not in PROFILES:
        raise FlowError("init.bad_choice", answer="profile", value=a["profile"], choices=", ".join(PROFILES))
    for key in KEYS:
        if "\n" in a[key] or (not a[key] and key not in ("regression_cmd", "worktree_setup")):
            raise FlowError("init.bad_answer", answer=key, value=a[key])
    for key in DIR_KEYS:
        a[key] = a[key].rstrip("/")
        if a[key].startswith("/") or ".." in a[key].split("/") or not a[key]:
            raise FlowError("init.bad_dir", answer=key, value=a[key])
    return {k: a[k] for k in KEYS}


def _fill(text: str, answers: dict[str, str], toml: bool) -> str:
    def sub(m: re.Match[str]) -> str:
        value = answers.get(m.group(1))
        if value is None:
            raise FlowError("init.unknown_var", name=m.group(1))
        return json.dumps(value, ensure_ascii=False)[1:-1] if toml else value  # values sit in "..."
    return _VAR.sub(sub, text)


def render(answers: dict[str, str]) -> dict[str, str]:
    """{project-relative path: content} for the whole template."""
    out: dict[str, str] = {}
    for layer in ("common", answers["locale"]):
        top = TEMPLATE / layer
        for p in sorted(top.rglob("*")):
            if not p.is_file() or p.name == ".DS_Store":
                continue
            rel = p.relative_to(top).as_posix()
            text = p.read_text(encoding="utf-8")
            if rel.endswith(".tmpl"):
                rel = rel[:-len(".tmpl")]
                text = _fill(text, answers, toml=rel.endswith(".toml"))
            out[rel] = text
    return out


def base_path(rel: str) -> str:
    return f"{BASE_DIR}/{rel}.base"


def missing_lines(have: str, text: str) -> list[str]:
    """Lines of the template's `text` (not comments) that the project's `have` lacks."""
    got = set(have.splitlines())
    return [ln for ln in text.splitlines() if ln and not ln.startswith("#") and ln not in got]


def appended(old: str, lines: list[str]) -> str:
    sep = "" if not old or old.endswith("\n") else "\n"
    return old + sep + "\n# Mark runtime state (never commit)\n" + "\n".join(lines) + "\n"


def record_text(answers: dict[str, str]) -> str:
    lines = ["# Written by `mark init`; do not edit. Upgrades read the answers below.",
             f'version = "{version()}"', "", "[answers]"]
    lines += [f"{k} = {json.dumps(answers[k], ensure_ascii=False)}" for k in KEYS]
    return "\n".join(lines) + "\n"


@dataclass
class Plan:
    root: Path
    answers: dict[str, str]
    fresh: bool                                         # no git repository yet
    write: dict[str, str] = field(default_factory=dict)
    append: dict[str, list[str]] = field(default_factory=dict)
    kept: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)


def plan(cwd: Path, given: dict[str, str]) -> Plan:
    """Check the target and decide what init would do; writes nothing."""
    code, top = git(["rev-parse", "--show-toplevel"], cwd)
    fresh = code != 0
    root = cwd.resolve() if fresh else Path(top).resolve()
    if find_project_root(cwd) is not None:
        raise FlowError("init.already", root=find_project_root(cwd))
    if fresh and any(root.iterdir()):
        raise FlowError("init.not_repo", root=root)
    answers = resolve(given, root)
    if not fresh:
        branch = current_branch(root)
        if branch != answers["main_branch"]:
            raise FlowError("init.not_main", branch=branch or "(detached)", main=answers["main_branch"])
        dirty = git(["status", "--porcelain"], root)[1]
        if dirty:
            raise FlowError("init.dirty", files="\n".join("  " + line for line in dirty.splitlines()[:10]))
    if git(["var", "GIT_COMMITTER_IDENT"], root)[0] != 0:
        raise FlowError("init.no_identity")
    files = render(answers)
    try:
        tomllib.loads(files[".mark/config.toml"])
    except tomllib.TOMLDecodeError as exc:
        raise FlowError("init.bad_config", error=exc) from exc
    p = Plan(root, answers, fresh)
    for rel, text in files.items():
        target = root / rel
        if not target.exists():
            p.write[rel] = text
        elif rel in MERGED:
            missing = missing_lines(target.read_text(encoding="utf-8"), text)
            if missing:
                p.append[rel] = missing
        elif rel in KEPT:
            p.kept.append(rel)
        else:
            p.conflicts.append(rel)
    if p.conflicts:
        raise FlowError("init.conflicts", files="\n".join(f"  - {r}" for r in p.conflicts))
    return p


def apply(p: Plan) -> list[tuple[str, dict]]:
    """Write the plan, commit it on main and push when there is an `origin`."""
    root, main = p.root, p.answers["main_branch"]
    if p.fresh and git(["init", "-q", "-b", main], root)[0] != 0:
        raise FlowError("init.git_failed", step="git init")
    out = dict(p.write)
    out.update({base_path(rel): text for rel, text in p.write.items()})
    out[RECORD] = record_text(p.answers)
    for rel, text in out.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    for rel, lines in p.append.items():
        (root / rel).write_text(appended((root / rel).read_text(encoding="utf-8"), lines), encoding="utf-8")
    paths = sorted(set(out) | set(p.append))
    if git(["add", "--", *paths], root)[0] != 0 or \
            git(["commit", "-q", "-m", f"chore: set up Mark v{version()}"], root)[0] != 0:
        raise FlowError("init.git_failed", step="git commit")
    notes: list[tuple[str, dict]] = []
    if has_remote(root):
        if git(["push", "-q", "origin", main], root)[0] == 0:
            notes.append(("init.pushed", {"main": main}))
        else:
            notes.append(("init.push_failed", {"main": main}))
    return notes
