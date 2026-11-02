"""Append-only, hash-chained decision log (JSONL). Each line commits to the previous one, so edits are detectable."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


class Journal:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.prev = "0" * 64
        if path.exists() and path.stat().st_size:
            with path.open("rb") as f:
                f.seek(max(0, path.stat().st_size - 65536))
                last = f.read().splitlines()[-1]
            self.prev = json.loads(last)["hash"]

    def log(self, kind: str, **data) -> dict:
        rec = {"ts": int(time.time() * 1000), "kind": kind, **data, "prev": self.prev}
        rec["hash"] = hashlib.sha256(json.dumps(rec, sort_keys=True, default=str).encode()).hexdigest()
        with self.path.open("a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        self.prev = rec["hash"]
        return rec


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def verify(path: Path) -> tuple[bool, int]:
    prev = "0" * 64
    rows = read(path)
    for i, r in enumerate(rows):
        h = r.pop("hash")
        if r["prev"] != prev or hashlib.sha256(json.dumps(r, sort_keys=True, default=str).encode()).hexdigest() != h:
            return False, i
        prev = h
    return True, len(rows)
