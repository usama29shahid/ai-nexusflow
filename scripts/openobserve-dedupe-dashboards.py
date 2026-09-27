#!/usr/bin/env python3
"""Delete duplicate OpenObserve dashboards (keep highest dashboard_id per title)."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from base64 import b64encode
from collections import defaultdict

email = os.environ["ZO_ROOT_USER_EMAIL"]
password = os.environ["ZO_ROOT_USER_PASSWORD"]
base = os.environ.get("OPENOBSERVE_URL", "http://openobserve:5080").rstrip("/")
org = os.environ.get("OPENOBSERVE_ORG", "default")
auth = b64encode(f"{email}:{password}".encode()).decode()
headers = {"Authorization": f"Basic {auth}"}


def req(method: str, path: str) -> tuple[int, object]:
    r = urllib.request.Request(
        f"{base}{path}",
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            body = resp.read()
            data = json.loads(body) if body else None
            return resp.status, data
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


code, data = req("GET", f"/api/{org}/dashboards")
if code >= 400 or not isinstance(data, dict):
    print(f"ERROR list dashboards HTTP {code}: {data}", file=sys.stderr)
    raise SystemExit(1)

items = data.get("dashboards") or []
by: dict[str, list] = defaultdict(list)
for i in items:
    if isinstance(i, dict):
        by[i.get("title") or "?"].append(i)

print(f"before: {len(items)}")
dropped = 0
for title, xs in sorted(by.items()):
    xs = sorted(xs, key=lambda d: int(d.get("dashboard_id") or 0))
    keep = xs[-1]
    print(f"  {title}: keep {keep.get('dashboard_id')} (had {len(xs)})")
    for d in xs[:-1]:
        did = d["dashboard_id"]
        c, _ = req("DELETE", f"/api/{org}/dashboards/{did}")
        print(f"    deleted {did} -> {c}")
        dropped += 1

code, data = req("GET", f"/api/{org}/dashboards")
items = (data or {}).get("dashboards") or [] if isinstance(data, dict) else []
print(f"after: {len(items)} (removed {dropped})")
for i in sorted(items, key=lambda d: d.get("title") or ""):
    print(f"  - {i.get('title')}")
