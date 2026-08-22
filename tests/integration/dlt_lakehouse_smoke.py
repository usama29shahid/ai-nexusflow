"""Host-side dlt smoke for dlt_dbt_spark_iceberg. No REST API.

Writes a few in-memory rows to:
  - MinIO JSONL archive (nexus-dlt-dbt-spark-iceberg-archive-{env})
  - Iceberg Bronze via Apache Polaris (nexus_{env}.raw_dlt_smoke.smoke)

Run from repo root (Compose profile lakehouse: Polaris, Spark Thrift, Trino, MinIO):

    set -a && source .env && set +a
    export NEXUS_ENV="${NEXUS_ENV:-dev}"
    export NEXUS_RUN_ID="${NEXUS_RUN_ID:-local-$(date -u +%Y%m%dT%H%M%SZ)}"
    uv run python tests/integration/dlt_lakehouse_smoke.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import dlt
from dlt.destinations import filesystem

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
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


def _minio_fs(bucket_url: str, destination_name: str, endpoint: str):
    return filesystem(
        bucket_url=bucket_url,
        destination_name=destination_name,
        credentials={
            "aws_access_key_id": _required("MINIO_ROOT_USER"),
            "aws_secret_access_key": _required("MINIO_ROOT_PASSWORD"),
            "endpoint_url": endpoint,
            "region_name": os.environ.get("AWS_REGION", "us-east-1"),
        },
    )


def _configure_polaris_catalog(env: str, endpoint: str) -> str:
    """Point dlt/pyiceberg at the Polaris REST catalog (host ports)."""
    catalog = f"nexus_{env}"
    polaris_uri = os.environ.get("POLARIS_CATALOG_URI", "http://localhost:8181/api/catalog")
    client_id = os.environ.get("POLARIS_CLIENT_ID", "root")
    client_secret = os.environ.get("POLARIS_CLIENT_SECRET", "s3cr3t")
    os.environ["ICEBERG_CATALOG__ICEBERG_CATALOG_NAME"] = catalog
    os.environ["ICEBERG_CATALOG__ICEBERG_CATALOG_TYPE"] = "rest"
    os.environ["ICEBERG_CATALOG__ICEBERG_CATALOG_CONFIG"] = json.dumps(
        {
            "type": "rest",
            "uri": polaris_uri,
            "warehouse": catalog,
            "credential": f"{client_id}:{client_secret}",
            "scope": "PRINCIPAL_ROLE:ALL",
            "header.Polaris-Realm": "POLARIS",
            "py-io-impl": "pyiceberg.io.fsspec.FsspecFileIO",
            "s3.endpoint": endpoint,
            "s3.path-style-access": "true",
            "s3.region": os.environ.get("AWS_REGION", "us-east-1"),
            "s3.access-key-id": _required("MINIO_ROOT_USER"),
            "s3.secret-access-key": _required("MINIO_ROOT_PASSWORD"),
        }
    )
    return catalog


def main() -> None:
    _load_dotenv(REPO_ROOT / ".env")
    env = os.environ.get("NEXUS_ENV", "dev")
    run_id = os.environ.get(
        "NEXUS_RUN_ID",
        f"local-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
    )
    dataset = "raw_dlt_smoke"
    minio_port = os.environ.get("MINIO_API_PORT", "9002")
    minio_endpoint = f"http://localhost:{minio_port}"
    archive_bucket = f"s3://nexus-dlt-dbt-spark-iceberg-archive-{env}"
    warehouse_bucket = f"s3://nexus-dlt-dbt-spark-iceberg-{env}/warehouse"

    rows = _rows(run_id)
    catalog = _configure_polaris_catalog(env, minio_endpoint)

    archive_pipeline = dlt.pipeline(
        pipeline_name="dlt_lakehouse_smoke_archive",
        destination=_minio_fs(archive_bucket, "lakehouse_archive", minio_endpoint),
        dataset_name=dataset,
    )
    archive_info = archive_pipeline.run(rows, table_name="smoke")
    print("MinIO archive load:", archive_info)
    print(f"  bucket={archive_bucket} endpoint={minio_endpoint}")

    iceberg_resource = dlt.resource(rows, name="smoke", table_format="iceberg")
    iceberg_pipeline = dlt.pipeline(
        pipeline_name="dlt_lakehouse_smoke_iceberg",
        destination=_minio_fs(warehouse_bucket, "polaris_iceberg", minio_endpoint),
        dataset_name=dataset,
    )
    iceberg_info = iceberg_pipeline.run(iceberg_resource)
    print("Iceberg Bronze load:", iceberg_info)
    print(f"  catalog.schema.table={catalog}.{dataset}.smoke")
    print(f"  warehouse={warehouse_bucket}")
    print(f"  run_id={run_id}")

    from pyiceberg.catalog import load_catalog

    ice = load_catalog(catalog, **json.loads(os.environ["ICEBERG_CATALOG__ICEBERG_CATALOG_CONFIG"]))
    table = ice.load_table(f"{dataset}.smoke")
    n = table.scan().to_arrow().num_rows
    print(f"  pyiceberg scan rows={n} location={table.location()}")
    print("OK")


if __name__ == "__main__":
    main()
