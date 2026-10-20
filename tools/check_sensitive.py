#!/usr/bin/env python3
"""Block commits that would leak sensitive data into this public repository.

Usage:
  python3 tools/check_sensitive.py            # scan all tracked + untracked-not-ignored files
  python3 tools/check_sensitive.py --staged   # scan staged content only (pre-commit)

Built-in patterns catch secrets and machine-specific paths. Add private terms
(internal project names, personal emails, hostnames) to `.sensitive-words`,
one per line; that file is gitignored so the terms themselves never get published.
Exit 1 on any finding.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORDS_FILE = REPO / ".sensitive-words"
SELF = Path(__file__).resolve()

# Patterns are assembled from pieces so this file does not flag itself.
_KEY = "PRIVATE" + " KEY"
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*" + _KEY + "-----")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("Anthropic/OpenAI style key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("credential assignment",
     re.compile(r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token)\b\s*[:=]\s*['\"][^'\"\s]{8,}['\"]")),
    ("absolute home path", re.compile(r"(?:/Users|/home)/[A-Za-z0-9._-]+/")),
    ("Windows home path", re.compile(r"[A-Za-z]:\\Users\\[A-Za-z0-9._-]+\\")),
]

EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
ALLOWED_EMAIL_DOMAINS = ("example.com", "example.org", "users.noreply.github.com", "anthropic.com")

FORBIDDEN_FILENAMES = re.compile(r"(^|/)(\.env(\..+)?|id_rsa|id_ed25519|.*\.pem|.*\.p12|.*\.key)$")
ALLOWED_FILENAMES = {".env.example"}


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout


def _private_words() -> list[str]:
    if not WORDS_FILE.is_file():
        return []
    return [w.strip() for w in WORDS_FILE.read_text(encoding="utf-8").splitlines()
            if w.strip() and not w.lstrip().startswith("#")]


def _files(staged: bool) -> list[str]:
    if staged:
        out = _git("diff", "--cached", "--name-only", "--diff-filter=ACMR")
    else:
        out = _git("ls-files", "--cached", "--others", "--exclude-standard")
    return [f for f in out.splitlines() if f]


def _content(path: str, staged: bool) -> str | None:
    try:
        raw = _git("show", f":{path}") if staged else (REPO / path).read_text(encoding="utf-8")
    except (subprocess.CalledProcessError, UnicodeDecodeError, OSError):
        return None  # binary or unreadable
    return raw


def scan(staged: bool) -> list[str]:
    findings: list[str] = []
    words = _private_words()
    word_res = [(w, re.compile(re.escape(w), re.IGNORECASE)) for w in words]
    for path in _files(staged):
        if (REPO / path).resolve() == SELF:
            continue
        name = Path(path).name
        if FORBIDDEN_FILENAMES.search(path) and name not in ALLOWED_FILENAMES:
            findings.append(f"{path}: forbidden file type")
            continue
        text = _content(path, staged)
        if text is None:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for label, pattern in PATTERNS:
                if pattern.search(line):
                    findings.append(f"{path}:{lineno}: {label}")
            for match in EMAIL.finditer(line):
                if not match.group(0).lower().endswith(ALLOWED_EMAIL_DOMAINS):
                    findings.append(f"{path}:{lineno}: email address")
            for word, pattern in word_res:
                if pattern.search(line):
                    findings.append(f"{path}:{lineno}: private term from .sensitive-words")
    return findings


def main() -> int:
    staged = "--staged" in sys.argv[1:]
    findings = scan(staged)
    if findings:
        print("Sensitive content found (not committed):", file=sys.stderr)
        for item in findings:
            print(f"  {item}", file=sys.stderr)
        print("Fix the lines above, or move private terms to gitignored files.", file=sys.stderr)
        return 1
    print("check_sensitive: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
