"""TypeSafe System One judgments shared by the fund, Kalshi and sportsbook desks.

Judgments are advisory inputs. They can add a veto, a label or a ranking signal; they never size,
approve or send an order — risk rules and the human approval word stay in code.

A question is data (primitive + instructions + criteria); state is a JSON object the question
references by backticked paths. `ask(client, state, questions)` sends independent questions over
one state together and returns {question_id: Answer}.

Clients:
  StubClient  — offline, deterministic, no network. Default in tests and whenever no key is set.
  HttpClient  — TypeSafe HTTP API. Needs TYPESAFE_API_KEY, TYPESAFE_LIVE=1 and network access to
                api.typesafe.ai; otherwise `from_env()` returns the stub.

Where JEV may sit (it reads untrusted text such as headlines): as an extra refusal on top of code
rules, never as the thing that authorizes an order. A wrong answer can cost a trade, never place one.
"""
import json
import os
import urllib.request
from dataclasses import dataclass, field

PRIMITIVES = ("choice", "noul", "score")


@dataclass(frozen=True)
class Question:
    id: str                    # for code only; not sent as meaning
    primitive: str             # choice | noul | score
    instructions: str          # the complete judgment, self-contained
    criteria: object = None    # choice: {option: definition}; score: [level descriptions low→high]; noul: str

    def __post_init__(self):
        if self.primitive not in PRIMITIVES:
            raise ValueError(f"primitive must be one of {PRIMITIVES}")
        if self.primitive in ("choice", "score") and not self.criteria:
            raise ValueError(f"{self.primitive} question {self.id} needs criteria")


@dataclass(frozen=True)
class Answer:
    value: object              # choice: option key; noul: bool; score: float 0..1 (probability-weighted level)
    probability: float         # noul: P(yes); choice: P(chosen); score: confidence
    distribution: dict = field(default_factory=dict)
    live: bool = False         # False when produced by the stub — callers must not act on stub answers

    def confident(self, threshold):
        return self.live and self.probability >= threshold


class StubClient:
    """Neutral, clearly-marked answers so the pipeline runs end to end without a key."""
    live = False

    def __init__(self, overrides=None):
        self.overrides = overrides or {}   # tests inject {question_id: Answer}

    def ask(self, state, questions):
        out = {}
        for q in questions:
            if q.id in self.overrides:
                out[q.id] = self.overrides[q.id]
            elif q.primitive == "noul":
                out[q.id] = Answer(False, 0.5)
            elif q.primitive == "choice":
                opts = list(q.criteria)
                p = 1 / len(opts)
                out[q.id] = Answer(opts[-1], p, {o: p for o in opts})
            else:
                out[q.id] = Answer(0.5, 0.0)
        return out


class HttpClient:
    """TypeSafe System One API, POST /v1/systemone (wire format per community docs; official docs are
    blocked from this environment, so the parser accepts only the documented shape and fails loudly).

    Request:  {"model": "jev-1.13.0", "state": "<text>", "questions": {id: {"type", "instructions", ...}}}
              choice → "criteria": {option: description}; score → "levels": [low → high]
    Response: {"answers": {id: {"type": "noul", "noul": p} |
                               {"type": "choice", "choice": k, "probabilities": {...}, "confidence": c} |
                               {"type": "score", "score": x, "probabilities": {...}, "confidence": c}}}
    """
    live = True
    DEFAULT_URL = "https://api.typesafe.ai/v1/systemone"
    DEFAULT_MODEL = "jev-1.13.0"   # pinned: never a floating alias like jev-latest

    def __init__(self, api_key, base_url=None, model=None, timeout=10):
        self.api_key, self.timeout = api_key, timeout
        self.base_url = (base_url or self.DEFAULT_URL).rstrip("/")
        self.model = model or self.DEFAULT_MODEL

    def payload(self, state, questions):
        qs = {}
        for q in questions:
            body = {"type": q.primitive, "instructions": q.instructions}
            if q.primitive == "choice":
                body["criteria"] = q.criteria
            elif q.primitive == "score":
                body["levels"] = list(q.criteria)
            elif q.criteria:
                body["instructions"] += " " + q.criteria
            qs[q.id] = body
        text = state if isinstance(state, str) else json.dumps(state, ensure_ascii=False, sort_keys=True)
        return {"model": self.model, "state": text, "questions": qs}

    @staticmethod
    def parse(body):
        out = {}
        for qid, a in (body.get("answers") or {}).items():
            t = a.get("type")
            if t == "noul":
                p = float(a["noul"])
                out[qid] = Answer(p >= 0.5, p, {"yes": p, "no": 1 - p}, live=True)
            elif t == "choice":
                probs = a.get("probabilities", {})
                out[qid] = Answer(a["choice"], float(probs.get(a["choice"], a.get("confidence", 0.0))), probs, live=True)
            elif t == "score":
                out[qid] = Answer(float(a["score"]), float(a.get("confidence", 0.0)), a.get("probabilities", {}), live=True)
            else:
                raise RuntimeError(f"judge: unknown answer type {t!r} for {qid}")
        return out

    def ask(self, state, questions):
        req = urllib.request.Request(
            self.base_url, data=json.dumps(self.payload(state, questions)).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return self.parse(json.loads(r.read()))


def from_env(env=os.environ):
    """Live client only when a key and an explicit opt-in are present. URL and model default to the
    documented endpoint and a pinned model; TYPESAFE_API_URL / TYPESAFE_MODEL override them."""
    key = env.get("TYPESAFE_API_KEY")
    if key and env.get("TYPESAFE_LIVE") == "1":
        return HttpClient(key, env.get("TYPESAFE_API_URL"), env.get("TYPESAFE_MODEL"))
    return StubClient()


def ask(client, state, questions):
    ids = [q.id for q in questions]
    if len(set(ids)) != len(ids):
        raise ValueError("question ids must be unique")
    answers = client.ask(state, questions)
    missing = set(ids) - set(answers)
    if missing:
        raise RuntimeError(f"judge returned no answer for {sorted(missing)}")
    return answers
