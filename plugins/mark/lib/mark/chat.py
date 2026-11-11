"""Board chat: talk a ticket through with Claude on the board, one headless turn per message.

Each message the human sends starts `claude -p` in the main checkout. The first opens the ticket's
skill (`/mark:feature <id>` or `/mark:fix <id>`) with the human's text; later ones `--resume` the
same session, so it is one conversation. The skill decides what happens, exactly as in a terminal:
a feature stops at its review gates, a bug runs its chain once the report is agreed.

Everything goes to `<state>/locks/chat-<id>.jsonl` (gitignored): each human message as a
`{"type": "human"}` line, then that turn's stream-json. `chat-<id>.json` holds the pid of the turn
in progress: one turn per ticket at a time. The prompt goes in on stdin, so no text the human
types can be read as a command-line option.

A turn is unattended (`CLAUDE_CODE_SESSION_ATTENDED=0`): nothing typed here counts as a human
command, and the human decides gates with the board's buttons. `mark wait` is refused in such a
session (`guards.bash.wait_guard`), so a turn ends when the session needs the human.

`claude -p` has no AskUserQuestion, so the note tells the session to put choice questions through
`mark ask` (`ask.py`); the board shows them as a form and the answers come back as a message.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from pathlib import Path

from . import ask, model, runner, states
from .config import MarkConfig

TEXT_MAX = 20000
BOARD_NOTE = (
    "This is a headless session: you are talking with the human through the Mark web board, not a "
    "terminal. They read your "
    "reply there and answer in their next message. They approve or reject gates with the board's "
    "buttons: point them there, not to /mark:approve or /mark:reject. When you need the human, "
    "end your turn; never start `mark wait`.\n"
    "AskUserQuestion does not exist here. To ask questions with choices (yes/no, pick one, pick "
    "several), pipe the JSON AskUserQuestion takes into `mark ask <ticket-id>` with a heredoc in one "
    "Bash call, then end your turn with a one-line reply; the board shows the questions as a form and "
    "the answers arrive as the human's next message:\n"
    "  mark ask <ticket-id> <<'EOF'\n"
    "  {\"questions\": [{\"question\": \"<one line>?\", \"header\": \"<12 chars>\", \"multiSelect\": false,\n"
    "    \"options\": [{\"label\": \"<short>\", \"description\": \"<what it means>\"}, ...]}]}\n"
    "  EOF\n"
    "1-4 questions, 2-4 options each; the human can always type their own answer, so add no \"Other\" "
    "option. If the heredoc is refused, write the JSON to a file and run `mark ask <ticket-id> <file>`. "
    "Ask open questions as plain text."
)


def log_path(cfg: MarkConfig, ticket_id: str) -> Path:
    return cfg.state_dir / "locks" / f"chat-{ticket_id}.jsonl"


def state_path(cfg: MarkConfig, ticket_id: str) -> Path:
    return cfg.state_dir / "locks" / f"chat-{ticket_id}.json"


def running(cfg: MarkConfig, ticket_id: str) -> int | None:
    """Pid of the turn in progress on this ticket, or None."""
    try:
        pid = json.loads(state_path(cfg, ticket_id).read_text()).get("pid")
    except (OSError, ValueError, AttributeError):
        return None
    return pid if runner._alive(pid) else None


def _events(cfg: MarkConfig, ticket_id: str) -> list[object]:
    """Every line of the log: a dict per JSON event, a str for anything else (stderr)."""
    try:
        # shortcut: reads the whole log on every view; tail it if chats grow to many MB
        lines = log_path(cfg, ticket_id).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out: list[object] = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            if line.strip():
                out.append(line.strip())
    return out


def session(cfg: MarkConfig, ticket_id: str) -> str | None:
    """The Claude session this ticket's chat resumes: the last one any turn reported."""
    sid = None
    for e in _events(cfg, ticket_id):
        if isinstance(e, dict) and e.get("type") in ("system", "result") and isinstance(e.get("session_id"), str):
            sid = e["session_id"]
    return sid


def settings_path(cfg: MarkConfig, ticket_id: str) -> Path:
    return cfg.state_dir / "locks" / f"chat-{ticket_id}.model.json"


def settings(cfg: MarkConfig, ticket_id: str, resuming: bool) -> dict:
    """The model this turn runs on: a resumed conversation keeps the one it started with, a new one
    takes the board's current setting and pins it."""
    if resuming:
        try:
            data = json.loads(settings_path(cfg, ticket_id).read_text())
            if model.valid(data):
                return data
        except (OSError, ValueError):
            pass  # a chat from before models were set: pin the current one
    data = model.load(cfg)
    model.write_private(settings_path(cfg, ticket_id), data)
    return data


def command(cfg: MarkConfig, sid: str | None, claude: str, extra: list[str] = (), note: str = BOARD_NOTE) -> list[str]:
    return [claude, "-p", *(["--resume", sid] if sid else []), "--append-system-prompt", note,
            "--permission-mode", cfg.board_permission_mode, *extra, "--output-format", "stream-json", "--verbose"]


def prompt(kind: str, ticket_id: str, text: str, first: bool) -> str:
    if not first:
        return text
    return f"/mark:{'feature' if kind == states.FEATURE else 'fix'} {ticket_id}\n\n{text}"


def start(cfg: MarkConfig, kind: str, ticket_id: str, text: str, claude: str | None = None,
          first: str | None = None, note: str = BOARD_NOTE) -> tuple[bool, str]:
    """Send one message: (started, why not). Never two turns on a ticket, nor a turn on a ticket
    the headless runner is carrying on. `first` replaces the opening prompt and `note` the system
    note (the new-project wizard, `wizard.py`, which has no ticket)."""
    if running(cfg, ticket_id) or runner.running(cfg, ticket_id):
        return False, "busy"
    claude = claude or runner.find_claude()
    if not claude:
        return False, "no-claude"
    sid = session(cfg, ticket_id)
    ask.clear(cfg, ticket_id)  # the human answered (or moved on): the form belonged to the last turn
    log = log_path(cfg, ticket_id)
    log.parent.mkdir(parents=True, exist_ok=True)
    pinned = settings(cfg, ticket_id, sid is not None)
    extra, env = model.launch(pinned, runner.clean_env())
    with open(log, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"type": "human", "text": text, "at": time.time()}, ensure_ascii=False) + "\n")
    with open(log, "ab") as fh:
        proc = subprocess.Popen(command(cfg, sid, claude, extra, note), cwd=cfg.root, env=env,
                                stdin=subprocess.PIPE, stdout=fh, stderr=subprocess.STDOUT,
                                start_new_session=True)  # its own group: stop ends what it started too
    state_path(cfg, ticket_id).write_text(json.dumps({"pid": proc.pid, "started": time.time()}) + "\n")
    try:
        opening = first if first is not None and sid is None else prompt(kind, ticket_id, text, sid is None)
        proc.stdin.write(opening.encode("utf-8"))
        proc.stdin.close()
    except OSError:
        pass  # it died at once; the log says why
    threading.Thread(target=proc.wait, daemon=True).start()  # reap it, so a finished turn reads as dead
    return True, ""


def stop(cfg: MarkConfig, ticket_id: str) -> bool:
    pid = running(cfg, ticket_id)
    if pid is None:
        return False
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        return False
    return True


def view(cfg: MarkConfig, ticket_id: str) -> dict[str, object]:
    """The conversation for the board: messages in order, and whether a turn is running.
    `who` is human, claude, step (a command or agent the session ran) or error."""
    msgs: list[dict[str, str]] = []
    pending = False  # a human message with no result after it yet
    for e in _events(cfg, ticket_id):
        if isinstance(e, str):
            if e.startswith(runner.HARMLESS):
                continue
            msgs.append({"who": "error", "text": e[:300]})
        elif e.get("type") == "human":
            msgs.append({"who": "human", "text": str(e.get("text") or "")})
            pending = True
        elif e.get("type") == "assistant":
            for c in (e.get("message") or {}).get("content") or []:
                if isinstance(c, dict) and c.get("type") == "text" and str(c.get("text") or "").strip():
                    msgs.append({"who": "claude", "text": c["text"]})
            msgs += [{"who": "step", "text": line.splitlines()[0][:200] if line else line} for line in runner._describe(e)]
        elif e.get("type") == "result":
            pending = False
            end = runner.outcome(e, False)
            if end["kind"] == "blocked":
                msgs.append({"who": "error", "text": "needs approval: " + "; ".join(map(str, end["commands"]))})
            elif end["kind"] == "failed":
                msgs.append({"who": "error", "text": str(end.get("text") or "failed")})
    live = running(cfg, ticket_id) is not None
    if pending and not live:
        msgs.append({"who": "error", "text": "the turn ended without a reply"})
    try:
        pinned = model.label(json.loads(settings_path(cfg, ticket_id).read_text()))
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        pinned = ""
    return {"running": live, "messages": msgs, "ask": None if live else ask.load(cfg, ticket_id), "model": pinned}
