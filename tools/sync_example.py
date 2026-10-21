#!/usr/bin/env python3
"""Re-render the Mark template into an example project from its recorded answers.

    python3 tools/sync_example.py [examples/todo]

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
    root = Path(argv[0]) if argv else REPO / "examples" / "todo"
    answers = tomllib.loads((root / scaffold.RECORD).read_text(encoding="utf-8"))["answers"]
    files = scaffold.render(scaffold.resolve(answers, root))
    for rel, text in files.items():
        for target in ([] if rel in OWNED else [rel]) + [scaffold.base_path(rel)]:
            path = root / target
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
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
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
