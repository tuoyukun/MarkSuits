"""Per-worktree ports: every new worktree gets its own slot in each `[worktree] ports` range.

The slot is written to the worktree's `.env` (`NAME=base+slot`), and those `.env` files are
the ledger: a slot is taken while some other worktree's `.env` holds a port in it. A slot is
also skipped while any of its ports already has a listener, which catches servers this
repository knows nothing about (another project, a stray dev server).
"""
from __future__ import annotations

import fcntl
import re
import socket
import zlib
from contextlib import contextmanager
from pathlib import Path

from .config import MarkConfig
from .gitutil import worktrees

ENV_FILE = ".env"
_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


class NoFreePorts(Exception):
    pass


def read_env(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    out = {}
    for line in text.splitlines():
        m = _LINE_RE.match(line)
        if m:
            out[m.group(1)] = m.group(2).strip("'\"")
    return out


def write_env(path: Path, values: dict[str, str]) -> None:
    """Set `values` in a `.env`, keeping every other line as it is."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    out: list[str] = []
    done: set[str] = set()
    for line in lines:
        m = _LINE_RE.match(line)
        key = m.group(1) if m else None
        if key in values:
            if key not in done:  # first occurrence takes the new value, later duplicates go
                out.append(f"{key}={values[key]}")
                done.add(key)
            continue
        out.append(line)
    out += [f"{k}={v}" for k, v in values.items() if k not in done]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def slots_in(cfg: MarkConfig, env: dict[str, str]) -> set[int]:
    """Slots this `.env` holds; a mismatched one can hold a different slot per range."""
    out = set()
    for name, base in cfg.worktree_ports.items():
        value = env.get(name, "")
        if value.isdigit() and base <= int(value) < base + cfg.worktree_port_slots:
            out.add(int(value) - base)
    return out


def in_use(port: int) -> bool:
    """Something listens on localhost (IPv4 or IPv6, as a dev server may bind either)."""
    try:
        socket.create_connection(("localhost", port), timeout=0.3).close()
        return True
    except OSError:
        return False


@contextmanager
def _locked(cfg: MarkConfig):
    # Two dispatches at once would each read the same ledger and hand out the same slot.
    lock = cfg.state_dir / "locks" / "ports.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open("a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield


def assign(cfg: MarkConfig, wt: Path) -> dict[str, int]:
    """Give `wt` a free slot and write its ports to `wt/.env`. Raises NoFreePorts."""
    ranges, slots = cfg.worktree_ports, cfg.worktree_port_slots
    me = wt.resolve()
    with _locked(cfg):
        taken: set[int] = set()
        for path, _ in worktrees(cfg.root)[1:]:
            if path != me:
                taken |= slots_in(cfg, read_env(path / ENV_FILE))
        start = zlib.crc32(wt.name.encode()) % slots  # stable start: a worktree's slot rarely moves
        for i in range(slots):
            slot = (start + i) % slots
            ports = {name: base + slot for name, base in ranges.items()}
            if slot in taken or any(in_use(p) for p in ports.values()):
                continue
            write_env(wt / ENV_FILE, {k: str(v) for k, v in ports.items()})
            return ports
    raise NoFreePorts()
