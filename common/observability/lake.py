"""Direct MinIO writes for observability lake blobs and JSONL events."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.client import BaseClient

from common.observability.config import minio_endpoint, nexus_env, required_env, telemetry_bucket

SCHEMA_VERSION = "nexus.telemetry/v1"

_DBT_ARTIFACTS = (
    "manifest.json",
    "run_results.json",
    "catalog.json",
    "sources.json",
)


def _s3_client() -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=minio_endpoint(),
        aws_access_key_id=required_env("MINIO_ROOT_USER"),
        aws_secret_access_key=required_env("MINIO_ROOT_PASSWORD"),
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )


def write_json_object(key: str, payload: dict[str, Any]) -> str:
    """Write a JSON object to the telemetry bucket. Returns s3:// URI."""
    body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    bucket = telemetry_bucket()
    client = _s3_client()
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
    )
    return f"s3://{bucket}/{key}"


def publish_run_summary(
    run_id: str,
    *,
    branch: str,
    component: str,
    status: str,
    extra: dict[str, Any] | None = None,
) -> str:
    """Write summaries/runs/{run_id}.json."""
    payload: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "nexus.run_id": run_id,
        "nexus.env": nexus_env(),
        "nexus.branch": branch,
        "nexus.component": component,
        "status": status,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        payload.update(extra)
    return write_json_object(f"summaries/runs/{run_id}.json", payload)


def publish_pipeline_event(
    run_id: str,
    *,
    branch: str,
    component: str,
    event_type: str,
    attributes: dict[str, Any] | None = None,
) -> str:
    """Append one nexus.telemetry/v1 JSONL record under events/pipeline/."""
    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    record: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "event_type": event_type,
        "nexus.run_id": run_id,
        "nexus.env": nexus_env(),
        "nexus.branch": branch,
        "nexus.component": component,
        "recorded_at": now.isoformat(),
    }
    if attributes:
        record.update(attributes)

    key = (
        f"events/pipeline/dt={day}/branch={branch}/"
        f"run_id={run_id}/{now.strftime('%H%M%S')}-{event_type}.jsonl"
    )
    bucket = telemetry_bucket()
    client = _s3_client()
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=(json.dumps(record, sort_keys=True) + "\n").encode("utf-8"),
        ContentType="application/x-ndjson",
    )
    return f"s3://{bucket}/{key}"


def copy_dbt_artifacts(
    branch: str,
    run_id: str,
    target_dir: Path,
    *,
    artifacts: tuple[str, ...] = _DBT_ARTIFACTS,
) -> list[str]:
    """Copy dbt target/*.json artifacts to artifacts/dbt/{branch}/{run_id}/."""
    uploaded: list[str] = []
    bucket = telemetry_bucket()
    client = _s3_client()

    for name in artifacts:
        path = target_dir / name
        if not path.is_file():
            continue
        key = f"artifacts/dbt/{branch}/{run_id}/{name}"
        client.upload_file(str(path), bucket, key)
        uploaded.append(f"s3://{bucket}/{key}")

    return uploaded
