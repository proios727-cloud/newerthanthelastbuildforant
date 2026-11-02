"""Drex (Nace) decisions over HTTP: POST {base}/v1/systemone with calibrated probabilities.

Fails closed: any error raises DrexError and the bot takes no new trade on that candle.
"""
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

import requests

from config import ROOT

QUESTIONS_PATH = Path(os.environ.get("BOT_QUESTIONS", ROOT / "questions.json"))


class DrexError(RuntimeError):
    pass


def load_questions() -> dict:
    return json.loads(QUESTIONS_PATH.read_text())


def _api_key() -> str:
    key = (os.environ.get("NACE_API_KEY") or os.environ.get("DREX_API_KEY") or "").strip()
    if not key:
        raise DrexError("No NACE_API_KEY / DREX_API_KEY in the environment.")
    if any(not (33 <= ord(ch) <= 126) for ch in key):
        raise DrexError("API key contains non-ASCII characters (looks like the masked preview, not the full key).")
    return key


class Drex:
    def __init__(self, base: str, model: str, timeout: float = 30.0):
        self.url = base.rstrip("/") + "/v1/systemone"
        self.model = model
        self.timeout = timeout
        self.s = requests.Session()

    def decide(self, state, questions: dict, image: Path | None = None) -> dict:
        body = {"state": state, "questions": questions, "model": self.model}
        if image is not None:
            body["images"] = ["data:image/png;base64," + base64.b64encode(image.read_bytes()).decode()]
        headers = {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}
        last = None
        for attempt in range(3):
            try:
                r = self.s.post(self.url, json=body, headers=headers, timeout=self.timeout)
            except requests.RequestException as e:
                last = f"network: {e}"
            else:
                if r.status_code == 200:
                    return r.json()
                last = f"HTTP {r.status_code}: {r.text[:300]}"
                if r.status_code < 500 and r.status_code != 429:
                    break
            time.sleep(2 ** attempt)
        raise DrexError(last or "unknown error")


def top(answer: dict) -> tuple[str, float]:
    """(label, probability) for a choice answer."""
    probs = answer["probabilities"]
    label = max(probs, key=probs.get)
    return label, float(probs[label])
