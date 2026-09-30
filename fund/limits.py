"""risk/limits.yaml, read with a two-level `key: value` parser (stdlib only; the file stays that simple)."""
import pathlib

PATH = pathlib.Path(__file__).resolve().parent.parent / "risk" / "limits.yaml"


def _val(s):
    s = s.split("#", 1)[0].strip()
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return s


def load(path=PATH):
    out, sec = {}, None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        key, _, rest = line.strip().partition(":")
        if raw.startswith((" ", "\t")):
            out[sec][key] = _val(rest)
        elif rest.strip():
            out[key], sec = _val(rest), None
        else:
            out[key], sec = {}, key
    return out


def fund_drawdown(ks, navs, starts, dd_kill=None):
    """Track the whole paper fund (every book as a share of its start) and return a reason when it is dd_kill below peak.

    Books are weighted by starting NAV, so the $100k put book dominates; the kill switch state keeps the peak."""
    dd_kill = dd_kill if dd_kill is not None else load()["fund"]["dd_kill"]
    total = sum(navs[b] for b in navs) / sum(starts[b] for b in navs)
    ks["fund_peak"] = max(ks.get("fund_peak") or 1.0, total)
    dd = total / ks["fund_peak"] - 1
    ks["fund_dd"] = round(dd, 4)
    return f"fund {dd:.1%} below peak <= -{dd_kill:.0%}" if dd <= -dd_kill else None
