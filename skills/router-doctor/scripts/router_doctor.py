#!/usr/bin/env python3
"""Router Doctor: read-only home Wi-Fi diagnosis.

Measures the link to the router vs the internet, scans nearby networks for
channel congestion and writes a JSON report with a verdict. It never logs into
or changes the router; that happens in the agent workflow (SKILL.md), one
approved change at a time.

  python router_doctor.py diagnose --out router_report.json
  python router_doctor.py keychain-cmd --user admin
"""
import argparse
import json
import platform
import re
import socket
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone

INTERNET_HOST = "1.1.1.1"
DNS_PROBE = "example.com"
CHANNELS_24 = (1, 6, 11)
CHANNELS_5 = (36, 40, 44, 48, 149, 153, 157, 161)  # non-DFS
KEYCHAIN_SERVICE = "router-doctor"

# Verdict thresholds (ms / %). Defaults, not calibrated per home.
GW_MAX_MS, GW_MAX_JITTER, MAX_LOSS = 20.0, 15.0, 2.0
NET_MAX_MS, NET_MAX_JITTER, DNS_MAX_MS = 80.0, 30.0, 150.0


# ---------- parsing (pure, tested) ----------

def parse_ping(text):
    """Round-trip times in ms from ping output (Linux, macOS, Windows)."""
    rtts = []
    for m in re.finditer(r"time([=<])\s*([\d.]+)\s*ms", text):
        rtts.append(float(m.group(2)) if m.group(1) == "=" else 0.5)
    return rtts


def link_stats(rtts, sent):
    """Median, jitter (mean |Δ| between consecutive replies) and loss %."""
    loss = 100.0 * (sent - len(rtts)) / sent if sent else 100.0
    if not rtts:
        return {"median_ms": None, "jitter_ms": None, "loss_pct": round(loss, 1)}
    diffs = [abs(b - a) for a, b in zip(rtts, rtts[1:])]
    return {
        "median_ms": round(statistics.median(rtts), 1),
        "jitter_ms": round(statistics.mean(diffs), 1) if diffs else 0.0,
        "loss_pct": round(loss, 1),
    }


def band_of(channel, hint=""):
    if "6GHz" in hint or "6 GHz" in hint:
        return "6"
    return "2.4" if channel <= 14 else "5"


def _strength(signal):
    """0-1 from a percentage (0-100) or dBm (negative)."""
    if signal is None:
        return 0.5
    if signal < 0:
        return max(0.0, min(1.0, (signal + 100) / 70.0))
    return max(0.0, min(1.0, signal / 100.0))


def parse_nmcli(text):
    """`nmcli -t -f IN-USE,SSID,CHAN,SIGNAL dev wifi list` (SSID may contain \\:)."""
    nets = []
    for line in text.splitlines():
        parts = re.split(r"(?<!\\):", line.strip())
        if len(parts) < 4 or not parts[2].isdigit():
            continue
        ch = int(parts[2])
        nets.append({
            "ssid": parts[1].replace("\\:", ":"),
            "channel": ch,
            "band": band_of(ch),
            "signal": int(parts[3]) if parts[3].isdigit() else None,
            "current": parts[0].strip() == "*",
        })
    return nets


def parse_netsh(text):
    """`netsh wlan show networks mode=bssid` on Windows."""
    nets, ssid, sig = [], None, None
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"SSID \d+\s*:\s*(.*)", line)
        if m:
            ssid = m.group(1)
            continue
        m = re.match(r"Signal\s*:\s*(\d+)%", line)
        if m:
            sig = int(m.group(1))
            continue
        m = re.match(r"Channel\s*:\s*(\d+)", line)
        if m and ssid is not None:
            ch = int(m.group(1))
            nets.append({"ssid": ssid, "channel": ch, "band": band_of(ch),
                         "signal": sig, "current": False})
    return nets


def parse_system_profiler(data):
    """`system_profiler SPAirPortDataType -json` on macOS."""
    nets = []

    def add(n, current):
        raw = str(n.get("spairport_network_channel", ""))
        m = re.match(r"(\d+)", raw)
        if not m:
            return
        sig = None
        sm = re.match(r"(-?\d+)\s*dBm", str(n.get("spairport_signal_noise", "")))
        if sm:
            sig = int(sm.group(1))
        ch = int(m.group(1))
        nets.append({"ssid": n.get("_name", ""), "channel": ch, "band": band_of(ch, raw),
                     "signal": sig, "current": current})

    for item in data.get("SPAirPortDataType", []):
        for iface in item.get("spairport_airport_interfaces", []):
            cur = iface.get("spairport_current_network_information")
            if cur:
                add(cur, True)
            for n in iface.get("spairport_airport_other_local_wireless_networks", []):
                add(n, False)
    return nets


# ---------- analysis (pure, tested) ----------

def congestion(nets):
    """Interference score for each candidate channel, best first, per band.

    2.4 GHz channels overlap: a network on channel c also hits c±1..4 with
    decaying weight. 5 GHz candidates count only exact-channel neighbours.
    The user's own network is excluded.
    """
    others = [n for n in nets if not n.get("current")]
    out = {}
    for band, cands in (("2.4", CHANNELS_24), ("5", CHANNELS_5)):
        scores = {}
        for c in cands:
            s = 0.0
            for n in others:
                if n["band"] != band:
                    continue
                d = abs(n["channel"] - c)
                if band == "2.4" and d <= 4:
                    s += _strength(n["signal"]) * (1 - d / 5.0)
                elif band == "5" and d == 0:
                    s += _strength(n["signal"])
            scores[c] = round(s, 2)
        ranked = sorted(scores.items(), key=lambda kv: (kv[1], kv[0]))
        out[band] = {"scores": scores, "best": [c for c, _ in ranked[:3]]}
    cur = next((n for n in nets if n.get("current")), None)
    if cur and cur["band"] in out:
        b = out[cur["band"]]
        b["current_channel"] = cur["channel"]
        b["current_score"] = b["scores"].get(cur["channel"])
    return out


def verdict(gw, inet, dns_ms):
    """Where the slowness lives. The order matters: a bad Wi-Fi link explains everything after it."""
    def bad(s, max_ms, max_jit):
        return s["median_ms"] is None or s["loss_pct"] > MAX_LOSS or \
            s["median_ms"] > max_ms or (s["jitter_ms"] or 0) > max_jit
    if gw["median_ms"] is None and inet["median_ms"] is None:
        return "no_data"
    # Some routers drop ping; with the internet answering, judge on that alone.
    if gw["median_ms"] is not None and bad(gw, GW_MAX_MS, GW_MAX_JITTER):
        return "wifi_link"
    if bad(inet, NET_MAX_MS, NET_MAX_JITTER):
        return "isp_or_upstream"
    if dns_ms is None or dns_ms > DNS_MAX_MS:
        return "dns"
    return "healthy"


def recommendations(v, cong):
    recs = []
    if v == "no_data":
        return ["Neither the router nor the internet answered. Run this on a machine on the home network with ping available."]
    if v == "isp_or_upstream":
        recs.append("Router link is clean; slowness is upstream. Check the plan speed, modem and ISP status before touching Wi-Fi settings.")
    if v == "dns":
        recs.append("DNS lookups are slow; consider switching the router's DNS to a resolver the user chooses.")
    b24 = cong.get("2.4", {})
    cur = b24.get("current_channel")
    if cur is not None and b24["best"] and cur != b24["best"][0] and \
            (b24.get("current_score") or 0) > b24["scores"][b24["best"][0]] + 0.3:
        recs.append(f"2.4 GHz channel {cur} is crowded; channel {b24['best'][0]} is clearer.")
    b5 = cong.get("5", {})
    cur5 = b5.get("current_channel")
    if cur5 is not None and b5["best"] and cur5 != b5["best"][0] and \
            (b5.get("current_score") or 0) > b5["scores"][b5["best"][0]] + 0.3:
        recs.append(f"5 GHz channel {cur5} is shared; channel {b5['best'][0]} is clearer.")
    if v == "wifi_link" and cur is not None:
        recs.append("This device is on 2.4 GHz; if the router has 5 GHz, enable it or band steering and set 5 GHz width to 80 MHz.")
    if v == "wifi_link":
        recs.append("Then check the router's Wi-Fi mode (ax/ac, not b/g legacy) and security (WPA2/WPA3-AES, not TKIP).")
    return recs


# ---------- measurement (OS calls) ----------

def _run(cmd, timeout=40):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def gateway():
    sysname = platform.system()
    if sysname == "Linux":
        m = re.search(r"default via (\S+)", _run(["ip", "route", "show", "default"]))
    elif sysname == "Darwin":
        m = re.search(r"gateway:\s*(\S+)", _run(["route", "-n", "get", "default"]))
    else:
        m = re.search(r"Default Gateway[ .]*:\s*(\d+\.\d+\.\d+\.\d+)", _run(["ipconfig"]))
    return m.group(1) if m else None


def ping(host, count):
    flag = "-n" if platform.system() == "Windows" else "-c"
    return link_stats(parse_ping(_run(["ping", flag, str(count), host])), count)


def dns_ms(host=DNS_PROBE):
    t = time.perf_counter()
    try:
        socket.getaddrinfo(host, 443)
    except OSError:
        return None
    return round((time.perf_counter() - t) * 1000, 1)


def scan():
    sysname = platform.system()
    if sysname == "Linux":
        return parse_nmcli(_run(["nmcli", "-t", "-f", "IN-USE,SSID,CHAN,SIGNAL", "dev", "wifi", "list"]))
    if sysname == "Darwin":
        try:
            return parse_system_profiler(json.loads(_run(["system_profiler", "SPAirPortDataType", "-json"]) or "{}"))
        except ValueError:
            return []
    return parse_netsh(_run(["netsh", "wlan", "show", "networks", "mode=bssid"]))


def keychain_cmd(user, os_name=None):
    """Command the user runs themselves so the router password never enters the chat."""
    os_name = os_name or platform.system()
    if os_name == "Darwin":
        return f'security add-generic-password -s {KEYCHAIN_SERVICE} -a {user} -w'
    if os_name == "Linux":
        return f'secret-tool store --label="Router admin" service {KEYCHAIN_SERVICE} user {user}'
    return f'cmdkey /generic:{KEYCHAIN_SERVICE} /user:{user} /pass'


# ---------- CLI ----------

def diagnose(count):
    gw = gateway()
    gw_stats = ping(gw, count) if gw else link_stats([], count)
    net_stats = ping(INTERNET_HOST, count)
    d = dns_ms()
    nets = scan()
    cong = congestion(nets)
    v = verdict(gw_stats, net_stats, d)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "platform": platform.system(),
        "gateway": gw,
        "gateway_link": gw_stats,
        "internet_link": net_stats,
        "dns_ms": d,
        "networks_seen": len(nets),
        "current_network": next((n for n in nets if n.get("current")), None),
        "congestion": cong,
        "verdict": v,
        "recommendations": recommendations(v, cong),
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("diagnose", help="read-only network diagnosis")
    d.add_argument("--count", type=int, default=20)
    d.add_argument("--out", default="router_report.json")
    k = sub.add_parser("keychain-cmd", help="print the keychain command for the user to run")
    k.add_argument("--user", default="admin")
    a = p.parse_args(argv)
    if a.cmd == "keychain-cmd":
        print(keychain_cmd(a.user))
        return 0
    rep = diagnose(a.count)
    with open(a.out, "w") as f:
        json.dump(rep, f, indent=2)
    g, n = rep["gateway_link"], rep["internet_link"]
    print(f"verdict: {rep['verdict']} | router {g['median_ms']}ms ±{g['jitter_ms']} loss {g['loss_pct']}% "
          f"| internet {n['median_ms']}ms ±{n['jitter_ms']} loss {n['loss_pct']}% | dns {rep['dns_ms']}ms")
    for r in rep["recommendations"]:
        print(" -", r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
