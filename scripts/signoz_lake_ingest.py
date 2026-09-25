#!/usr/bin/env python3
"""Replay MinIO lake OTLP JSON batches into SigNoz (reader-side only).

Lake keys (awss3 exporter with s3_prefix=otel, partition %Y/%m/%d/%H/%M):

  otel/2026/09/24/19/46/traces_<id>.json
  otel/2026/09/24/19/46/metrics_<id>.json
  otel/2026/09/24/19/46/logs_<id>.json

Does not import from pipeline packages that call SigNoz. Invoked by
``./scripts/observability-ingest.sh signoz``.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from common.observability.config import (  # noqa: E402
    minio_endpoint,
    nexus_env,
    required_env,
    telemetry_bucket,
)

OTLP_PATHS = {
    "traces": "/v1/traces",
    "metrics": "/v1/metrics",
    "logs": "/v1/logs",
}
INDEX_PREFIX = "indexes/signoz/"
DEFAULT_WINDOW_HOURS = 24
SIGNOZ_OTLP_BASE = "http://127.0.0.1:4318"


@dataclass(frozen=True)
class LakeObject:
    key: str
    signal: str
    partition_time: datetime


def parse_lake_key(key: str) -> LakeObject | None:
    """Parse an awss3 lake key into signal + partition time, or None if not OTLP."""
    parts = key.strip("/").split("/")
    if len(parts) < 6 or parts[0] != "otel":
        return None
    try:
        year, month, day, hour, minute = (int(parts[i]) for i in range(1, 6))
        partition_time = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    filename = parts[-1]
    for signal in ("traces", "metrics", "logs"):
        if filename.startswith(f"{signal}_") and filename.endswith(".json"):
            return LakeObject(key=key, signal=signal, partition_time=partition_time)
    return None


def in_window(
    obj: LakeObject,
    *,
    since: datetime,
    until: datetime,
) -> bool:
    return since <= obj.partition_time < until


def marker_key(object_key: str) -> str:
    return f"{INDEX_PREFIX}{object_key.replace('/', '__')}.ingested"


def parse_iso_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _s3_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=minio_endpoint(),
        aws_access_key_id=required_env("MINIO_ROOT_USER"),
        aws_secret_access_key=required_env("MINIO_ROOT_PASSWORD"),
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )


def list_otel_objects(client, bucket: str) -> Iterable[str]:
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix="otel/"):
        for item in page.get("Contents") or []:
            key = item.get("Key")
            if key:
                yield key


def marker_exists(client, bucket: str, object_key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=marker_key(object_key))
        return True
    except client.exceptions.ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"404", "NoSuchKey", "NotFound", "404 Not Found"}:
            return False
        # botocore often uses HTTPStatusCode
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status == 404:
            return False
        raise


def write_marker(client, bucket: str, object_key: str) -> None:
    import json

    body = json.dumps(
        {
            "schema": "nexus.telemetry/v1",
            "lake_key": object_key,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
        },
        sort_keys=True,
    ).encode("utf-8")
    client.put_object(
        Bucket=bucket,
        Key=marker_key(object_key),
        Body=body,
        ContentType="application/json",
    )


def signoz_container_running() -> bool:
    result = subprocess.run(
        ["docker", "compose", "--profile", "signoz", "ps", "signoz", "--status", "running", "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return bool(result.stdout.strip())


def post_otlp_inside_signoz(*, signal: str, body: bytes) -> None:
    path = OTLP_PATHS[signal]
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--profile",
            "signoz",
            "exec",
            "-T",
            "signoz",
            "curl",
            "--fail",
            "--silent",
            "--show-error",
            "-X",
            "POST",
            f"{SIGNOZ_OTLP_BASE}{path}",
            "-H",
            "Content-Type: application/json",
            "--data-binary",
            "@-",
        ],
        cwd=REPO_ROOT,
        input=body,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or b"").decode("utf-8", errors="replace")
        raise RuntimeError(f"SigNoz OTLP POST {path} failed (rc={result.returncode}): {err}")


def select_objects(
    keys: Iterable[str],
    *,
    since: datetime,
    until: datetime,
) -> list[LakeObject]:
    selected: list[LakeObject] = []
    for key in keys:
        parsed = parse_lake_key(key)
        if parsed is None:
            continue
        if in_window(parsed, since=since, until=until):
            selected.append(parsed)
    selected.sort(key=lambda o: (o.partition_time, o.key))
    return selected


def run_ingest(
    *,
    since: datetime,
    until: datetime,
    force: bool,
    dry_run: bool,
) -> int:
    if not signoz_container_running():
        print(
            "ERROR: SigNoz container is not running. Start with: ./scripts/start.sh signoz",
            file=sys.stderr,
        )
        return 2

    bucket = telemetry_bucket()
    client = _s3_client()
    objects = select_objects(list_otel_objects(client, bucket), since=since, until=until)
    if not objects:
        print(
            f"No lake OTLP objects in {bucket}/otel/ for window "
            f"{since.isoformat()} .. {until.isoformat()}"
        )
        return 0

    posted = 0
    skipped = 0
    for obj in objects:
        if not force and marker_exists(client, bucket, obj.key):
            skipped += 1
            continue
        if dry_run:
            print(f"DRY-RUN would post {obj.signal}: {obj.key}")
            posted += 1
            continue
        body = client.get_object(Bucket=bucket, Key=obj.key)["Body"].read()
        post_otlp_inside_signoz(signal=obj.signal, body=body)
        write_marker(client, bucket, obj.key)
        posted += 1
        print(f"Posted {obj.signal}: {obj.key}")

    print(
        f"Done: posted={posted} skipped={skipped} "
        f"window={since.isoformat()}..{until.isoformat()} force={force}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since",
        help="UTC start (ISO-8601). Default: now-24h.",
    )
    parser.add_argument(
        "--until",
        help="UTC end (ISO-8601). Default: now.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-post even when an indexes/signoz/*.ingested marker exists "
        "(may duplicate spans after a SigNoz wipe).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List matching objects without POSTing.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    until = parse_iso_utc(args.until) if args.until else datetime.now(timezone.utc)
    since = (
        parse_iso_utc(args.since)
        if args.since
        else until - timedelta(hours=DEFAULT_WINDOW_HOURS)
    )
    if since >= until:
        print("ERROR: --since must be before --until", file=sys.stderr)
        return 2
    print(f"NEXUS_ENV={nexus_env()} bucket={telemetry_bucket()}")
    return run_ingest(since=since, until=until, force=args.force, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
