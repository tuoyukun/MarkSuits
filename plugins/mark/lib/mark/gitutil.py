"""Small, failure-tolerant git helpers.

Every helper answers "don't know" (None / empty / False) instead of raising, so
a broken git call never turns into a crashed hook. Callers decide whether
"don't know" means allow or block.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

TIMEOUT = 10


def git(args: list[str], cwd: str | Path) -> tuple[int, str]:
    try:
        p = subprocess.run(["git", "-C", str(cwd), *args],
                           capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return p.returncode, (p.stdout or "").strip()


def nearest_existing_dir(path: str | Path) -> Path:
    """Closest existing ancestor (a Write target and its parents may not exist yet)."""
    p = Path(os.path.abspath(path))
    while not p.is_dir() and p != p.parent:
        p = p.parent
    return p


def checkout_root(path: str | Path) -> Path | None:
    """Root of the checkout (main or worktree) that `path` belongs to."""
    code, out = git(["rev-parse", "--show-toplevel"], nearest_existing_dir(path))
    return Path(out).resolve() if code == 0 and out else None


def main_root(root: Path) -> Path:
    """The main checkout for `root`, even when `root` is a git worktree.

    Ticket state, claim markers, gates and locks are global to the repository,
    so they are always read from the main checkout. Falls back to `root`
    outside git or if the main checkout is not a Mark project.
    """
    code, common = git(["rev-parse", "--path-format=absolute", "--git-common-dir"], root)
    if code != 0 or not common:
        return root
    candidate = Path(common).resolve().parent
    if (candidate / ".mark" / "config.toml").is_file():
        return candidate
    return root


def current_branch(cwd: str | Path) -> str | None:
    code, out = git(["branch", "--show-current"], cwd)
    return out or None if code == 0 else None


def worktrees(cwd: str | Path) -> list[tuple[Path, str | None]]:
    """[(path, branch)] for every checkout; the main checkout is always first."""
    code, out = git(["worktree", "list", "--porcelain"], cwd)
    if code != 0:
        return []
    rows: list[tuple[Path, str | None]] = []
    path: str | None = None
    branch: str | None = None
    for line in out.splitlines() + [""]:
        if line.startswith("worktree "):
            path, branch = line[len("worktree "):], None
        elif line.startswith("branch "):
            branch = line[len("branch "):].removeprefix("refs/heads/")
        elif not line and path:
            rows.append((Path(path).resolve(), branch))
            path, branch = None, None
    return rows


def has_remote(cwd: str | Path, name: str = "origin") -> bool:
    code, out = git(["remote"], cwd)
    return code == 0 and name in out.split()


def ref_exists(cwd: str | Path, ref: str) -> bool:
    return git(["rev-parse", "--verify", "-q", f"{ref}^{{commit}}"], cwd)[0] == 0


def is_ancestor(cwd: str | Path, ancestor: str, descendant: str) -> bool:
    return git(["merge-base", "--is-ancestor", ancestor, descendant], cwd)[0] == 0


def patch_unique(cwd: str | Path, upstream: str, head: str) -> list[str]:
    """Commits on `head` whose patch is not in `upstream` (`git cherry` '+' lines)."""
    code, out = git(["cherry", upstream, head], cwd)
    if code != 0:
        return []
    return [line[2:] for line in out.splitlines() if line.startswith("+ ")]


def dirty_paths(cwd: str | Path, pathspec: str) -> list[str]:
    """Tracked-or-new paths with uncommitted changes under `pathspec`."""
    code, out = git(["status", "--porcelain", "--untracked-files=all", "--", pathspec], cwd)
    if code != 0:
        return []
    return [line[3:] for line in out.splitlines() if len(line) > 3]


def ahead_of(cwd: str | Path, local: str, remote: str) -> int:
    code, out = git(["rev-list", "--count", f"{remote}..{local}"], cwd)
    return int(out) if code == 0 and out.isdigit() else 0
