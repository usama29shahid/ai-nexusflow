"""HTTP checks for Caddy docs/elementary/cube popup + Cube docs_gate cookie.

Requires profiles ``proxy`` + ``cube``, Vault-rendered ``.nexusflow/secrets.env``,
and ``./scripts/proxy-hosts.sh install`` (or curl ``Host:`` headers as used here).

    set -a && source .env && source scripts/load-secrets.sh && set +a
    uv run python tests/integration/caddy_docs_auth_smoke.py
"""

from __future__ import annotations

import base64
import hashlib
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SECRETS = REPO_ROOT / ".nexusflow" / "secrets.env"
TTL = 86400


def _load_secrets() -> dict[str, str]:
    if not SECRETS.is_file():
        raise SystemExit(f"missing {SECRETS}; run ./scripts/start.sh vault")
    out: dict[str, str] = {}
    for line in SECRETS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key] = value
    return out


def _gate(password: str) -> str:
    window = int(time.time()) // TTL
    return hashlib.sha256(f"cube-docs-gate-v2:{password}:{window}".encode()).hexdigest()


def _request(
    host: str,
    path: str = "/",
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, list[str]]:
    req = urllib.request.Request(
        f"http://127.0.0.1{path}",
        headers={"Host": host, **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.headers.get_all("Set-Cookie") or []
    except urllib.error.HTTPError as err:
        return err.code, err.headers.get_all("Set-Cookie") or []
    except OSError as err:
        raise SystemExit(
            f"cannot reach Caddy on 127.0.0.1:80 ({err}); "
            "start with ./scripts/start.sh proxy (and cube)"
        ) from err


def main() -> int:
    secrets = _load_secrets()
    user = secrets.get("NEXUS_DOCS_BASIC_AUTH_USER", "")
    password = secrets.get("NEXUS_DOCS_BASIC_AUTH_PASSWORD", "")
    if not user or not password:
        print("NEXUS_DOCS_BASIC_AUTH_* missing from secrets.env", file=sys.stderr)
        return 1

    host_public = os.environ.get("NEXUS_PUBLIC_HOST", "localhost.com")
    cube = f"cube.{host_public}"
    docs = f"docs.{host_public}"
    elementary = f"elementary.{host_public}"
    basic = base64.b64encode(f"{user}:{password}".encode()).decode()
    gate = _gate(password)
    failures: list[str] = []

    for site in (docs, elementary, cube):
        status, cookies = _request(site)
        if status != 401:
            failures.append(f"{site} anon expected 401 got {status}")
        if cookies:
            failures.append(f"{site} 401 must not Set-Cookie: {cookies}")

    status, cookies = _request(
        cube,
        "/cubejs-api/v1/meta",
        headers={"Authorization": f"Basic {basic}"},
    )
    if status != 200:
        failures.append(f"cube basic auth expected 200 got {status}")
    if not any(c.startswith("docs_gate=") for c in cookies):
        failures.append(f"cube basic 2xx must Set-Cookie docs_gate; got {cookies}")

    status, cookies = _request(
        cube,
        "/cubejs-api/v1/meta",
        headers={"Cookie": f"docs_gate={gate}", "Authorization": "Bearer x"},
    )
    if status != 200:
        failures.append(f"exact docs_gate expected 200 got {status}")
    if not any(c.startswith("docs_gate=") for c in cookies):
        failures.append(f"cookie path 2xx must refresh Set-Cookie; got {cookies}")

    # Substring bypasses that the old header Cookie *docs_gate=* matcher allowed.
    for label, cookie in (
        ("prefix_name", f"xdocs_gate={gate}"),
        ("suffix_value", f"docs_gate={gate}extra"),
        ("wrong_gate", f"docs_gate={'0' * 64}"),
    ):
        status, cookies = _request(
            cube,
            "/cubejs-api/v1/meta",
            headers={"Cookie": cookie, "Authorization": "Bearer x"},
        )
        if status != 401:
            failures.append(f"{label} expected 401 got {status}")
        if cookies:
            failures.append(f"{label} 401 must not Set-Cookie: {cookies}")

    if failures:
        print("FAIL")
        for item in failures:
            print(f"- {item}")
        return 1
    print("PASS caddy docs auth smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
