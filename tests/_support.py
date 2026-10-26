"""Test helpers: make the plugin's `lib/` importable and build fake projects."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "mark"
sys.path.insert(0, str(PLUGIN_ROOT / "lib"))

MINIMAL_CONFIG = 'mark_schema = 1\nlocale = "zh-CN"\n'


def make_project(config_text: str | None = MINIMAL_CONFIG) -> Path:
    """Create a temp directory; write `.mark/config.toml` unless config_text is None."""
    root = Path(tempfile.mkdtemp(prefix="mark-test-"))
    if config_text is not None:
        (root / ".mark").mkdir()
        (root / ".mark" / "config.toml").write_text(config_text, encoding="utf-8")
    return root


# --------------------------------------------------------------------------
# Git-backed fixtures for guard tests
# --------------------------------------------------------------------------
import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402

HOOK = PLUGIN_ROOT / "hooks" / "mark_hook.py"

FULL_CONFIG = '''mark_schema = 1
locale = "en"
roles = ["designer", "coder-plan", "coder-impl", "tester", "fix-plan"]

[project]
main_branch = "main"

[gates]
coder-plan = "design-approved"
coder-impl = "plan-approved"
tester = "plan-approved"

[outputs]
designer = ["design.md"]
coder-plan = ["tech-plan.md"]
fix-plan = ["fix-plan.md"]
coder-impl = ["handoff.md"]
tester = ["verdict.md"]

[[write_rules]]
glob = "**/requirement.md"
roles = ["main"]
[[write_rules]]
glob = "**/design.md"
roles = ["designer"]
[[write_rules]]
glob = "**/tech-plan.md"
roles = ["coder-plan"]
[[write_rules]]
glob = "**/handoff.md"
roles = ["coder-impl"]
[[write_rules]]
glob = "**/verdict.md"
roles = ["tester"]
[[write_rules]]
glob = "tests/**"
roles = ["tester"]
[[write_rules]]
glob = "frontend/**"
roles = ["coder-impl"]
'''

GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
           "PYTHONDONTWRITEBYTECODE": "1"}
# CLI tests run git in-process (mark set / approve commit on main).
os.environ.update({k: v for k, v in GIT_ENV.items() if k.startswith("GIT_")})


def sh(cwd, *args: str) -> str:
    out = subprocess.run(list(args), cwd=cwd, env=GIT_ENV, capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"{args}: {out.stderr}")
    return out.stdout.strip()


def make_repo(config_text: str = FULL_CONFIG) -> Path:
    root = make_project(config_text).resolve()
    sh(root, "git", "init", "-q", "-b", "main")
    sh(root, "git", "add", ".")
    sh(root, "git", "commit", "-q", "-m", "init")
    return root


def status_text(status: str, **extra: str) -> str:
    fields = {"status": status, "owner": "x", "updated": "2026-01-01",
              "updater": "orchestrator", "desc": "d", **extra}
    return "---\n" + "".join(f"{k}: {v}\n" for k, v in fields.items()) + "---\n"


def add_ticket(root: Path, kind: str, ticket_id: str, status: str, gates=(), commit=True, **extra: str) -> Path:
    d = root / ".mark" / ("features" if kind == "feature" else "bugs") / ticket_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "status.md").write_text(status_text(status, **extra), encoding="utf-8")
    for g in gates:
        gd = root / ".mark" / "gates"
        gd.mkdir(exist_ok=True)
        (gd / f"{ticket_id}.{g}").write_text("ok\n")
    if commit:
        sh(root, "git", "add", ".")
        sh(root, "git", "commit", "-q", "-m", f"ticket {ticket_id}")
    return d


def add_worktree(root: Path, kind: str, ticket_id: str, base: str = "main") -> Path:
    wt = root / ".claude" / "worktrees" / f"{kind}-{ticket_id}"
    sh(root, "git", "worktree", "add", "-q", "-b", f"{kind}/{ticket_id}", str(wt), base)
    return wt


def add_origin(root: Path) -> Path:
    bare = Path(tempfile.mkdtemp(prefix="mark-origin-")).resolve()
    sh(bare, "git", "init", "-q", "--bare", "-b", "main")
    sh(root, "git", "remote", "add", "origin", str(bare))
    sh(root, "git", "push", "-q", "-u", "origin", "main")
    return bare


def hook(group: str, payload: dict) -> tuple[int, str]:
    p = subprocess.run([sys.executable, str(HOOK), group], input=json.dumps(payload),
                       capture_output=True, text=True, env=GIT_ENV)
    return p.returncode, p.stderr


SCENARIO_ROLES = {
    "designer-initial": "designer", "designer-review-rework": "designer", "designer-rework": "designer",
    "designer-integration-qa": "designer", "coder-plan": "coder-plan", "coder-plan-rework": "coder-plan",
    "coder-impl": "coder-impl", "coder-impl-fix": "coder-impl", "coder-impl-merge-rework": "coder-impl",
    "tester-initial": "tester", "tester-reverify": "tester", "fix-plan-initial": "fix-plan",
    "fix-plan-rework": "fix-plan", "designer-bugfix": "designer",
}


def add_templates(root: Path, body: str = "Work on {{id}} in {{ticket_dir}}.\n{{brief}}\n") -> None:
    d = root / ".mark" / "prompts"
    d.mkdir(parents=True, exist_ok=True)
    for scenario, role in SCENARIO_ROLES.items():
        extra = "outputs: design-qa.md\n" if scenario == "designer-integration-qa" else ""
        (d / f"{scenario}.md").write_text(f"---\nrole: {role}\n{extra}---\n{body}", encoding="utf-8")


def human_typed(root: Path, prompt: str) -> tuple[int, str]:
    return hook("user-prompt", {"hook_event_name": "UserPromptSubmit", "cwd": str(root), "prompt": prompt})
