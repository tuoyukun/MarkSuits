"""The model the board's headless sessions run on (runner and chat), set on the board.

The harness is always the Claude Code CLI. `<state>/locks/model.json` (gitignored, mode 600, only
the board writes it) holds one of:

    {"provider": "anthropic", "model": "opus"}       the CLI's own login; an alias or a full id
    {"provider": "custom", "model": "...", "base_url": "https://...", "api_key": "..."}
                                                      an Anthropic-compatible endpoint (DeepSeek ...)

Each new session reads it when it starts, so a change never touches a session in progress. A
chat pins the settings its first turn used (`chat.py`): later turns resume that conversation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .config import MarkConfig

FILE = "model.json"
DEFAULT = {"provider": "anthropic", "model": "opus"}
PROVIDERS = ("anthropic", "custom")
FIELD_MAX = 2048
ALIAS_VARS = ("ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
              "ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_FABLE_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL")
# Anthropic credentials and provider switches must not reach (or override) a custom endpoint.
DROPPED = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK",
           "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY")


def path(cfg: MarkConfig) -> Path:
    return cfg.state_dir / "locks" / FILE


def valid(data: object) -> bool:
    if not isinstance(data, dict) or data.get("provider") not in PROVIDERS:
        return False
    fields = [data.get("model")] + ([data.get("base_url"), data.get("api_key")] if data["provider"] == "custom" else [])
    if not all(isinstance(f, str) and f.strip() and len(f) <= FIELD_MAX and not any(c.isspace() for c in f)
               for f in fields):
        return False
    return data["provider"] == "anthropic" or data["base_url"].startswith(("https://", "http://"))


def load(cfg: MarkConfig) -> dict:
    try:
        data = json.loads(path(cfg).read_text())
    except (OSError, ValueError):
        return dict(DEFAULT)
    return data if valid(data) else dict(DEFAULT)


def write_private(p: Path, data: dict) -> None:
    """Write JSON readable by this user only (it may hold an API key)."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(data, fh)
        fh.write("\n")
    os.replace(tmp, p)


def save(cfg: MarkConfig, req: dict) -> tuple[bool, str]:
    """The board's form: (ok, why not). An empty api_key keeps the stored one."""
    if not isinstance(req, dict):
        return False, "bad request"
    provider = req.get("provider")
    data = {"provider": provider, "model": req.get("model")}
    if provider == "custom":
        key = req.get("api_key") or ""
        if not key:
            old = load(cfg)
            key = old.get("api_key", "") if old.get("provider") == "custom" else ""
        data |= {"base_url": req.get("base_url"), "api_key": key}
    if not valid(data):
        return False, "bad request"
    write_private(path(cfg), data)
    return True, ""


def public(data: dict) -> dict:
    """What the page may see: never the key."""
    return {"provider": data["provider"], "model": data["model"], "base_url": data.get("base_url", ""),
            "has_key": bool(data.get("api_key")), "label": label(data)}


def label(data: dict) -> str:
    if data["provider"] == "anthropic":
        return data["model"]
    host = data["base_url"].split("://", 1)[1].split("/", 1)[0]
    return f"{data['model']} @ {host}"


def launch(data: dict, env: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    """Extra `claude` arguments and the environment for a session on these settings."""
    args = [f"--model={data['model']}"]  # one argv item: a model name can never read as an option
    if data["provider"] == "anthropic":
        return args, env
    env = {k: v for k, v in env.items() if k not in DROPPED}
    env |= {"ANTHROPIC_BASE_URL": data["base_url"], "ANTHROPIC_AUTH_TOKEN": data["api_key"],
            "ANTHROPIC_MODEL": data["model"], **{v: data["model"] for v in ALIAS_VARS}}
    return args, env
