"""Locate and load a project's `.mark/config.toml`.

A directory is a Mark project only if `.mark/config.toml` exists at or above it.
Hooks use this to stay silent in every other project, because a plugin's hooks
fire in every session where the plugin is enabled.
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


class ConfigError(Exception):
    """Config exists but is unreadable or incompatible with this engine."""


@dataclass(frozen=True)
class MarkConfig:
    root: Path
    data: dict[str, Any]

    @property
    def schema(self) -> int:
        return int(self.data.get("mark_schema", 0))

    @property
    def locale(self) -> str:
        return str(self.data.get("locale", "en"))

    @property
    def state_dir(self) -> Path:
        rel = self.data.get("paths", {}).get("state_dir", ".mark")
        return self.root / rel


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
