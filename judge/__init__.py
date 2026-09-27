"""TypeSafe System One judgments shared by the fund, Kalshi and sportsbook desks.

Judgments are advisory inputs. They can add a veto, a label or a ranking signal; they never size,
approve or send an order — risk rules and the human approval word stay in code.

A question is data (primitive + instructions + criteria); state is a JSON object the question
references by backticked paths. `ask(client, state, questions)` sends independent questions over
one state together and returns {question_id: Answer}.

Clients:
  StubClient  — offline, deterministic, no network. Default in tests and whenever no key is set.
  HttpClient  — TypeSafe HTTP API. Needs TYPESAFE_API_KEY and network access to the API host.
                The request/response mapping must be checked against https://docs.typesafe.ai/api.md
                before first live use; until then `from_env()` returns the stub.
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
    live = True

    def __init__(self, api_key, base_url, model="jev", timeout=10):
        self.api_key, self.base_url, self.model, self.timeout = api_key, base_url.rstrip("/"), model, timeout

    def payload(self, state, questions):
        return {
            "model": self.model,
            "state": state,
            "questions": [
                {"id": q.id, "type": q.primitive, "instructions": q.instructions,
                 **({"criteria": q.criteria} if q.criteria is not None else {})}
                for q in questions
            ],
        }

    def ask(self, state, questions):
        req = urllib.request.Request(
            self.base_url, data=json.dumps(self.payload(state, questions)).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            body = json.loads(r.read())
        return {a["id"]: Answer(a.get("value"), float(a.get("probability", 0.0)),
                                a.get("distribution", {}), live=True)
                for a in body.get("answers", [])}


def from_env(env=os.environ):
    """Live client only when a key, an endpoint and an explicit opt-in are all present."""
    key, url = env.get("TYPESAFE_API_KEY"), env.get("TYPESAFE_API_URL")
    if key and url and env.get("TYPESAFE_LIVE") == "1":
        return HttpClient(key, url)
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
