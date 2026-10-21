---
name: router-doctor
description: Diagnose a slow or flaky home Wi-Fi network and, only with the user's per-change approval, tune the router through its own admin interface. Measures latency, jitter and loss to the router vs the internet, scans nearby networks for channel congestion, reads the router's current settings, and proposes fixes (channel, band, channel width, Wi-Fi mode, DNS) as an old→new plan. Use when the user says their Wi-Fi or internet is slow, laggy or dropping, asks to "check my router", "fix my Wi-Fi", "who's on my Wi-Fi", or shares a router photo/model. Must run on a machine on the user's home network (local Claude Code, not a cloud session). Diagnose-only by default.
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
1. **Scope**: router make/model (a photo of the label works), ISP-supplied or own, mesh or single unit, the symptom, and which devices it affects. Mesh systems (eero, Google/Nest, Orbi app-mode) are usually cloud-managed with no local admin, so give app steps instead of scripting them.
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

## Honesty rules
- Wi-Fi fixes can't beat the plan's speed. Compare the result against what the user pays for.
- One speed test is noise. Use the diagnose medians and repeat at least twice.
- If the firmware is unknown, say so. Don't guess endpoints by brute force against the router.
