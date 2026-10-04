"""Render MinIO IAM policy JSON for one NEXUS_ENV.

Templates live in docker/minio/iam/*.json.tpl. The environment is substituted
into bucket names only. Usernames stay nexus_loader / nexus_reader /
nexus_platform_reader / nexus_admin.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = REPO_ROOT / "docker" / "minio" / "iam"
POLICIES = (
    "nexus-loader",
    "nexus-reader",
    "nexus-platform-reader",
    "nexus-admin",
)
_ENV_RE = re.compile(r"[a-z0-9_]+")


def render_policy(name: str, nexus_env: str) -> str:
    """Return policy JSON with {{NEXUS_ENV}} replaced."""
    if name not in POLICIES:
        raise ValueError(f"Unknown MinIO policy {name!r}")
    if not _ENV_RE.fullmatch(nexus_env):
        raise ValueError(f"Invalid NEXUS_ENV for bucket names: {nexus_env!r}")
    path = TEMPLATE_DIR / f"{name}.json.tpl"
    text = path.read_text(encoding="utf-8")
    return text.replace("{{NEXUS_ENV}}", nexus_env)


def write_policies(nexus_env: str, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in POLICIES:
        (out_dir / f"{name}.json").write_text(render_policy(name, nexus_env), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render MinIO IAM policy JSON.")
    parser.add_argument("--env", default=None, help="NEXUS_ENV (default: $NEXUS_ENV or dev)")
    parser.add_argument("--out", type=Path, required=True, help="Directory for rendered JSON")
    args = parser.parse_args(argv)
    import os

    nexus_env = args.env or os.environ.get("NEXUS_ENV", "dev")
    try:
        write_policies(nexus_env, args.out)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
