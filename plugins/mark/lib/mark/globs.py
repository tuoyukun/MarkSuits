"""Path globs matched segment by segment.

- `*` and `?` never cross `/` (unlike fnmatch, where `*` matches `a/b/c`).
- `**` matches zero or more whole segments, so `**/design.md` also matches a
  top-level `design.md`, and `src/**` matches `src/a/b.ts`.
"""
from __future__ import annotations

from fnmatch import fnmatchcase
from functools import lru_cache


def match(pattern: str, path: str) -> bool:
    return _match(tuple(_split(pattern)), tuple(_split(path)))


def _split(p: str) -> list[str]:
    return [s for s in p.replace("\\", "/").strip("/").split("/") if s and s != "."]


@lru_cache(maxsize=4096)
def _match(pat: tuple[str, ...], parts: tuple[str, ...]) -> bool:
    if not pat:
        return not parts
    head, rest = pat[0], pat[1:]
    if head == "**":
        return any(_match(rest, parts[i:]) for i in range(len(parts) + 1))
    return bool(parts) and fnmatchcase(parts[0], head) and _match(rest, parts[1:])
