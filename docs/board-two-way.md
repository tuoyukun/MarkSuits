# Board two-way: deciding gates from the board

Status: phase 0.47 (deciding) implemented; 0.48–0.49 proposed. Agreed: a new `/mark:continue`; the `[board]` switches
default on; the token hole was fixed on its own (v0.46.1). Experiments below were run on
2026-11-09 with Claude Code 2.1.319 on macOS.

## 1. Goal

When a ticket waits on the human (`review-*`, `blocked-*`, opening not yet approved), the human
reads its documents on the board, decides there, and Mark carries on to the next gate **without
the human typing in a terminal**.

Out of scope: opening tickets, editing documents, merging, `/mark:general` from the board.
`/mark:approve` and `/mark:reject` in the terminal stay as they are; whichever comes first wins.

## 2. What the experiments showed

| Question | Result |
|---|---|
| Does a background Bash task that exits wake an idle session? | Yes. The wake message is marked "system notification, not user input" |
| Does `claude -p` load plugin hooks? | Yes; guards apply |
| Does `claude -p` fire `UserPromptSubmit`? | Yes (since v0.46.1 Mark records no token there: `CLAUDE_CODE_SESSION_ATTENDED=0`) |
| Can `claude -p` run a `disable-model-invocation` skill? | Yes |
| Prompting tool calls in the default permission mode | Denied at once, listed in `permission_denials`; never hangs |
| `--permission-mode auto` | Works as auto does in the terminal |
| Session markers | `-p`: `CLAUDE_CODE_ENTRYPOINT=sdk-cli`, `CLAUDE_CODE_SESSION_ATTENDED=0`; interactive: `cli`, `1` |
| Background agents under `claude -p` (v0.28 live run) | Killed when the session exits; dispatch in the foreground |

## 3. Design

Deciding and continuing are separate:

```
             ┌──────── decide (trusted, no model) ────────┐
 browser ──POST + secret──> board server ──> token → flow.approve / flow.reject → commit + push
                                                 │
             ┌──────── continue (model) ─────────┴────────────────────┐
             │ a live `mark wait`?                                     │
             │   yes → it sees the status change and exits → session wakes │
             │   no  → the board starts `claude -p "/mark:continue <id>"`   │
             └──────────────────────────────────────────────────────────┘
```

The decision is complete inside the board server process, through the same code as the CLI. A
woken or newly started session only carries on; it holds no approval power. Neither the wake
message nor a headless prompt counts as human consent.

## 4. Deciding: the board's write path

### 4.1 Endpoint

- `POST /api/decide`, JSON:
  - `{"ticket": "0012", "verb": "approve", "to": "developing"?, "answer": "…"?}`
  - `{"ticket": "0012", "verb": "reject", "items": ["…", "…"], "to": "planning"?}`
- Server:
  1. Checks Host (exists), `Origin` = the board itself, `Content-Type: application/json`, and the
     session cookie (4.2).
  2. Writes a token in `human.record`'s format plus `"source": "board"`.
  3. Runs what `cmd_approve` / `cmd_reject` run (`flow.approve` / `flow.reject`, commit, push) and
     returns any refusal to the page as is.
- Reject items come from the form one per field; no model splits them.
- Existing rules hold: `blocked-unclear` needs an answer; `to` must be in `flow.approve_targets`.

### 4.2 Keeping the model out: a session secret

Threat: the orchestrator has Bash and can `curl 127.0.0.1:6275/api/decide`.

- The board server (`serve()` in `board.py`) makes a random secret when it starts. It lives in
  memory only: never written, never printed. A restart (`--stop`, replacement after a plugin
  update, reboot) voids it.
- The server itself calls `webbrowser.open("http://127.0.0.1:<port>/#k=<key>")`, on start and
  on `POST /api/open`, with a fresh one-time key each time. The page trades the key for an
  `HttpOnly; SameSite=Strict` cookie holding the secret and drops `#k` from the address bar, so a
  URL left in the browser history is spent.
- `mark board` (which the model may run) only asks the server to open the browser again; the
  response carries no secret. The model can pop the board up on the human's screen but never
  sees the secret.
- Without the cookie the page stays read-only and the decision panel says to use the window
  `mark board` opened.

Residual risk: a model that deliberately reads the browser's cookie store or history. That is
the same level as the token directory today (name-based guards stop a model straying, not a
targeted attack); the architecture doc says so.

## 5. Continuing

### 5.1 Terminal session still open: `mark wait`

- `mark wait` blocks until any ticket that waits on the human changes status (or `--stop`),
  prints e.g. `0012: review-plan -> developing (board)` and exits.
- It writes `<state>/locks/wait.json` (pid); the board uses it to see a live waiter.
- `rules/orchestrator.md`: at a human gate, start `mark wait` in the background and end the
  turn; when woken, run `mark next` and loop to the next gate. Being woken is not consent.
- One `mark wait` per session covers every ticket.
- An approval typed in the terminal also ends `mark wait`; the woken session finds the work
  already moving and does nothing.

### 5.2 Terminal session closed: the board starts a headless session

- When: the decision succeeded and `wait.json` is missing or its pid is dead.
- Command (clean environment, main checkout as cwd):
  `claude -p "/mark:continue <id>" --permission-mode auto --output-format stream-json --verbose`
- `/mark:continue <id>` (new skill, features and bugs): loop to the next human gate or a stop, as
  `/mark:approve` step 5 does, with agents and `mark merge` in the **foreground**
  (`claude -p` kills background agents).
- One runner per project: `<state>/locks/runner.json` `{pid, ticket, log, started}`.
- Log: `<state>/locks/run-<id>-<time>.jsonl` (`locks/` is gitignored).
- On exit, read the last `result` event:
  - `permission_denials` not empty → the ticket shows "blocked: `<command>` needs approval";
  - `is_error` → "run failed" with the result text;
  - otherwise nothing: the ticket rests at its next gate.

### 5.3 Board page

- **Decision panel** in the ticket modal, only while the ticket waits on the human:
  - `review-*`: approve / reject (add and remove comment items);
  - `blocked-*`: target status (from `approve_targets`) and an answer;
  - opening not approved: approve opening.
- **Run panel**: the running session (ticket, start time), a trimmed live log (agent dispatches,
  `mark` commands, results), a stop button (`POST /api/stop`, with the secret; SIGTERM to the
  process group).
- Card badges: waiting on you / running / blocked.

## 6. Experiments left before implementing

1. Is a background Bash task (`mark merge`) killed when `claude -p` exits, like background agents?
2. Under `-p` + auto, are subagents' writes and test runs allowed? (One real feature chain.)
3. Does `--output-format stream-json` need `--verbose`; the event format.

## 7. Config (`.mark/config.toml`, with defaults; no `mark_schema` bump)

```toml
[board]
decide = true            # decide on the board; false keeps it read-only
run = "auto"             # "auto": start a headless session when no waiter; "off": decide only
permission_mode = "auto" # for the headless session
```

## 8. Phases

| Version | Content | Continues without the terminal? |
|---|---|---|
| 0.46.1 ✅ | nested `claude -p` token hole closed | — |
| 0.47 ✅ | decide endpoint, secret, decision panel | No: say "continue" in the terminal |
| 0.48 | `mark wait`, orchestrator rule change | Yes, while a terminal session is open |
| 0.49 | headless runner, `/mark:continue`, run panel | Yes, with no session open |

Each phase ships tests (rule 9): secret and Origin checks, token `source`, a bad target status
refused, runner lock, `mark wait` exit conditions, denial parsing.

## 9. Risks

- **Unattended token spend and code changes**: Mark already works unattended between gates and
  the hooks still apply; there is a stop button and `run = "off"`.
- **A terminal session is open but has no `mark wait`** (the human is chatting about something
  else): the board would start a second session. The dedup lock and brief guard stop a double
  dispatch, but both sessions might commit. Mitigation: each session writes a `session.json`
  heartbeat; the board starts nothing while one is live and points the human to the terminal.
- **Claude Code changes**: the wake mechanism and `-p` hook and permission behaviour are not
  documented guarantees. Each phase adds a manual smoke checklist outside CI.
