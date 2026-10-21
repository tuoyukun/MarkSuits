"""Locate and load a project's `.mark/config.toml`.

A directory is a Mark project only if `.mark/config.toml` exists at or above it.
Hooks use this to stay silent in every other project, because a plugin's hooks
fire in every session where the plugin is enabled.

Every knob has an engine default here, so a minimal config (`mark_schema` only)
still yields a working, strict setup. The project template writes the full set.
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_RELPATH = Path(".mark") / "config.toml"

# Config schema versions this engine understands. Bump on breaking changes and
# ship a migration note; the engine refuses (exit 2) on unknown versions.
SUPPORTED_SCHEMAS = frozenset({1})

# The orchestrator (main thread) in role lists.
MAIN = "main"

DEFAULT_ROLES = ("designer", "coder-plan", "coder-impl", "tester", "fix-plan")
DEFAULT_GATES = {"coder-plan": "design-approved", "coder-impl": "plan-approved",
                 "tester": "plan-approved"}
DEFAULT_OUTPUTS = {"designer": ["design.md"], "coder-plan": ["tech-plan.md"],
                   "fix-plan": ["fix-plan.md"], "coder-impl": ["handoff.md"],
                   "tester": ["verdict.md"]}


class ConfigError(Exception):
    """Config exists but is unreadable or incompatible with this engine."""


@dataclass(frozen=True)
class WriteRule:
    glob: str
    roles: frozenset[str]


@dataclass(frozen=True)
class BudgetRule:
    glob: str
    max_bytes: int   # 0 = exempt


@dataclass(frozen=True)
class MarkConfig:
    root: Path
    data: dict[str, Any]

    def _section(self, name: str) -> dict[str, Any]:
        value = self.data.get(name, {})
        return value if isinstance(value, dict) else {}

    @property
    def schema(self) -> int:
        return int(self.data.get("mark_schema", 0))

    @property
    def locale(self) -> str:
        return str(self.data.get("locale", "en"))

    @property
    def main_branch(self) -> str:
        return str(self._section("project").get("main_branch", "main"))

    @property
    def state_rel(self) -> str:
        """State dir relative to the project root, POSIX style (default `.mark`)."""
        return str(self._section("paths").get("state_dir", ".mark")).strip("/")

    @property
    def state_dir(self) -> Path:
        return self.root / self.state_rel

    @property
    def roles(self) -> frozenset[str]:
        """Pipeline role names (bare, without plugin prefix)."""
        return frozenset(self.data.get("roles", DEFAULT_ROLES))

    @property
    def gates(self) -> dict[str, str]:
        """role -> gate name required before dispatch (feature tickets only)."""
        raw = self.data.get("gates", DEFAULT_GATES)
        return {k: str(v) for k, v in raw.items() if v}

    @property
    def outputs(self) -> dict[str, list[str]]:
        """role -> files the role must leave in the ticket dir before it may stop."""
        raw = self.data.get("outputs", DEFAULT_OUTPUTS)
        return {k: [str(f) for f in v] for k, v in raw.items()}

    @property
    def write_rules(self) -> list[WriteRule]:
        return [WriteRule(str(r["glob"]), frozenset(r.get("roles", [])))
                for r in self.data.get("write_rules", []) if "glob" in r]

    @property
    def doc_budget(self) -> list[BudgetRule]:
        """Byte budgets for docs agents load; first matching glob wins. None: no budget."""
        return [BudgetRule(str(r["glob"]), int(r["max_bytes"]))
                for r in self.data.get("doc_budget", [])
                if isinstance(r, dict) and "glob" in r and type(r.get("max_bytes")) is int
                and r["max_bytes"] >= 0]

    @property
    def worktree_dir(self) -> str:
        return str(self._section("worktree").get("dir", ".claude/worktrees")).strip("/")

    @property
    def main_writable(self) -> list[str]:
        """Extra globs writable in the main checkout, beyond the state lanes."""
        return [str(g) for g in self._section("worktree").get("main_writable", [])]

    @property
    def worktree_setup(self) -> str:
        """Shell command run in every new worktree before an agent gets it; exit 0 = ready."""
        return str(self._section("worktree").get("setup", "")).strip()

    @property
    def worktree_setup_timeout(self) -> int:
        value = self._section("worktree").get("setup_timeout", 300)
        return value if type(value) is int and value > 0 else 300

    @property
    def prompts_dir(self) -> Path:
        """Dispatch prompt templates (`<scenario>.md`), owned by the project."""
        rel = str(self._section("paths").get("prompts", f"{self.state_rel}/prompts")).strip("/")
        return self.root / rel

    @property
    def design_qa_paths(self) -> list[str]:
        """Globs that make a feature with design.md go through design-qa. Empty: never."""
        return [str(g) for g in self._section("design_qa").get("paths", [])]

    @property
    def design_qa_exclude(self) -> list[str]:
        return [str(g) for g in self._section("design_qa").get("exclude", [])]

    @property
    def merge_regression(self) -> str:
        """Shell command `mark merge` runs in the worktree after merging main; exit 0 = green."""
        return str(self._section("merge").get("regression", "")).strip()

    def branch_for(self, kind: str, ticket_id: str) -> str:
        return f"{kind}/{ticket_id}"

    def worktree_for(self, kind: str, ticket_id: str) -> str:
        return f"{self.worktree_dir}/{kind}-{ticket_id}"


def find_project_root(start: str | Path | None) -> Path | None:
    """Walk up from `start` to the nearest directory holding `.mark/config.toml`."""
    if not start:
        return None
    here = Path(start).resolve()
    if here.is_file():
        here = here.parent
    for candidate in (here, *here.parents):
        if (candidate / CONFIG_RELPATH).is_file():
            return candidate
    return None


def load_config(root: Path) -> MarkConfig:
    path = root / CONFIG_RELPATH
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    cfg = MarkConfig(root=root, data=data)
    if cfg.schema not in SUPPORTED_SCHEMAS:
        raise ConfigError(
            f"{path} declares mark_schema={cfg.schema}, but this engine supports "
            f"{sorted(SUPPORTED_SCHEMAS)}. Update the plugin or migrate the config."
        )
    return cfg
