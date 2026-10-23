#!/usr/bin/env bash
# Build the UI preview (src/ui/Preview.js, every S-N) as one self-contained HTML file:
#   bash preview.sh <out.html>
# Web build of the real components, script inlined, so it opens from disk offline. It is
# close to the device, not the same: design QA on the simulator decides.
set -euo pipefail
out=$(cd "$(dirname "${1:?usage: preview.sh <out.html>}")" && pwd)/$(basename "$1")
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
EXPO_PUBLIC_PREVIEW=1 npx expo export --platform web --output-dir "$tmp" > "$tmp.log" 2>&1 \
  || { cat "$tmp.log" >&2; exit 1; }
python3 - "$tmp" "$out" <<'PY'
import pathlib, re, sys
dist, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
html = (dist / "index.html").read_text(encoding="utf-8")
def inline(m):
    js = (dist / m.group(1).lstrip("/")).read_text(encoding="utf-8")
    return "<script>" + js.replace("</script", "<\\/script") + "</script>"
html = re.sub(r'<script src="([^"]+)"[^>]*></script>', inline, html)
html = re.sub(r'<link rel="icon"[^>]*>', "", html)
out.write_text(html, encoding="utf-8")
PY
echo "preview: $out"
