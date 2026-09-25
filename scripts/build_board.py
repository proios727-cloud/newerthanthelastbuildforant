#!/usr/bin/env python3
"""Validate a desk.json config and build the control-room board from the HTML template.

Usage:
  python build_board.py desk.json                      # validate only
  python build_board.py desk.json --out board.html     # validate + build
  python build_board.py desk.json --template path/to/desk-board.html --out board.html

Exit 1 with a readable list of problems if the config is invalid. Never renders a broken file.
Stdlib only.
"""
import argparse, json, pathlib, re, sys

MODES = {"DEMO", "PAPER", "LIVE"}
COLORS = {"green", "amber", "red", "blue", "violet"}
STATUSES = {"idle", "live", "waiting", "blocked", "done"}
ROLES = {"router", "scanner", "risk", "entry", "exit", "intel", "reporter", "custom"}
GATE_STATUS = {"open", "passed", "blocked"}
ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
MARKER = "/*__CONFIG__*/null"


def err(problems, msg):
    problems.append(msg)


def require(problems, obj, key, typ, where):
    if key not in obj:
        err(problems, f"{where}: missing '{key}'")
        return None
    v = obj[key]
    if typ is not None and not isinstance(v, typ):
        err(problems, f"{where}: '{key}' must be {typ.__name__}")
        return None
    return v


def validate(cfg):
    p = []
    if not isinstance(cfg, dict):
        return ["config must be a JSON object"]
    for k in ("name", "mission", "session", "domain"):
        require(p, cfg, k, str, "root")
    mode = require(p, cfg, "mode", str, "root")
    if mode and mode not in MODES:
        err(p, f"root: mode '{mode}' not in {sorted(MODES)}")

    co = require(p, cfg, "coordinator", dict, "root") or {}
    require(p, co, "name", str, "coordinator")
    brief = require(p, co, "brief", list, "coordinator") or []
    if not brief or not all(isinstance(b, str) and b.strip() for b in brief):
        err(p, "coordinator.brief must be a non-empty list of strings")
    require(p, co, "go_line", str, "coordinator")

    seats = require(p, cfg, "seats", list, "root") or []
    ids = set()
    if not seats:
        err(p, "seats: at least one seat is required")
    for i, s in enumerate(seats):
        w = f"seats[{i}]"
        if not isinstance(s, dict):
            err(p, f"{w}: must be an object"); continue
        sid = require(p, s, "id", str, w)
        if sid:
            if not ID_RE.match(sid):
                err(p, f"{w}: id '{sid}' must match {ID_RE.pattern}")
            if sid in ids:
                err(p, f"{w}: duplicate id '{sid}'")
            ids.add(sid)
        require(p, s, "name", str, w)
        role = require(p, s, "role", str, w)
        if role and role not in ROLES:
            err(p, f"{w}: role '{role}' not in {sorted(ROLES)}")
        color = require(p, s, "color", str, w)
        if color and color not in COLORS:
            err(p, f"{w}: color '{color}' not in {sorted(COLORS)}")
        st = require(p, s, "status", str, w)
        if st and st not in STATUSES:
            err(p, f"{w}: status '{st}' not in {sorted(STATUSES)}")
        require(p, s, "task", str, w)
        require(p, s, "done", str, w)
        require(p, s, "trigger", str, w)
    routers = [s for s in seats if isinstance(s, dict) and s.get("role") == "router"]
    if len(routers) != 1:
        err(p, f"seats: exactly one seat must have role 'router' (found {len(routers)})")

    tiles = require(p, cfg, "tiles", list, "root") or []
    if not 3 <= len(tiles) <= 5:
        err(p, "tiles: need 3–5 entries")
    for i, t in enumerate(tiles):
        w = f"tiles[{i}]"
        if not isinstance(t, dict):
            err(p, f"{w}: must be an object"); continue
        require(p, t, "label", str, w)
        if "value" not in t:
            err(p, f"{w}: missing 'value' (use \"—\" when nothing real exists)")
        tr = t.get("trend", "flat")
        if tr not in ("up", "down", "flat"):
            err(p, f"{w}: trend must be up|down|flat")

    funnel = cfg.get("funnel", [])
    if not isinstance(funnel, list):
        err(p, "funnel must be a list")
    else:
        for i, f in enumerate(funnel):
            w = f"funnel[{i}]"
            if not isinstance(f, dict):
                err(p, f"{w}: must be an object"); continue
            require(p, f, "stage", str, w)
            if "count" not in f:
                err(p, f"{w}: missing 'count' (number or null)")
            elif f["count"] is not None and not isinstance(f["count"], (int, float)):
                err(p, f"{w}: count must be a number or null")
            seat = f.get("seat")
            if seat is not None and seat not in ids:
                err(p, f"{w}: seat '{seat}' is not a seat id")

    for key, fields in (("queue", ("id", "title", "owner", "pct")), ("feed", ("t", "agent", "msg"))):
        items = require(p, cfg, key, list, "root") or []
        for i, it in enumerate(items):
            w = f"{key}[{i}]"
            if not isinstance(it, dict):
                err(p, f"{w}: must be an object"); continue
            for f in fields:
                if f not in it:
                    err(p, f"{w}: missing '{f}'")
            owner = it.get("owner") if key == "queue" else it.get("agent")
            if owner is not None and owner not in ids:
                err(p, f"{w}: '{owner}' is not a seat id")
            if key == "queue" and "pct" in it and not (isinstance(it["pct"], (int, float)) and 0 <= it["pct"] <= 100):
                err(p, f"{w}: pct must be 0–100")

    watch = require(p, cfg, "watch", list, "root") or []
    for i, wv in enumerate(watch):
        w = f"watch[{i}]"
        if not isinstance(wv, dict) or "label" not in wv or "value" not in wv:
            err(p, f"{w}: needs label and value (delta optional)")

    gates = cfg.get("gates", [])
    if not isinstance(gates, list):
        err(p, "gates must be a list")
    else:
        for i, g in enumerate(gates):
            w = f"gates[{i}]"
            if not isinstance(g, dict):
                err(p, f"{w}: must be an object"); continue
            require(p, g, "title", str, w)
            gs = g.get("status", "open")
            if gs not in GATE_STATUS:
                err(p, f"{w}: status must be open|passed|blocked")
        if gates and "approval_word" not in cfg:
            err(p, "gates present but root 'approval_word' missing — the last gate is the human's explicit word")

    handoffs = cfg.get("handoffs", [])
    if not isinstance(handoffs, list):
        err(p, "handoffs must be a list")
    else:
        for i, h in enumerate(handoffs):
            w = f"handoffs[{i}]"
            if not isinstance(h, dict):
                err(p, f"{w}: must be an object"); continue
            for f in ("from", "to", "key", "timeout", "on_failure"):
                if f not in h:
                    err(p, f"{w}: missing '{f}'")
            for f in ("from", "to"):
                if h.get(f) is not None and h.get(f) not in ids and h.get(f) != "human":
                    err(p, f"{w}: '{f}' = '{h.get(f)}' is not a seat id or 'human'")

    if cfg.get("mode") == "LIVE":
        blocked = [q for q in cfg.get("queue", []) if isinstance(q, dict) and str(q.get("title", "")).lower().startswith("blocker")]
        if blocked:
            err(p, "mode is LIVE but the queue still lists blockers — set PAPER or DEMO until they clear")
    return p


def build(cfg, template_path, out_path):
    tpl = pathlib.Path(template_path).read_text(encoding="utf-8")
    if MARKER not in tpl:
        raise SystemExit(f"template has no {MARKER} marker")
    payload = json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")
    html = tpl.replace(MARKER, payload, 1)
    title = cfg["name"]
    html = re.sub(r"<title>.*?</title>", f"<title>{title}</title>", html, count=1, flags=re.S)
    pathlib.Path(out_path).write_text(html, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--template", default=str(pathlib.Path(__file__).resolve().parent.parent / "assets" / "desk-board.html"))
    ap.add_argument("--out")
    a = ap.parse_args()
    try:
        cfg = json.loads(pathlib.Path(a.config).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"invalid JSON: {e}"); sys.exit(1)
    problems = validate(cfg)
    if problems:
        print(f"{len(problems)} problem(s) in {a.config}:")
        for pr in problems:
            print("  -", pr)
        sys.exit(1)
    n = len(cfg["seats"])
    print(f"ok: {cfg['name']} [{cfg['mode']}] — {n} seats, {len(cfg.get('queue', []))} queue, {len(cfg.get('feed', []))} feed, {len(cfg.get('gates', []))} gates")
    if a.out:
        build(cfg, a.template, a.out)
        print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
