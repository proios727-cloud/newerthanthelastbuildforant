#!/usr/bin/env python3
"""Generate charters/<seat-id>.md from desk.json so charters never drift from the config.

Usage:
  python scripts/gen_charters.py desk.json --out charters

Inputs/outputs come from `handoffs`; the "never" list comes from the seat's role.
Stdlib only.
"""
import argparse, json, pathlib

NEVER = {
    "router": [
        "Place, modify, or cancel an order. The PM routes work and holds the queue. The human executes.",
        "Override a Risk VETO. A vetoed idea can only come back as a new idea with new facts.",
        "Change the mode label (DEMO/PAPER/LIVE) without the gates to back it.",
    ],
    "scanner": [
        "Emit a signal without the data timestamp and source it was computed from.",
        "Spend the feed quota on symbols outside the pinned universe.",
        "Size, recommend, or preview a trade.",
    ],
    "intel": [
        "Emit a regime label without citing the data points behind it.",
        "Treat headlines as confirmed facts. Tag the source and time of every item.",
        "Size, recommend, or preview a trade.",
    ],
    "custom": [
        "Pass an idea forward without an invalidation level.",
        "Invent estimates, flows, or filings. If the data isn't retrieved, say 'unknown'.",
        "Size, recommend, or preview a trade.",
    ],
    "risk": [
        "Loosen a limit mid-session. Limit changes are made by the human, in desk.json, between sessions.",
        "PASS an idea while the drawdown halt is active.",
        "Let 'the thesis is strong' outweigh a hard limit.",
    ],
    "entry": [
        "Send any order to a broker or exchange. Build the preview only; the human types the approval word.",
        "Reuse a preview older than 5 minutes. Re-quote it instead.",
        "Size above the max size in the Risk PASS.",
    ],
    "exit": [
        "Send an exit order. Exits are previews as well; a stop exit escalates to the PM immediately.",
        "Widen a stop to avoid taking a loss.",
        "Average down into a position whose thesis is broken.",
    ],
    "reporter": [
        "Report a number that isn't in the ledger or a quoted feed. Use '—' instead.",
        "Omit vetoes, losses, or blockers from the receipt.",
        "Smooth, annualize, or extrapolate short-sample performance.",
    ],
}


def seat_name(ids, sid):
    return "Human" if sid == "human" else ids.get(sid, {}).get("name", sid)


def charter(cfg, seat, ids):
    ins = [h for h in cfg.get("handoffs", []) if h["to"] == seat["id"]]
    outs = [h for h in cfg.get("handoffs", []) if h["from"] == seat["id"]]
    stages = [f["stage"] for f in cfg.get("funnel", []) if f.get("seat") == seat["id"]]
    queue = [q["title"] for q in cfg.get("queue", []) if q.get("owner") == seat["id"]]
    L = [f"# {seat['name']} (`{seat['id']}`)", "",
         f"**Desk:** {cfg['name']} · **Role:** {seat['role']} · **Mode:** {cfg['mode']}", "",
         "## Mission", seat["task"], "",
         "## Trigger", seat["trigger"], "",
         "## Done when", seat["done"], ""]
    L += ["## Inputs"] + ([f"- `{h['key']}` from {seat_name(ids, h['from'])} (timeout {h['timeout']}). If it doesn't arrive: {h['on_failure']}." for h in ins] or ["- Scheduled trigger and desk state only."]) + [""]
    L += ["## Outputs"] + ([f"- `{h['key']}` to {seat_name(ids, h['to'])} (timeout {h['timeout']}). If it fails: {h['on_failure']}." for h in outs] or ["- Posts to the desk feed."]) + [""]
    if stages:
        L += ["## Funnel stages owned"] + [f"- {s}" for s in stages] + [""]
    if queue:
        L += ["## Open queue items"] + [f"- {q}" for q in queue] + [""]
    L += ["## Never"] + [f"- {n}" for n in NEVER.get(seat["role"], [])] + [
        f"- Anything irreversible. {cfg['coordinator']['go_line']}", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--out", default="charters")
    a = ap.parse_args()
    cfg = json.loads(pathlib.Path(a.config).read_text(encoding="utf-8"))
    ids = {s["id"]: s for s in cfg["seats"]}
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for s in cfg["seats"]:
        (out / f"{s['id']}.md").write_text(charter(cfg, s, ids), encoding="utf-8")
        print(f"wrote {out / (s['id'] + '.md')}")


if __name__ == "__main__":
    main()
