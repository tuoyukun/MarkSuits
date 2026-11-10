#!/bin/bash
# Install Mark: Claude Code (if missing), the Mark plugin for your user, and on macOS the menu bar
# app that runs the board and keeps the plugin up to date. Safe to run again: it repairs.
#   curl -fsSL https://raw.githubusercontent.com/tuoyukun/MarkSuits/main/install.sh | bash
set -euo pipefail

say() { printf '\033[1m==> %s\033[0m\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }
export PATH="$HOME/.local/bin:$PATH"  # where Claude Code's installer puts `claude`

command -v git >/dev/null 2>&1 && git --version >/dev/null 2>&1 \
  || die "git is missing. On macOS run: xcode-select --install   then run this script again."

PY=""
for c in python3 python3.13 python3.12 python3.11; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    PY=$(command -v "$c"); break
  fi
done
[ -n "$PY" ] || die "Mark needs Python 3.11 or newer as python3 (for example: brew install python, or python.org)."
command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null \
  || printf 'Warning: `python3` on your PATH is older than 3.11; Mark hooks in Claude Code run `python3`.\n' >&2

if ! command -v claude >/dev/null 2>&1; then
  say "Installing Claude Code"
  curl -fsSL https://claude.ai/install.sh | bash
  command -v claude >/dev/null 2>&1 || die "claude is still not on PATH; open a new terminal and run this again."
fi

say "Installing the Mark plugin"
claude plugin marketplace add tuoyukun/MarkSuits --scope user </dev/null
claude plugin marketplace update marksuits </dev/null
claude plugin install mark@marksuits --scope user </dev/null
claude plugin update mark@marksuits --scope user </dev/null

ROOT=$("$PY" -c '
import json, os, pathlib
base = pathlib.Path(os.environ.get("CLAUDE_CONFIG_DIR") or pathlib.Path.home() / ".claude")
data = json.loads((base / "plugins" / "installed_plugins.json").read_text())["plugins"]["mark@marksuits"]
print(([e for e in data if e.get("scope") == "user"] or data)[0]["installPath"])')
[ -f "$ROOT/bin/mark" ] || die "the plugin did not install (no $ROOT/bin/mark)."

MARK_DIR=${MARK_HOME:-$HOME/.mark}
if [ "$(uname)" = "Darwin" ]; then
  say "Building the Mark menu bar app"
  "$PY" "$ROOT/bin/mark" app install
  # the app runs the board; open that one, not a second board the app would stop when it starts
  for _ in $(seq 1 30); do grep -q '"service"' "$MARK_DIR/board.json" 2>/dev/null && break; sleep 0.5; done
fi

say "Opening the board"
"$PY" "$ROOT/bin/mark" board || true
cat <<EOF

Done. On the board:
  - if the panel at the top lists anything, finish it there (a model to run on, ...)
  - New project: pick a directory and say what you are building; Claude sets Mark up with you
  - Add existing project: a repository that already uses Mark
Open the board again any time: the Mark menu bar icon > Open, or run: mark board
Uninstall: curl -fsSL https://raw.githubusercontent.com/tuoyukun/MarkSuits/main/uninstall.sh | bash
EOF
