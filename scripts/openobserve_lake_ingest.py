#!/usr/bin/env python3
"""Replay MinIO lake OTLP JSON batches into OpenObserve (reader-side only).

Lake keys (awss3 exporter with s3_prefix=otel, partition %Y/%m/%d/%H/%M):

  otel/2026/09/24/19/46/traces_<id>.json
  otel/2026/09/24/19/46/metrics_<id>.json
  otel/2026/09/24/19/46/logs_<id>.json

Does not import from pipeline packages that call OpenObserve. Invoked by
``./scripts/observability-ingest.sh openobserve``.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
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
INDEX_PREFIX = "indexes/openobserve/"
DEFAULT_WINDOW_HOURS = 24
DEFAULT_ORG = "default"


@dataclass(frozen=True)
class LakeObject:
    key: str
    signal: str
    partition_time: datetime


def parse_lake_key(key: str) -> LakeObject | None:
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


def in_window(obj: LakeObject, *, since: datetime, until: datetime) -> bool:
    return since <= obj.partition_time < until


def marker_key(object_key: str) -> str:
    return f"{INDEX_PREFIX}{object_key.replace('/', '__')}.ingested"


def reject_marker_key(object_key: str) -> str:
    """Skip permanently bad lake objects without treating them as successful ingest."""
    return f"{INDEX_PREFIX}{object_key.replace('/', '__')}.rejected"


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
        aws_access_key_id=required_env("MINIO_READER_USER"),
        aws_secret_access_key=required_env("MINIO_READER_PASSWORD"),
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
    return _object_exists(client, bucket, marker_key(object_key)) or _object_exists(
        client, bucket, reject_marker_key(object_key)
    )


def _object_exists(client, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except client.exceptions.ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"404", "NoSuchKey", "NotFound", "404 Not Found"}:
            return False
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status == 404:
            return False
        raise


def write_marker(client, bucket: str, object_key: str) -> None:
    body = json.dumps(
        {
            "schema": "nexus.telemetry/v1",
            "lake_key": object_key,
            "ingested_at": datetime.now(timezone.utc).isoformat(),
            "reader": "openobserve",
        },
        sort_keys=True,
    ).encode("utf-8")
    client.put_object(
        Bucket=bucket,
        Key=marker_key(object_key),
        Body=body,
        ContentType="application/json",
    )


def write_reject_marker(client, bucket: str, object_key: str, reason: str) -> None:
    body = json.dumps(
        {
            "schema": "nexus.telemetry/v1",
            "lake_key": object_key,
            "rejected_at": datetime.now(timezone.utc).isoformat(),
            "reader": "openobserve",
            "reason": reason[:2000],
        },
        sort_keys=True,
    ).encode("utf-8")
    client.put_object(
        Bucket=bucket,
        Key=reject_marker_key(object_key),
        Body=body,
        ContentType="application/json",
    )


def clear_reject_marker(client, bucket: str, object_key: str) -> None:
    """Drop ``.rejected`` after a successful (re)ingest so the lake index stays clean."""
    key = reject_marker_key(object_key)
    try:
        client.delete_object(Bucket=bucket, Key=key)
    except client.exceptions.ClientError:
        # Missing key is fine (never rejected, or already cleared).
        return


def is_transient_otlp_failure(exc: BaseException) -> bool:
    """True when a later retry may succeed (config, auth, OO overload, network).

    Permanent schema/payload errors should be marked ``.rejected`` so cron
    ingest does not spam the same bad object forever.
    """
    msg = str(exc).lower()
    tokens = (
        "retention",
        "exceeding the allowed",
        "http 401",
        "http 403",
        "http 429",
        "http 502",
        "http 503",
        "memorytableoverflow",
        "connection refused",
        "timed out",
        "connect timeout",
        "read timed out",
        "name or service not known",
        "nodename nor servname",
    )
    return any(token in msg for token in tokens)


def oo_base_url() -> str:
    explicit = (os.environ.get("OPENOBSERVE_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    port = os.environ.get("OPENOBSERVE_UI_PORT", "5080")
    return f"http://127.0.0.1:{port}"


def openobserve_reachable() -> bool:
    """True only when ``{OPENOBSERVE_URL}/healthz`` succeeds.

    Do not treat ``docker compose ps`` as healthy — on Docker Desktop/WSL the
    container may be running while host ``127.0.0.1:5080`` is unreachable.
    Set ``OPENOBSERVE_URL=http://openobserve:5080`` when calling from the
    Compose network.
    """
    url = f"{oo_base_url()}/healthz"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def oo_auth_header() -> str:
    email = required_env("ZO_ROOT_USER_EMAIL")
    password = required_env("ZO_ROOT_USER_PASSWORD")
    token = base64.b64encode(f"{email}:{password}".encode()).decode()
    return f"Basic {token}"


def sanitize_otlp_json(payload: object) -> object:
    """Fix OTLP JSON quirks that OpenObserve rejects.

    Collector/lake exports sometimes omit ``values`` on empty
    ``arrayValue`` objects (``{"arrayValue":{}}``). OpenObserve requires
    ``{"arrayValue":{"values":[]}}``.
    """
    if isinstance(payload, dict):
        if (
            "arrayValue" in payload
            and isinstance(payload["arrayValue"], dict)
            and "values" not in payload["arrayValue"]
        ):
            payload = {**payload, "arrayValue": {**payload["arrayValue"], "values": []}}
        return {k: sanitize_otlp_json(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [sanitize_otlp_json(item) for item in payload]
    return payload


def prepare_otlp_body(body: bytes) -> bytes:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return body
    return json.dumps(sanitize_otlp_json(payload), separators=(",", ":")).encode("utf-8")


def post_otlp(*, signal: str, body: bytes) -> None:
    org = os.environ.get("OPENOBSERVE_ORG", DEFAULT_ORG)
    path = OTLP_PATHS[signal]
    url = f"{oo_base_url()}/api/{org}{path}"
    req = urllib.request.Request(
        url,
        data=prepare_otlp_body(body),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": oo_auth_header(),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if resp.status >= 400:
                raise RuntimeError(f"OpenObserve OTLP POST {path} HTTP {resp.status}")
            if raw.strip():
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = None
                if isinstance(payload, dict):
                    partial = payload.get("partialSuccess") or {}
                    rejected = (
                        partial.get("rejectedSpans")
                        or partial.get("rejectedLogRecords")
                        or partial.get("rejectedDataPoints")
                        or 0
                    )
                    if rejected:
                        msg = partial.get("errorMessage") or "partial reject"
                        raise RuntimeError(
                            f"OpenObserve OTLP POST {path} rejected {rejected}: {msg}"
                        )
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"OpenObserve OTLP POST {path} failed HTTP {exc.code}: {detail}"
        ) from exc


def _parse_recorded_at_ns(value: object) -> int:
    if not value:
        return int(datetime.now(timezone.utc).timestamp() * 1e9)
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return int(datetime.now(timezone.utc).timestamp() * 1e9)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1e9)


def pipeline_event_to_otlp_logs(record: dict) -> bytes:
    """Convert one nexus.telemetry/v1 lake event into an OTLP/JSON logs body."""
    attrs = []
    for key, value in record.items():
        if value is None:
            continue
        if isinstance(value, bool):
            attrs.append({"key": key, "value": {"boolValue": value}})
        elif isinstance(value, int) and not isinstance(value, bool):
            attrs.append({"key": key, "value": {"intValue": str(value)}})
        elif isinstance(value, float):
            attrs.append({"key": key, "value": {"doubleValue": value}})
        else:
            attrs.append({"key": key, "value": {"stringValue": str(value)}})
    event_type = str(record.get("event_type") or "pipeline.event")
    status = str(record.get("status") or "")
    severity = 17 if status == "failed" or "fail" in event_type else 9
    severity_text = "ERROR" if severity >= 17 else "INFO"
    ts = _parse_recorded_at_ns(record.get("recorded_at"))
    service = f"nexusflow.{record.get('nexus.component') or 'pipeline'}"
    body = {
        "resourceLogs": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": service}},
                        {
                            "key": "nexus.env",
                            "value": {
                                "stringValue": str(record.get("nexus.env") or nexus_env())
                            },
                        },
                    ]
                },
                "scopeLogs": [
                    {
                        "scope": {"name": "nexus.telemetry"},
                        "logRecords": [
                            {
                                "timeUnixNano": str(ts),
                                "observedTimeUnixNano": str(ts),
                                "severityNumber": severity,
                                "severityText": severity_text,
                                "body": {
                                    "stringValue": json.dumps(record, sort_keys=True)
                                },
                                "attributes": attrs,
                            }
                        ],
                    }
                ],
            }
        ]
    }
    return json.dumps(body).encode("utf-8")


def list_pipeline_event_keys(client, bucket: str) -> Iterable[str]:
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix="events/pipeline/"):
        for item in page.get("Contents") or []:
            key = item.get("Key")
            if key and key.endswith(".jsonl"):
                yield key


def event_in_window(key: str, *, since: datetime, until: datetime) -> bool:
    # events/pipeline/dt=YYYY-MM-DD/...
    parts = key.split("/")
    for part in parts:
        if part.startswith("dt="):
            try:
                day = datetime.strptime(part[3:], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                return False
            return since.date() <= day.date() <= until.date()
    return False


def run_event_log_ingest(
    *,
    since: datetime,
    until: datetime,
    force: bool,
    dry_run: bool,
) -> tuple[int, int, int]:
    """Project lake events/pipeline/*.jsonl into OpenObserve logs."""
    bucket = telemetry_bucket()
    client = _s3_client()
    posted = skipped = failed = 0
    for key in list_pipeline_event_keys(client, bucket):
        if not event_in_window(key, since=since, until=until):
            continue
        # Stable keys (include full lake path) — keep format for existing markers.
        ingested_key = f"{INDEX_PREFIX}events__{key.replace('/', '__')}.ingested"
        rejected_key = f"{INDEX_PREFIX}events__{key.replace('/', '__')}.rejected"
        if not force and (
            _object_exists(client, bucket, ingested_key)
            or _object_exists(client, bucket, rejected_key)
        ):
            skipped += 1
            continue
        if dry_run:
            print(f"DRY-RUN would post event log: {key}")
            posted += 1
            continue
        raw = client.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
        line_ok = 0
        line_fail_transient = 0
        line_fail_permanent = 0
        last_perm_reason = ""
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                post_otlp(signal="logs", body=pipeline_event_to_otlp_logs(record))
                line_ok += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"SKIP (event log failed): {key} — {exc}", file=sys.stderr)
                if is_transient_otlp_failure(exc):
                    line_fail_transient += 1
                else:
                    line_fail_permanent += 1
                    last_perm_reason = str(exc)
                continue
        if line_ok:
            posted += line_ok
            print(f"Posted event log: {key} ({line_ok} records)")
        line_fail = line_fail_transient + line_fail_permanent
        if line_ok and line_fail == 0:
            client.put_object(
                Bucket=bucket,
                Key=ingested_key,
                Body=json.dumps(
                    {
                        "schema": "nexus.telemetry/v1",
                        "lake_key": key,
                        "ingested_at": datetime.now(timezone.utc).isoformat(),
                        "reader": "openobserve",
                        "kind": "pipeline_event_log",
                    },
                    sort_keys=True,
                ).encode("utf-8"),
                ContentType="application/json",
            )
            try:
                client.delete_object(Bucket=bucket, Key=rejected_key)
            except client.exceptions.ClientError:
                pass
        elif line_ok == 0 and line_fail_permanent and not line_fail_transient:
            client.put_object(
                Bucket=bucket,
                Key=rejected_key,
                Body=json.dumps(
                    {
                        "schema": "nexus.telemetry/v1",
                        "lake_key": key,
                        "rejected_at": datetime.now(timezone.utc).isoformat(),
                        "reader": "openobserve",
                        "kind": "pipeline_event_log",
                        "reason": (last_perm_reason or "permanent event log reject")[
                            :2000
                        ],
                    },
                    sort_keys=True,
                ).encode("utf-8"),
                ContentType="application/json",
            )
            print(f"Marked rejected (no retry): {key}", file=sys.stderr)
        elif line_fail:
            print(
                f"WARN: not marking {key} "
                f"(ok={line_ok} transient_fail={line_fail_transient} "
                f"permanent_fail={line_fail_permanent}; retry later)",
                file=sys.stderr,
            )
    return posted, skipped, failed


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
    signals: set[str] | None = None,
) -> int:
    if not openobserve_reachable():
        print(
            "ERROR: OpenObserve /healthz failed at "
            f"{oo_base_url()}/healthz. "
            "Start with: ./scripts/start.sh openobserve "
            "(or set OPENOBSERVE_URL=http://openobserve:5080 on the Compose network).",
            file=sys.stderr,
        )
        return 2

    wanted = signals or {"traces", "logs", "events"}
    bucket = telemetry_bucket()
    client = _s3_client()
    objects = select_objects(list_otel_objects(client, bucket), since=since, until=until)
    if not objects and wanted & {"traces", "logs", "metrics"}:
        print(
            f"No lake OTLP objects in {bucket}/otel/ for window "
            f"{since.isoformat()} .. {until.isoformat()}"
        )
    posted = 0
    skipped = 0
    failed = 0
    # Prefer traces first so the Traces UI fills before bulky metrics.
    objects_sorted = sorted(
        objects,
        key=lambda o: (
            0 if o.signal == "traces" else 1 if o.signal == "logs" else 2,
            o.partition_time,
            o.key,
        ),
    )
    for obj in objects_sorted:
        if obj.signal not in wanted:
            continue
        if not force and marker_exists(client, bucket, obj.key):
            skipped += 1
            continue
        if dry_run:
            print(f"DRY-RUN would post {obj.signal}: {obj.key}")
            posted += 1
            continue
        body = client.get_object(Bucket=bucket, Key=obj.key)["Body"].read()
        try:
            post_otlp(signal=obj.signal, body=body)
        except RuntimeError as exc:
            failed += 1
            print(f"SKIP (post failed): {obj.key} — {exc}", file=sys.stderr)
            if is_transient_otlp_failure(exc):
                # Retry later (retention window, OO overload, auth/network).
                continue
            write_reject_marker(client, bucket, obj.key, str(exc))
            print(f"Marked rejected (no retry): {obj.key}", file=sys.stderr)
            continue
        write_marker(client, bucket, obj.key)
        clear_reject_marker(client, bucket, obj.key)
        posted += 1
        print(f"Posted {obj.signal}: {obj.key}")

    if "events" in wanted:
        ev_posted, ev_skipped, ev_failed = run_event_log_ingest(
            since=since, until=until, force=force, dry_run=dry_run
        )
        posted += ev_posted
        skipped += ev_skipped
        failed += ev_failed

    print(
        f"Done: posted={posted} skipped={skipped} failed={failed} "
        f"window={since.isoformat()}..{until.isoformat()} force={force} "
        f"signals={','.join(sorted(wanted))}"
    )
    if failed:
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", help="UTC start (ISO-8601). Default: now-24h.")
    parser.add_argument("--until", help="UTC end (ISO-8601). Default: now.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-post even when indexes/openobserve/*.ingested exists.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List matching objects without POSTing.",
    )
    parser.add_argument(
        "--signals",
        default="traces,logs,events",
        help=(
            "Comma list: traces,logs,metrics,events. "
            "Default omits metrics (bulk scrapes can OOM OO); pass metrics explicitly."
        ),
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
    signals = {s.strip() for s in args.signals.split(",") if s.strip()}
    allowed = {"traces", "logs", "metrics", "events"}
    unknown = signals - allowed
    if unknown:
        print(
            f"ERROR: unknown --signals {sorted(unknown)}; allowed={sorted(allowed)}",
            file=sys.stderr,
        )
        return 2
    print(f"NEXUS_ENV={nexus_env()} bucket={telemetry_bucket()}")
    return run_ingest(
        since=since, until=until, force=args.force, dry_run=args.dry_run, signals=signals
    )


if __name__ == "__main__":
    raise SystemExit(main())
