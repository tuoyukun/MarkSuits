#!/usr/bin/env python3
"""Re-render the Mark template into an example project from its recorded answers.

    python3 tools/sync_example.py [examples/<name>]     (default: every example)

Overwrites every template file except the ones the project owns (CLAUDE.md, .gitignore),
rewrites the pristine copies under .mark/.base/ and the version in .mark/template.toml, and
removes files the template no longer ships (unless the example edited them).
Review the diff of the project-owned files by hand. tests/test_example.py fails until this
has been run after a template change.
"""
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "plugins" / "mark" / "lib"))

from mark import scaffold  # noqa: E402

OWNED = {"CLAUDE.md", ".gitignore"}


def main(argv: list[str]) -> int:
    roots = [Path(a) for a in argv] or sorted(p.parent.parent for p in (REPO / "examples").glob(f"*/{scaffold.RECORD}"))
    for root in roots:
        print(f"== {root.name}")
        sync(root)
    return 0


def sync(root: Path) -> None:
    answers = tomllib.loads((root / scaffold.RECORD).read_text(encoding="utf-8"))["answers"]
    answers = {k: v for k, v in answers.items() if k in scaffold.keys(answers.get("profile", "web-fullstack"))}  # keys a release dropped
    files = scaffold.render(scaffold.resolve(answers, root))
    for rel, text in files.items():
        for target in ([] if rel in OWNED else [rel]) + [scaffold.base_path(rel)]:
            path = root / target
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                scaffold.write_file(path, target, text)
                print("updated", target)
    base_dir = root / scaffold.BASE_DIR
    for base in sorted(base_dir.rglob("*.base")):
        rel = base.relative_to(base_dir).as_posix()[:-len(".base")]
        if rel in files:
            continue
        # The template no longer ships it: drop the copy, and the file unless the project edited it.
        own = root / rel
        if own.is_file() and own.read_text(encoding="utf-8") == base.read_text(encoding="utf-8"):
            own.unlink()
            print("removed", rel)
        elif own.is_file():
            print("kept (edited, now an override)", rel)
        base.unlink()
    (root / scaffold.RECORD).write_text(scaffold.record_text(scaffold.resolve(answers, root)), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
