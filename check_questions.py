"""Guardrail for nightly question rewrites. Exit 1 if questions.json drifts from the fixed contract.

Wording (instructions / criteria descriptions) may change. Question names, types and labels may not,
and the version must go up by exactly 1 versus the git HEAD copy.
"""
import json
import subprocess
import sys

CONTRACT = {
    "regime": {"regime": ("choice", ["TRENDING", "CHOPPY", "PANIC"])},
    "signal": {"take": ("noul", ["true", "false"]),
               "book_control": ("choice", ["BUYERS", "SELLERS", "BALANCED"]),
               "entry": ("choice", ["MARKET", "LIMIT", "WAIT"])},
}


def main() -> int:
    q = json.load(open("questions.json"))
    errs = []
    for group, qs in CONTRACT.items():
        if set(q.get(group, {})) != set(qs):
            errs.append(f"{group}: question names must be exactly {sorted(qs)}")
            continue
        for name, (typ, labels) in qs.items():
            item = q[group][name]
            if item.get("type") != typ:
                errs.append(f"{group}.{name}: type must stay {typ}")
            if sorted(item.get("criteria", {})) != sorted(labels):
                errs.append(f"{group}.{name}: labels must stay {labels}")
            if not isinstance(item.get("instructions"), str) or not item["instructions"].strip():
                errs.append(f"{group}.{name}: instructions must be non-empty text")
            if any(not isinstance(v, str) or len(v) > 600 for v in item.get("criteria", {}).values()):
                errs.append(f"{group}.{name}: each criterion must be text under 600 chars")
    if "--bump" in sys.argv:
        try:
            head = json.loads(subprocess.run(["git", "show", "HEAD:questions.json"], capture_output=True, text=True, check=True).stdout)
            if q["version"] != head["version"] + 1:
                errs.append(f"version must be {head['version'] + 1} (HEAD is {head['version']})")
        except subprocess.CalledProcessError:
            errs.append("cannot read HEAD:questions.json")
    for e in errs:
        print("FAIL", e)
    print("OK" if not errs else f"{len(errs)} problem(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
