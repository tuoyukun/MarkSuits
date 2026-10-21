#!/usr/bin/env python3
"""Copy an example project into a fresh git repository you can run Mark in.

    python3 examples/sandbox.py <dest> [--example todo]

Mark works on branches and worktrees and pushes to `origin`, so the example cannot run
inside this repository. This script copies it to <dest>, makes it a repository on `main`
with one commit, and adds a local bare repository (<dest>.origin.git) as `origin`.
Nothing outside <dest> and <dest>.origin.git is touched.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent / "plugins" / "mark"
IGNORE = shutil.ignore_patterns("node_modules", "test-results", "playwright-report", "__pycache__",
                                ".numbers", "locks", "worktrees")


def git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, stdout=subprocess.DEVNULL)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dest", type=Path)
    parser.add_argument("--example", default="todo")
    args = parser.parse_args(argv)

    src = HERE / args.example
    dest = args.dest.resolve()
    origin = dest.with_name(dest.name + ".origin.git")
    if not (src / ".mark" / "config.toml").is_file():
        print(f"no example named {args.example!r} in {HERE}", file=sys.stderr)
        return 2
    for path in (dest, origin):
        if path.exists():
            print(f"{path} already exists; pick another destination", file=sys.stderr)
            return 2

    shutil.copytree(src, dest, ignore=IGNORE)
    git(dest.parent, "init", "--bare", "--initial-branch", "main", str(origin))
    git(dest, "init", "--initial-branch", "main")
    git(dest, "add", "-A")
    git(dest, "commit", "-m", f"{args.example}: initial import from the Mark examples")
    git(dest, "remote", "add", "origin", str(origin))
    git(dest, "push", "-u", "origin", "main")

    print(f"Sandbox ready: {dest}  (origin: {origin})\n")
    print("Next:")
    print(f"  cd {dest}")
    print("  npm --prefix tests ci && npm --prefix tests exec playwright install chromium")
    print(f"  claude --plugin-dir {PLUGIN}")
    print("Then follow the walkthrough in examples/README.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
