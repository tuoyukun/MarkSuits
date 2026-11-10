"""The model the board's headless sessions run on (runner and chat), set on the board.

The harness is always the Claude Code CLI. `MARK_HOME/model.json` (`home.py`; mode 600, only the
board writes it) holds named profiles and which one is in use, for every project on this machine:

    {"active": "DeepSeek", "profiles": [{"name": "Opus", <settings>}, {"name": "DeepSeek", <settings>}]}

where <settings> is one of:

    "provider": "anthropic", "model": "opus"         the CLI's own login; an alias or a full id
    "provider": "custom", "model": "...", "base_url": "https://...", "api_key": "..."
                                                      an Anthropic-compatible endpoint (DeepSeek ...)

A file holding bare settings (v0.54-v0.56) reads as one profile named after its label. Before
v0.58 the file was per project (`<state>/locks/model.json`): the first project read with no
global file yet seeds it.

Each new session reads it when it starts, so a change never touches a session in progress. A
chat pins the settings its first turn used (`chat.py`): later turns resume that conversation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import home
from .config import MarkConfig

FILE = "model.json"
DEFAULT = {"provider": "anthropic", "model": "opus"}
PROVIDERS = ("anthropic", "custom")
FIELD_MAX = 2048
NAME_MAX = 40
ALIAS_VARS = ("ANTHROPIC_DEFAULT_OPUS_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL",
              "ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_FABLE_MODEL", "CLAUDE_CODE_SUBAGENT_MODEL")
# Anthropic credentials and provider switches must not reach (or override) a custom endpoint.
DROPPED = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_USE_BEDROCK",
           "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY")


def path(cfg: MarkConfig | None) -> Path:
    """The global file; a project's pre-v0.58 file seeds it (cfg None: the board's home page)."""
    p = home.root() / FILE
    legacy = cfg.state_dir / "locks" / FILE if cfg is not None else None
    if not p.exists() and legacy is not None and legacy.is_file():
        try:
            write_private(p, json.loads(legacy.read_text()))
        except (OSError, ValueError):
            pass  # a broken old file: start from the default
    return p


def valid(data: object) -> bool:
    if not isinstance(data, dict) or data.get("provider") not in PROVIDERS:
        return False
    fields = [data.get("model")] + ([data.get("base_url"), data.get("api_key")] if data["provider"] == "custom" else [])
    if not all(isinstance(f, str) and f.strip() and len(f) <= FIELD_MAX and not any(c.isspace() for c in f)
               for f in fields):
        return False
    return data["provider"] == "anthropic" or data["base_url"].startswith(("https://", "http://"))


def settings(p: dict) -> dict:
    """A profile without its name: what a session runs on."""
    return {k: v for k, v in p.items() if k != "name"}


def good_name(name: object) -> bool:
    return isinstance(name, str) and 0 < len(name.strip()) <= NAME_MAX and name == name.strip() \
        and name.isprintable()


def store(cfg: MarkConfig | None) -> dict:
    """All profiles and the active name; a missing or broken file is the default alone."""
    try:
        data = json.loads(path(cfg).read_text())
    except (OSError, ValueError):
        data = None
    if valid(data):  # the old single-settings file
        data = {"active": label(data), "profiles": [{"name": label(data), **data}]}
    if isinstance(data, dict) and isinstance(data.get("profiles"), list):
        profiles = [p for p in data["profiles"] if isinstance(p, dict) and good_name(p.get("name"))
                    and valid(settings(p))]
        if profiles:
            names = [p["name"] for p in profiles]
            return {"active": data.get("active") if data.get("active") in names else names[0], "profiles": profiles}
    return {"active": DEFAULT["model"], "profiles": [{"name": DEFAULT["model"], **DEFAULT}]}


def load(cfg: MarkConfig) -> dict:
    """The active profile's settings."""
    s = store(cfg)
    return settings(next(p for p in s["profiles"] if p["name"] == s["active"]))


def write_private(p: Path, data: dict) -> None:
    """Write JSON readable by this user only (it may hold an API key)."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(data, fh)
        fh.write("\n")
    os.replace(tmp, p)


def save(cfg: MarkConfig | None, req: dict) -> tuple[bool, str]:
    """The board's form: (ok, why not). `action` is "use" or "delete" a profile by `name`, or else save
    one (and use it): `old` names the profile being edited, `name` defaults to the label, and an empty
    api_key keeps the edited profile's key."""
    if not isinstance(req, dict):
        return False, "bad request"
    s = store(cfg)
    names = [p["name"] for p in s["profiles"]]
    action, name = req.get("action"), req.get("name")
    if action in ("use", "delete"):
        if name not in names or (action == "delete" and len(names) == 1):
            return False, "bad request"
        if action == "use":
            s["active"] = name
        else:
            s["profiles"] = [p for p in s["profiles"] if p["name"] != name]
            if s["active"] == name:
                s["active"] = s["profiles"][0]["name"]
        write_private(path(cfg), s)
        return True, ""
    provider = req.get("provider")
    data = {"provider": provider, "model": req.get("model")}
    old = next((p for p in s["profiles"] if p["name"] == req.get("old")), None)
    if provider == "custom":
        key = req.get("api_key") or ""
        if not key and old and old["provider"] == "custom":
            key = old["api_key"]
        data |= {"base_url": req.get("base_url"), "api_key": key}
    if not valid(data):
        return False, "bad request"
    name = name or label(data)
    if not good_name(name) or (name in names and name != (old or {}).get("name") and req.get("old")):
        return False, "bad request"
    profile = {"name": name, **data}
    keep = [p for p in s["profiles"] if p["name"] not in (name, (old or {}).get("name"))]
    at = next((i for i, p in enumerate(s["profiles"]) if p["name"] in (name, (old or {}).get("name"))), len(keep))
    s["profiles"] = keep[:at] + [profile] + keep[at:]
    s["active"] = name
    write_private(path(cfg), s)
    return True, ""


def public(s: dict) -> dict:
    """What the page may see: never a key."""
    def one(p: dict) -> dict:
        return {"name": p["name"], "provider": p["provider"], "model": p["model"], "base_url": p.get("base_url", ""),
                "has_key": bool(p.get("api_key")), "label": label(p)}
    active = next(p for p in s["profiles"] if p["name"] == s["active"])
    return {"active": s["active"], "label": active["name"], "profiles": [one(p) for p in s["profiles"]]}


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
