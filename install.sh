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

if [ "$(uname)" = "Darwin" ]; then
  say "Building the Mark menu bar app"
  "$PY" "$ROOT/bin/mark" app install
else
  say "Run \`$ROOT/bin/mark board\` (or /mark:board in Claude Code) to open the board."
fi

if ! claude auth status >/dev/null 2>&1; then
  say "Last step: sign in to Claude in a terminal:  claude auth login"
fi
say "Done. In a project, run /mark:init in Claude Code, or use New project on the board."
