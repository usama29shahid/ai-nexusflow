"""Host-side dlt smoke for dlt_dbt_clickhouse. No REST API.

Writes a few in-memory rows to ClickHouse and MinIO. Run from repo root:

    set -a && source .env && set +a
    export NEXUS_ENV="${NEXUS_ENV:-dev}"
    export NEXUS_RUN_ID="${NEXUS_RUN_ID:-local-$(date -u +%Y%m%dT%H%M%SZ)}"
    uv run python tests/integration/dlt_clickhouse_smoke.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import dlt
from dlt.destinations import clickhouse, filesystem

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path, *, overwrite: bool = False) -> None:
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if overwrite:
            os.environ[key] = value
        else:
            os.environ.setdefault(key, value)


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        print(f"Missing {name}. Source .env from the repo root first.", file=sys.stderr)
        sys.exit(1)
    return value


def _rows(run_id: str) -> list[dict[str, object]]:
    now = datetime.now(timezone.utc).isoformat()
    return [
        {"id": 1, "name": "dlt_smoke_a", "run_id": run_id, "_extracted_at": now},
        {"id": 2, "name": "dlt_smoke_b", "run_id": run_id, "_extracted_at": now},
        {"id": 3, "name": "dlt_smoke_c", "run_id": run_id, "_extracted_at": now},
    ]


def main() -> None:
    _load_dotenv(REPO_ROOT / ".env")
    secrets_file = REPO_ROOT / ".nexusflow" / "secrets.env"
    if os.environ.get("NEXUS_SECRETS_BACKEND", "env") == "vault" and secrets_file.is_file():
        _load_dotenv(secrets_file, overwrite=True)
    env = os.environ.get("NEXUS_ENV", "dev")
    run_id = os.environ.get(
        "NEXUS_RUN_ID",
        f"local-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
    )
    dataset = f"raw_dlt_smoke_{env}"
    bucket = f"s3://nexus-dlt-dbt-clickhouse-{env}"
    minio_port = os.environ.get("MINIO_API_PORT", "9002")
    minio_endpoint = f"http://localhost:{minio_port}"

    rows = _rows(run_id)

    ch_dest = clickhouse(
        credentials={
            "host": os.environ.get("CLICKHOUSE_HOST", "localhost"),
            "port": int(os.environ.get("CLICKHOUSE_NATIVE_PORT", "9000")),
            "http_port": int(os.environ.get("CLICKHOUSE_HTTP_PORT", "8123")),
            "username": os.environ.get("CLICKHOUSE_USER", "default"),
            "password": _required("CLICKHOUSE_PASSWORD"),
            "database": os.environ.get("CLICKHOUSE_DB", "default"),
            "secure": 0,
        }
    )
    ch_pipeline = dlt.pipeline(
        pipeline_name="dlt_clickhouse_smoke",
        destination=ch_dest,
        dataset_name=dataset,
    )
    ch_info = ch_pipeline.run(rows, table_name="smoke")
    print("ClickHouse load:", ch_info)
    print(f"  database={os.environ.get('CLICKHOUSE_DB', 'default')}")
    print(f"  dlt table={dataset}___smoke  (dlt ClickHouse uses dataset___table in one DB)")

    fs_dest = filesystem(
        bucket_url=bucket,
        destination_name="minio_archive",
        credentials={
            "aws_access_key_id": _required("MINIO_ROOT_USER"),
            "aws_secret_access_key": _required("MINIO_ROOT_PASSWORD"),
            "endpoint_url": minio_endpoint,
            "region_name": os.environ.get("AWS_REGION", "us-east-1"),
        },
    )
    fs_pipeline = dlt.pipeline(
        pipeline_name="dlt_clickhouse_smoke_archive",
        destination=fs_dest,
        dataset_name=dataset,
    )
    fs_info = fs_pipeline.run(rows, table_name="smoke")
    print("MinIO archive load:", fs_info)
    print(f"  bucket={bucket} endpoint={minio_endpoint}")

    from common.observability.publish import publish_dlt_load

    lake_uri = publish_dlt_load(
        branch="dlt_dbt_clickhouse",
        component="dlt",
        pipeline_name="dlt_clickhouse_smoke",
        status="ok",
        run_id=run_id,
        row_count=len(rows),
    )
    print(f"  observability lake: {lake_uri}")
    print(f"  run_id={run_id}")
    print("OK")


if __name__ == "__main__":
    main()
