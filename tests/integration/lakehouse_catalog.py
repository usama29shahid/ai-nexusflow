"""Shared Polaris / MinIO settings for lakehouse integration scripts (host-side)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
METADATA_VERSION_RE = re.compile(r"^(\d+)-")


def load_dotenv(path: Path | None = None) -> None:
    path = path or REPO_ROOT / ".env"
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing {name}. Source .env from the repo root first.")
    return value


def nexus_env() -> str:
    return os.environ.get("NEXUS_ENV", "dev")


def catalog_name(env: str | None = None) -> str:
    return f"nexus_{env or nexus_env()}"


def minio_endpoint() -> str:
    port = os.environ.get("MINIO_API_PORT", "9002")
    return f"http://localhost:{port}"


def warehouse_bucket(env: str | None = None) -> str:
    return f"nexus-dlt-dbt-spark-iceberg-{env or nexus_env()}"


def polaris_catalog_config(env: str | None = None) -> dict[str, str]:
    env = env or nexus_env()
    endpoint = minio_endpoint()
    client_id = os.environ.get("POLARIS_CLIENT_ID", "root")
    client_secret = os.environ.get("POLARIS_CLIENT_SECRET", "s3cr3t")
    polaris_uri = os.environ.get("POLARIS_CATALOG_URI", "http://localhost:8181/api/catalog")
    return {
        "type": "rest",
        "uri": polaris_uri,
        "warehouse": catalog_name(env),
        "credential": f"{client_id}:{client_secret}",
        "scope": "PRINCIPAL_ROLE:ALL",
        "header.Polaris-Realm": "POLARIS",
        "py-io-impl": "pyiceberg.io.fsspec.FsspecFileIO",
        "s3.endpoint": endpoint,
        "s3.path-style-access": "true",
        "s3.region": os.environ.get("AWS_REGION", "us-east-1"),
        "s3.access-key-id": required("MINIO_ROOT_USER"),
        "s3.secret-access-key": required("MINIO_ROOT_PASSWORD"),
    }


def configure_iceberg_catalog_env(env: str | None = None) -> str:
    """Set dlt/pyiceberg env vars; return catalog name."""
    env = env or nexus_env()
    name = catalog_name(env)
    os.environ["ICEBERG_CATALOG__ICEBERG_CATALOG_NAME"] = name
    os.environ["ICEBERG_CATALOG__ICEBERG_CATALOG_TYPE"] = "rest"
    os.environ["ICEBERG_CATALOG__ICEBERG_CATALOG_CONFIG"] = json.dumps(polaris_catalog_config(env))
    return name


def load_polaris_catalog(env: str | None = None):
    from pyiceberg.catalog import load_catalog

    env = env or nexus_env()
    return load_catalog(catalog_name(env), **polaris_catalog_config(env))


def smoke_table_metadata_prefix(env: str | None = None) -> str:
    bucket = warehouse_bucket(env)
    return f"{bucket}/warehouse/raw_dlt_smoke/smoke/metadata"


def find_latest_smoke_metadata_location(env: str | None = None) -> str | None:
    """Return s3:// URI of the newest *.metadata.json for raw_dlt_smoke.smoke, if any."""
    import s3fs

    env = env or nexus_env()
    prefix = smoke_table_metadata_prefix(env)
    fs = s3fs.S3FileSystem(
        key=required("MINIO_ROOT_USER"),
        secret=required("MINIO_ROOT_PASSWORD"),
        client_kwargs={"endpoint_url": minio_endpoint()},
    )
    if not fs.exists(f"{prefix}/"):
        return None

    best_version = -1
    best_path: str | None = None
    for path in fs.ls(prefix, detail=False):
        name = path.rsplit("/", 1)[-1]
        if not name.endswith(".metadata.json"):
            continue
        match = METADATA_VERSION_RE.match(name)
        if not match:
            continue
        version = int(match.group(1))
        if version > best_version:
            best_version = version
            best_path = path

    if best_path is None:
        return None
    if best_path.startswith("s3://"):
        return best_path
    return f"s3://{best_path}"
