#!/bin/bash
# Uninstall Mark: the menu bar app, its login item, the `mark` launcher and the Claude Code plugin.
# Keeps Claude Code, your projects (their .mark/ and code) and ~/.mark unless --purge is given.
#   curl -fsSL https://raw.githubusercontent.com/tuoyukun/MarkSuits/main/uninstall.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/tuoyukun/MarkSuits/main/uninstall.sh | bash -s -- --purge
set -uo pipefail

say() { printf '\033[1m==> %s\033[0m\n' "$*"; }
PURGE=""; [ "${1:-}" = "--purge" ] && PURGE=1
export PATH="$HOME/.local/bin:$PATH"
if [ "$(uname)" = "Darwin" ]; then
  MARK_DIR=${MARK_HOME:-$HOME/.mark}
else
  MARK_DIR=${MARK_HOME:-${XDG_DATA_HOME:-$HOME/.local/share}/mark}
fi

say "Stopping Mark"
osascript -e 'quit app id "com.marksuits.mark"' >/dev/null 2>&1 || true
pkill -f "/Mark.app/Contents/MacOS/Mark" >/dev/null 2>&1 || true
PID=$(sed -n 's/.*"pid": *\([0-9]*\).*/\1/p' "$MARK_DIR/board.json" 2>/dev/null)
[ -n "$PID" ] && kill "$PID" 2>/dev/null || true

say "Removing the menu bar app, its login item and the mark command"
rm -rf "$HOME/Applications/Mark.app" "$HOME/Library/LaunchAgents/com.marksuits.mark.plist"
# only our launcher: it names the Mark plugin it runs
grep -q "Mark plugin" "$HOME/.local/bin/mark" 2>/dev/null && rm -f "$HOME/.local/bin/mark"

if command -v claude >/dev/null 2>&1; then
  say "Removing the Mark plugin from Claude Code"
  claude plugin uninstall mark@marksuits --scope user </dev/null || true
  claude plugin marketplace remove marksuits </dev/null || true
fi

if [ -n "$PURGE" ]; then
  say "Removing $MARK_DIR"
  rm -rf "$MARK_DIR"
  echo "Done."
else
  cat <<MSG
Done. Kept: Claude Code, your projects, and $MARK_DIR
(the project list, model profiles with their API keys, board logs). To remove it too:
  rm -rf "$MARK_DIR"
MSG
fi
