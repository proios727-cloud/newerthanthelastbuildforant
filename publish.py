"""Publish the nightly review to a `reviews` branch on GitHub so the nightly Claude session can read it.

Needs GITHUB_TOKEN (fine-grained, Contents: read/write on this one repo) and GITHUB_REPO (owner/name).
Silently skipped when either is unset.
"""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path

import requests

log = logging.getLogger("publish")
API = "https://api.github.com"
BRANCH = os.environ.get("GITHUB_REVIEWS_BRANCH", "reviews")


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}


def _ensure_branch(s, repo, tok):
    if s.get(f"{API}/repos/{repo}/branches/{BRANCH}", headers=_h(tok), timeout=15).status_code == 200:
        return
    default = os.environ.get("GITHUB_BOT_BRANCH", "regime-bot")
    sha = s.get(f"{API}/repos/{repo}/git/ref/heads/{default}", headers=_h(tok), timeout=15).json()["object"]["sha"]
    s.post(f"{API}/repos/{repo}/git/refs", headers=_h(tok), json={"ref": f"refs/heads/{BRANCH}", "sha": sha}, timeout=15).raise_for_status()


def put_file(s, repo, tok, path: str, content: bytes, msg: str):
    url = f"{API}/repos/{repo}/contents/{path}"
    cur = s.get(url, headers=_h(tok), params={"ref": BRANCH}, timeout=15)
    body = {"message": msg, "content": base64.b64encode(content).decode(), "branch": BRANCH}
    if cur.status_code == 200:
        body["sha"] = cur.json()["sha"]
    s.put(url, headers=_h(tok), json=body, timeout=30).raise_for_status()


def publish(files: dict[str, Path], day: str) -> bool:
    tok, repo = os.environ.get("GITHUB_TOKEN", "").strip(), os.environ.get("GITHUB_REPO", "").strip()
    if not tok or not repo:
        log.info("GITHUB_TOKEN/GITHUB_REPO not set; review not published")
        return False
    try:
        with requests.Session() as s:
            _ensure_branch(s, repo, tok)
            for dest, src in files.items():
                if src.exists():
                    put_file(s, repo, tok, dest, src.read_bytes(), f"review {day}: {dest}")
        return True
    except (requests.RequestException, KeyError) as e:
        log.warning("publish failed: %s", e)
        return False
