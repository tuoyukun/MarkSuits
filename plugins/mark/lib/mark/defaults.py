"""Built-in role agents, prompts and formats, and the project files that override them.

The plugin ships every generic file, so auto-update upgrades a project without touching it.
A project changes one by adding a file of the same name; that file then wins:

    role agent       plugins/mark/agents/<role>.md  (loaded as `mark:<role>`)   .claude/agents/<role>.md
    dispatch prompt  defaults/<locale>/prompts/<scenario>.md                     [paths] prompts (.mark/prompts/)
    artifact format  defaults/<locale>/formats/<name>.md                         .mark/formats/<name>.md
"""
from __future__ import annotations

from pathlib import Path

from .config import MarkConfig

PLUGIN = Path(__file__).resolve().parents[2]
DEFAULTS = PLUGIN / "defaults"
PLUGIN_NAME = "mark"


def builtin(locale: str, *parts: str) -> Path:
    """A built-in file for `locale`, falling back to English."""
    path = DEFAULTS.joinpath(locale, *parts)
    return path if path.is_file() else DEFAULTS.joinpath("en", *parts)


def prompt_path(cfg: MarkConfig, scenario: str) -> Path:
    own = cfg.prompts_dir / f"{scenario}.md"
    return own if own.is_file() else builtin(cfg.locale, "prompts", f"{scenario}.md")


def format_path(cfg: MarkConfig, name: str) -> Path:
    name = name if name.endswith(".md") else f"{name}.md"
    own = cfg.state_dir / "formats" / name
    return own if own.is_file() else builtin(cfg.locale, "formats", name)


def agent_type(cfg: MarkConfig, role: str) -> str:
    """`subagent_type` for a role: the project's own agent if it has one, else the plugin's."""
    return role if (cfg.root / ".claude" / "agents" / f"{role}.md").is_file() else f"{PLUGIN_NAME}:{role}"
