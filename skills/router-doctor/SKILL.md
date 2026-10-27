---
name: router-doctor
description: Diagnose a slow or flaky home Wi-Fi network and, only with the user's per-change approval, tune the router through its own admin interface. Measures latency, jitter and loss to the router vs the internet, scans nearby networks for channel congestion, reads the router's current settings, and proposes fixes (channel, band, channel width, Wi-Fi mode, DNS) as an old→new plan. Use when the user says their Wi-Fi or internet is slow, laggy or dropping, asks to "check my router", "fix my Wi-Fi", "who's on my Wi-Fi", or shares a router photo/model, says Wi-Fi is "sometimes" or "inconsistently" slow, or mentions eero or another app-managed mesh. Must run on a machine on the user's home network (local Claude Code, not a cloud session). Diagnose-only by default.
---

# Router Doctor

Origin: a viral post (@0xCodila, Oct 20 2026) claiming Claude Code "reverse-engineered" a router and fixed slow Wi-Fi in 5 minutes. The real mechanism is ordinary: the agent uses the router's normal admin page or API from a machine on the LAN. This skill does the same job with the guardrails the post skipped.

## Hard rules
1. **Diagnose first, change nothing** until the user has read the diagnosis and asked for fixes.
2. **Password never in chat.** Store it in the OS keychain (`router_doctor.py keychain-cmd` prints the command for the user to run). Read it back at call time; never echo, log or commit it.
3. **Back up before the first write**: export the router config (or save every setting you'll touch, with its current value) to `router_backup_<timestamp>.json` beside the report.
4. **One change at a time, approved each time.** Show `setting: old → new` and why; apply only on an explicit yes; re-measure after each change; roll back if it got worse.
5. **Never touch**: admin password, firmware updates, port forwarding, UPnP, DMZ, remote management, DNS to unknown resolvers, or WAN/ISP credentials, unless the user asks for that specific change by name.
6. **Say when the router isn't the problem.** If latency to the gateway is clean but the internet is slow, it's the ISP, the plan or upstream. Say so and stop.

## Workflow
1. **Scope**: router make/model (a photo of the label works), ISP-supplied or own, mesh or single unit, the symptom, and which devices it affects. Mesh systems (eero, Google/Nest, Orbi app-mode) are usually cloud-managed with no local admin, so give app steps instead of scripting them (see **eero** below).
2. **Measure**: `python scripts/router_doctor.py diagnose --out router_report.json`
   - pings the gateway and 1.1.1.1 (latency, jitter, loss), times a DNS lookup, and scans nearby Wi-Fi (macOS `system_profiler`, Linux `nmcli`, Windows `netsh`).
   - reports a **verdict** (`wifi_link` / `isp_or_upstream` / `dns` / `healthy` / `no_data`) and channel congestion per band with the least-crowded alternatives. `no_data` means the script isn't on the home network: stop.
3. **Read the router (read-only)**: open `http://<gateway>` and identify the firmware (OpenWrt/LuCI `ubus`, ASUSWRT `appGet.cgi`, TP-Link, Netgear SOAP, ISP gateway). Read the current SSID band, channel, width, mode and connected clients. If there's no local admin, stop and give manual steps.
4. **Plan**: build a change list from the verdict plus the settings. Typical wins:
   - congested 2.4 GHz channel → move to 1/6/11, whichever is least used
   - 5 GHz off or devices stuck on 2.4 → enable band steering or a separate 5 GHz SSID
   - 20 MHz width on 5 GHz → 80 MHz (keep 20 MHz on 2.4)
   - legacy b/g-only or WPA/TKIP mode → ax/ac with WPA2/WPA3-AES
   - slow DNS → the user's choice of resolver
5. **Apply** under hard rules 3–4, re-run `diagnose` after each change, and finish with one line: `before → after` (gateway latency, jitter, loss, speed if measured).
6. **Optional chat control**: read-only queries ("who's on my Wi-Fi", "what channel am I on") are fine at any time. A reboot needs a yes each time.

## Intermittent problems ("sometimes it's fine")
A one-shot test misses on-and-off trouble. Run `python scripts/router_doctor.py watch --minutes 10` while the problem is happening. It pings the router and the internet every 2 s and reports `cause`:
- `wifi_link`: the router link spikes or drops at the same moments as the internet, so the cause is local Wi-Fi (band hopping, a far node, interference).
- `isp_or_upstream`: only the internet side spikes, so it's the line or the provider.
- `stable`: nothing caught. Run it again at the time of day it usually happens.

On Windows with no Python, have the user double-click `windows/Check-WiFi.bat`. It runs the same watch and spike rule, also logs band and signal every 10 s (band hopping is a common cause of drops on mesh), and saves `WiFi-Check-*.txt` to the Desktop for them to send back.

## eero (and other app-managed mesh)
eero has **no local admin page or API** and chooses channels automatically (eero 6, 6+, Pro 6/6E/7, and ISP-branded units). Steps 3–5 above don't apply, so nothing gets scripted against the router.
- Run `diagnose --router eero`: channel advice is dropped and recommendations become eero app steps.
- Read the model in the app (Settings → the eero). Wi-Fi speeds above ~500 Mbps suggest a 6+/Pro rather than a base eero 6.
- Highest-value checks in the app, done while the problem is happening: the device page (which eero, band, signal), the app's own speed test (eero vs ISP), "Optimize for conferencing and gaming", and the node count against the layout of the home.
- ISP-supplied eeros may have settings locked. When an option is missing, say the provider controls it and stop.
- The fix is usually placement or another node. Say so instead of hunting for a setting.

## Honesty rules
- Wi-Fi fixes can't beat the plan's speed. Compare the result against what the user pays for.
- One speed test is noise. Use the diagnose medians and repeat at least twice.
- If the firmware is unknown, say so. Don't guess endpoints by brute force against the router.
