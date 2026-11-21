"""Append-only, hash-chained decision log (JSONL). Each line commits to the previous one, so edits are detectable."""
from __future__ import annotations

import fcntl
import hashlib
import json
import time
from pathlib import Path


class Journal:
    """Several processes append to the same file (the bot, and review.py's `tune` line), so the chain head is
    re-read from disk under an exclusive lock on every append; an in-memory head would go stale and fork."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        self.prev = _tail_hash(path)

    def log(self, kind: str, **data) -> dict:
        with self.path.open("a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                prev = _tail_hash(self.path)
                rec = {"ts": int(time.time() * 1000), "kind": kind, **data, "prev": prev}
                rec["hash"] = hashlib.sha256(json.dumps(rec, sort_keys=True, default=str).encode()).hexdigest()
                f.write(json.dumps(rec, default=str) + "\n")
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        self.prev = rec["hash"]
        return rec


def _tail_hash(path: Path) -> str:
    """Hash of the last record in the file (the genesis value for an empty file)."""
    if not path.exists() or not path.stat().st_size:
        return "0" * 64
    with path.open("rb") as f:
        f.seek(max(0, path.stat().st_size - 65536))
        lines = [x for x in f.read().splitlines() if x.strip()]
    return json.loads(lines[-1])["hash"] if lines else "0" * 64


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def verify(path: Path, with_forks: bool = False):
    """Check the hash chain. Returns (ok, n) — n is the record count, or the first bad line when not ok.

    A "fork" is two consecutive records that both name the same parent (a concurrent writer appended between the
    other writer's read of the head and its own write, the bug fixed in Journal.log). Both records are present and
    each hashes correctly, so nothing is missing or altered; it is reported, not treated as a break. A deleted or
    edited record still breaks the chain. with_forks=True returns (ok, n, fork_lines)."""
    prev, prev2 = "0" * 64, None
    forks = []
    rows = read(path)
    for i, r in enumerate(rows):
        h = r.pop("hash")
        if hashlib.sha256(json.dumps(r, sort_keys=True, default=str).encode()).hexdigest() != h:
            return (False, i, forks) if with_forks else (False, i)
        if r["prev"] != prev:
            sibling = i >= 1 and prev2 is not None and r["prev"] == prev2 and rows[i - 1]["prev"] == prev2
            if not sibling:
                return (False, i, forks) if with_forks else (False, i)
            forks.append(i)
        prev2, prev = prev, h
    return (True, len(rows), forks) if with_forks else (True, len(rows))
