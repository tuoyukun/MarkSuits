"""`mark upgrade`: bring a project's template files up to the installed plugin, on a general lane.

Each template file has three versions: the pristine copy from the last init or upgrade
(`.mark/.base/<path>.base`), the project's file, and a fresh render with the recorded answers.
`git merge-file` merges the template's change into the project's file; a clash is left as
conflict markers. The result is one commit on a general lane, `mark general merge` lands it
(and refuses conflict markers), `mark general drop --force` discards it.

A file the project deleted stays deleted; a file the template no longer ships is removed when
the project never changed it. A CLAUDE.md that existed before init has no base: the project
owns it and upgrades leave it alone. A .gitignore without a base only gains missing lines.
"""
from __future__ import annotations

import subprocess
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import general, scaffold
from .config import MarkConfig
from .flow import FlowError
from .gitutil import git


def _ver(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return ()


def recorded(root: Path) -> tuple[str, dict[str, str]] | None:
    """(version, answers) from `.mark/template.toml`, or None when there is no usable record."""
    try:
        data = tomllib.loads((root / scaffold.RECORD).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    if not isinstance(data.get("version"), str) or not isinstance(data.get("answers"), dict):
        return None
    return data["version"], {k: str(v) for k, v in data["answers"].items()}


def stale(root: Path) -> str | None:
    """The recorded template version when it is older than the plugin, else None."""
    rec = recorded(root)
    return rec[0] if rec and _ver(rec[0]) < _ver(scaffold.version()) else None


def _read(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.is_file() else None


def _merge3(ours: str, base: str, theirs: str, old: str, new: str) -> tuple[str, bool]:
    """(merged text, clean) via `git merge-file`."""
    with tempfile.TemporaryDirectory(prefix="mark-upgrade-") as d:
        paths = []
        for name, text in (("ours", ours), ("base", base), ("theirs", theirs)):
            p = Path(d) / name
            p.write_text(text, encoding="utf-8")
            paths.append(str(p))
        p = subprocess.run(["git", "merge-file", "-p", "-L", "project", "-L", f"template v{old}",
                            "-L", f"template v{new}", *paths], capture_output=True, text=True)
    if p.returncode < 0 or p.returncode > 127:
        raise FlowError("upgrade.merge_failed", error=p.stderr.strip())
    return p.stdout, p.returncode == 0


@dataclass
class Plan:
    old: str
    new: str
    answers: dict[str, str]
    writes: dict[str, str | None] = field(default_factory=dict)  # None deletes
    report: list[tuple[str, str]] = field(default_factory=list)  # (what, path)

    @property
    def conflicts(self) -> list[str]:
        return [rel for what, rel in self.report if what == "conflict"]


def plan(root: Path) -> Plan:
    """What an upgrade of the checkout at `root` would write; writes nothing."""
    rec = recorded(root)
    if rec is None:
        raise FlowError("upgrade.no_record", record=scaffold.RECORD)
    old, given = rec
    new = scaffold.version()
    if _ver(old) >= _ver(new):
        raise FlowError("upgrade.current", version=old, plugin=new)
    # Keys the recording plugin did not know get today's defaults.
    answers = scaffold.resolve({k: v for k, v in given.items() if k in scaffold.KEYS}, root)
    files = scaffold.render(answers)
    p = Plan(old, new, answers)
    on_disk = {b.relative_to(root / scaffold.BASE_DIR).as_posix()[:-len(".base")]
               for b in (root / scaffold.BASE_DIR).rglob("*.base")}

    for rel in sorted(set(files) | on_disk):
        theirs, base, ours = files.get(rel), _read(root / scaffold.base_path(rel)), _read(root / rel)
        if theirs is None:                                   # the template dropped this file
            p.writes[scaffold.base_path(rel)] = None
            if ours is not None and ours == base:
                p.writes[rel] = None
                p.report.append(("removed", rel))
            elif ours is not None:
                p.report.append(("orphaned", rel))
            continue
        if base is None:
            if rel in scaffold.KEPT and ours is not None:
                continue                                     # the project's own CLAUDE.md
            if rel in scaffold.MERGED and ours is not None:
                lines = scaffold.missing_lines(ours, theirs)
                if lines:
                    p.writes[rel] = scaffold.appended(ours, lines)
                    p.report.append(("updated", rel))
                continue
            base = ""                                        # no common ancestor
        if theirs == base:
            continue
        p.writes[scaffold.base_path(rel)] = theirs
        if ours is None and base:
            p.report.append(("deleted", rel))                # the project removed it: keep it gone
        elif ours is None or ours in (base, theirs):
            if ours != theirs:
                p.writes[rel] = theirs
                p.report.append(("added" if ours is None else "updated", rel))
        else:
            text, clean = _merge3(ours, base, theirs, old, new)
            p.writes[rel] = text
            p.report.append(("merged" if clean else "conflict", rel))
    p.writes[scaffold.RECORD] = scaffold.record_text(answers)
    return p


def run(cfg: MarkConfig) -> tuple[str, Path, Plan, list[tuple[str, dict]]]:
    """Open a general lane, write the upgrade there and commit it. Main is untouched."""
    plan(cfg.root)                                           # refuse before cutting a lane
    branch, wt, notes = general.new(cfg)
    try:
        p = plan(wt)
        for rel, text in p.writes.items():
            target = wt / rel
            if text is None:
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
        if git(["add", "-A", "--", *p.writes], wt)[0] != 0 or \
                git(["commit", "-q", "-m", f"chore: upgrade Mark v{p.old} -> v{p.new}"], wt)[0] != 0:
            raise FlowError("upgrade.git_failed", wt=str(wt))
    except FlowError:
        general.drop(cfg, branch, force=True)
        raise
    return branch, wt, p, notes
