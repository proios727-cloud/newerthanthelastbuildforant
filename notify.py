"""Phone pings via ntfy.sh (free app for iOS/Android; subscribe to your topic). Never raises."""
from __future__ import annotations

import logging

import requests

log = logging.getLogger("notify")


def ping(cfg, title: str, body: str, priority: str = "default"):
    if not cfg.ntfy_topic:
        return
    try:
        requests.post(f"{cfg.ntfy_base.rstrip('/')}/{cfg.ntfy_topic}", data=body.encode(),
                      headers={"Title": title, "Priority": priority, "Tags": "chart_with_upwards_trend"}, timeout=5)
    except requests.RequestException as e:
        log.warning("ntfy failed: %s", e)
