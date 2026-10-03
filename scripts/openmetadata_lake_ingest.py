#!/usr/bin/env python3
"""Project ClickHouse warehouse + lake dbt/dlt/Elementary signals into OpenMetadata.

Runs ``metadata ingest`` and ``metadata profile`` in the official OpenMetadata
ingestion image (Python 3.10) on the Compose network — host Python is 3.12 and
outside the connector support range.

Projects (reader-side, lake/warehouse → OM):
  - ClickHouse bronze/silver/gold/elementary catalog + profiler
  - dbt artifacts (lineage, descriptions, tags, TestCaseResults)
  - Airflow DAGs (dlt/dbt orchestration as pipeline entities)
  - Links to Elementary HTML / docs for deep-dive UIs

Invoked by ``./scripts/observability-ingest.sh openmetadata``.
Pipeline code must not call OpenMetadata APIs.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from common.observability.config import (  # noqa: E402
    minio_endpoint,
    nexus_env,
    required_env,
    telemetry_bucket,
)

INDEX_PREFIX = "indexes/openmetadata/"
DBT_BRANCH = "dlt_dbt_clickhouse"
SERVICE_NAME = "nexus_clickhouse"
PIPELINE_SERVICE_NAME = "nexus_airflow"
OM_CLICKHOUSE_DATABASE = "default"
REQUIRED_TABLES = (
    "raw_route__products",
    "stg_route__products",
    "dim_product",
)
WORK_DIR = REPO_ROOT / ".nexusflow" / "openmetadata"


def docker_host_path(path: Path | str) -> str:
    """Absolute path the Docker *daemon* can bind-mount (``docker run -v``).

    Inside ``nexus-elt`` the clone is ``/workspace``, but the host daemon only
    sees ``NEXUS_REPO_ROOT``. Pass ``-e NEXUS_REPO_ROOT=…`` into the job container
    so nested ``metadata`` / helper containers mount the real host path.
    """
    p = Path(path).resolve()
    host_root = os.environ.get("NEXUS_REPO_ROOT", "").strip()
    if not host_root:
        return str(p)
    host_root_p = Path(host_root).resolve()
    for root in (REPO_ROOT.resolve(), Path("/workspace").resolve()):
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        return str(host_root_p / rel)
    return str(p)


def docker_volume_bind(
    host_side: Path | str, container_side: str, *, mode: str = "ro"
) -> str:
    """``host:container:mode`` bind with host-path rewrite for nested docker."""
    return f"{docker_host_path(host_side)}:{container_side}:{mode}"


def layer_databases(env: str | None = None) -> list[str]:
    """ClickHouse databases projected into OM as schemas under ``default``."""
    e = env or nexus_env()
    return [
        f"bronze_{e}",
        f"silver_{e}",
        f"gold_{e}",
        f"elementary_{e}",
    ]



def om_base_url() -> str:
    return os.environ.get("OPENMETADATA_URL", "http://127.0.0.1:8585").rstrip("/")


def om_admin_port_url() -> str:
    if os.environ.get("OPENMETADATA_ADMIN_URL"):
        return os.environ["OPENMETADATA_ADMIN_URL"].rstrip("/")
    port = os.environ.get("OPENMETADATA_ADMIN_PORT", "8586")
    return f"http://127.0.0.1:{port}"


def _host_url_ok(url: str, *, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


_COMPOSE_NETWORK_MODE: bool | None = None


def prefer_compose_network() -> bool:
    """True when published host ports are unreachable (e.g. isolated WSL agent).

    When ``OPENMETADATA_URL`` already targets Compose DNS (``openmetadata-server``),
    stay on direct HTTP/boto3 — nested docker helpers break from inside ``nexus-elt``
    (host ``-v`` paths are not the container workspace).
    """
    global _COMPOSE_NETWORK_MODE
    if _COMPOSE_NETWORK_MODE is not None:
        return _COMPOSE_NETWORK_MODE
    url = om_base_url()
    if "openmetadata-server" in url:
        _COMPOSE_NETWORK_MODE = False
        return _COMPOSE_NETWORK_MODE
    forced = os.environ.get("OPENMETADATA_USE_COMPOSE_NETWORK", "").lower()
    if forced in ("1", "true", "yes"):
        _COMPOSE_NETWORK_MODE = True
    elif forced in ("0", "false", "no"):
        _COMPOSE_NETWORK_MODE = False
    else:
        _COMPOSE_NETWORK_MODE = not _host_url_ok(f"{om_admin_port_url()}/healthcheck")
    if _COMPOSE_NETWORK_MODE:
        print(
            "Host OpenMetadata ports unreachable; using Compose network for API/MinIO.",
            file=sys.stderr,
        )
    return _COMPOSE_NETWORK_MODE


def compose_dns_om_url() -> str:
    return "http://openmetadata-server:8585"


def compose_dns_admin_url() -> str:
    return "http://openmetadata-server:8586"


def _http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: int = 60,
) -> Any:
    """HTTP JSON helper with optional Compose-network fallback via docker run."""
    hdrs = dict(headers or {})
    if prefer_compose_network() and (
        "127.0.0.1" in url or "localhost" in url
    ):
        # Rewrite published-host URLs to Compose DNS and fetch from the network.
        rewritten = url.replace("http://127.0.0.1:8585", compose_dns_om_url())
        rewritten = rewritten.replace("http://localhost:8585", compose_dns_om_url())
        rewritten = rewritten.replace(
            f"http://127.0.0.1:{os.environ.get('OPENMETADATA_ADMIN_PORT', '8586')}",
            compose_dns_admin_url(),
        )
        rewritten = rewritten.replace("http://localhost:8586", compose_dns_admin_url())
        return _http_json_via_docker(method, rewritten, headers=hdrs, body=body, timeout=timeout)

    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {exc.code} {url}: {detail}") from exc


def _http_json_via_docker(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    body: bytes | None,
    timeout: int,
) -> Any:
    payload_b64 = base64.b64encode(body or b"").decode()
    headers_json = json.dumps(headers)
    script = f"""
import base64, json, urllib.request, urllib.error, sys
url = {url!r}
method = {method!r}
headers = json.loads({headers_json!r})
body = base64.b64decode({payload_b64!r}) or None
req = urllib.request.Request(url, data=body, headers=headers, method=method)
try:
    with urllib.request.urlopen(req, timeout={timeout}) as resp:
        raw = resp.read().decode()
        sys.stdout.write(raw if raw else "null")
except urllib.error.HTTPError as e:
    sys.stderr.write(e.read().decode(errors="replace"))
    raise SystemExit(e.code if isinstance(e.code, int) else 1)
"""
    # Reuse compose helper runner but without boto3 (stdlib only).
    network = compose_network()
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    script_path = WORK_DIR / "_compose_http_helper.py"
    script_path.write_text(script, encoding="utf-8")
    script_path.chmod(0o600)
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        network,
        "-v",
        docker_volume_bind(script_path, "/helper.py"),
        "python:3.12-alpine",
        "python",
        "/helper.py",
    ]
    try:
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Compose-network HTTP failed for {url}: {exc.stderr}"
        ) from exc
    return json.loads(out) if out.strip() else None


def ingestion_image() -> str:
    ver = os.environ.get("OPENMETADATA_VERSION", "2.0.3")
    return f"docker.getcollate.io/openmetadata/ingestion:{ver}"


def clickhouse_host_port() -> str:
    # Ingestion runs on the Compose network; ClickHouse service DNS is ``clickhouse``.
    return os.environ.get("OPENMETADATA_CLICKHOUSE_HOST_PORT", "clickhouse:8123")


def catalog_user() -> str:
    return os.environ.get("CLICKHOUSE_CATALOG_USER", "nexus_catalog")


def catalog_password() -> str:
    return os.environ.get(
        "CLICKHOUSE_CATALOG_PASSWORD",
        os.environ.get("CLICKHOUSE_PASSWORD", ""),
    )


def build_clickhouse_workflow(
    *,
    jwt_token: str,
    username: str,
    password: str,
    host_port: str,
    databases: list[str],
    om_host_port: str,
    service_name: str = SERVICE_NAME,
) -> dict[str, Any]:
    """Build DatabaseMetadata workflow for ClickHouse (no secrets written to git).

    Filter patterns match **ClickHouse** database names (bronze/silver/gold/elementary).
    The connector then stores them as OM schemas under database ``default``.
    """
    return {
        "source": {
            "type": "clickhouse",
            "serviceName": service_name,
            "serviceConnection": {
                "config": {
                    "type": "Clickhouse",
                    "username": username,
                    "password": password,
                    "hostPort": host_port,
                    "scheme": "clickhouse+http",
                    "https": False,
                }
            },
            "sourceConfig": {
                "config": {
                    "type": "DatabaseMetadata",
                    "markDeletedTables": False,
                    "markDeletedStoredProcedures": False,
                    "markDeletedSchemas": False,
                    "markDeletedDatabases": False,
                    "includeTables": True,
                    "includeViews": True,
                    "databaseFilterPattern": {"includes": list(databases)},
                    "schemaFilterPattern": {"includes": list(databases)},
                }
            },
        },
        "sink": {"type": "metadata-rest", "config": {}},
        "workflowConfig": {
            "loggerLevel": "INFO",
            "openMetadataServerConfig": {
                "hostPort": om_host_port,
                "authProvider": "openmetadata",
                "securityConfig": {"jwtToken": jwt_token},
                "storeServiceConnection": False,
            },
        },
    }


def build_dbt_workflow(
    *,
    jwt_token: str,
    om_host_port: str,
    manifest_path: str,
    catalog_path: str,
    run_results_path: str,
    sources_path: str | None = None,
    service_name: str = SERVICE_NAME,
) -> dict[str, Any]:
    """Attach lake dbt artifacts to an existing database service."""
    dbt_source: dict[str, Any] = {
        "dbtConfigType": "local",
        "dbtManifestFilePath": manifest_path,
        "dbtCatalogFilePath": catalog_path,
        "dbtRunResultsFilePath": run_results_path,
    }
    if sources_path:
        dbt_source["dbtSourcesFilePath"] = sources_path
    return {
        "source": {
            "type": "dbt",
            "serviceName": service_name,
            "sourceConfig": {
                "config": {
                    "type": "DBT",
                    "dbtConfigSource": dbt_source,
                    "dbtUpdateDescriptions": True,
                    "includeTags": True,
                    "searchAcrossDatabases": True,
                    "overrideLineage": True,
                }
            },
        },
        "sink": {"type": "metadata-rest", "config": {}},
        "workflowConfig": {
            "loggerLevel": "INFO",
            "openMetadataServerConfig": {
                "hostPort": om_host_port,
                "authProvider": "openmetadata",
                "securityConfig": {"jwtToken": jwt_token},
                "storeServiceConnection": False,
            },
        },
    }


def build_airflow_workflow(
    *,
    jwt_token: str,
    om_host_port: str,
    service_name: str = PIPELINE_SERVICE_NAME,
) -> dict[str, Any]:
    """Ingest Airflow DAGs (dlt/dbt orchestration) via the Airflow metadata DB."""
    # Compose Airflow 3 uses Postgres; OM reads DAG metadata from the backend.
    pg_user = os.environ.get("AIRFLOW_POSTGRES_USER", "airflow")
    pg_password = os.environ.get("AIRFLOW_POSTGRES_PASSWORD", "airflow")
    pg_host = os.environ.get(
        "OPENMETADATA_AIRFLOW_POSTGRES_HOST_PORT", "airflow-postgres:5432"
    )
    pg_db = os.environ.get("AIRFLOW_POSTGRES_DB", "airflow")
    airflow_ui = os.environ.get(
        "OPENMETADATA_AIRFLOW_HOST_PORT", "http://airflow-api-server:8080"
    )
    return {
        "source": {
            "type": "airflow",
            "serviceName": service_name,
            "serviceConnection": {
                "config": {
                    "type": "Airflow",
                    "hostPort": airflow_ui,
                    "numberOfStatus": 10,
                    "connection": {
                        "type": "Postgres",
                        "username": pg_user,
                        "authType": {"password": pg_password},
                        "hostPort": pg_host,
                        "database": pg_db,
                    },
                }
            },
            "sourceConfig": {
                "config": {
                    "type": "PipelineMetadata",
                    "includeLineage": True,
                    "markDeletedPipelines": False,
                    "pipelineFilterPattern": {
                        "includes": [
                            "route_clickhouse_products",
                            "nexus_airflow_smoke",
                        ]
                    },
                }
            },
        },
        "sink": {"type": "metadata-rest", "config": {}},
        "workflowConfig": {
            "loggerLevel": "INFO",
            "openMetadataServerConfig": {
                "hostPort": om_host_port,
                "authProvider": "openmetadata",
                "securityConfig": {"jwtToken": jwt_token},
                "storeServiceConnection": False,
            },
        },
    }


def rewrite_manifest_sources_for_om(manifest_path: Path) -> int:
    """Set dbt source ``database`` to OM ClickHouse database ``default``.

    ClickHouse OM layout is ``service.default.{bronze,silver,gold}_*``. Historical
    manifests set ``database=bronze_{env}`` which does not exist in OM; clearing it
    to empty can yield ``None`` FQNs. Map layer-valued database → ``default``.
    """
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    changed = 0
    for node in (data.get("sources") or {}).values():
        db = (node.get("database") or "").strip()
        schema = (node.get("schema") or "").strip()
        if db == OM_CLICKHOUSE_DATABASE:
            continue
        if db and schema and db == schema and (
            db.startswith("bronze_")
            or db.startswith("silver_")
            or db.startswith("gold_")
        ):
            node["database"] = OM_CLICKHOUSE_DATABASE
            changed += 1
        elif db.startswith("bronze_") or db.startswith("silver_") or db.startswith(
            "gold_"
        ):
            node["database"] = OM_CLICKHOUSE_DATABASE
            changed += 1
        elif not db and schema.startswith(("bronze_", "silver_", "gold_")):
            node["database"] = OM_CLICKHOUSE_DATABASE
            changed += 1
    if changed:
        manifest_path.write_text(
            json.dumps(data, separators=(",", ":")), encoding="utf-8"
        )
        print(
            f"Rewrote {changed} dbt source(s) in manifest for OM ClickHouse FQNs "
            f"(database → {OM_CLICKHOUSE_DATABASE})."
        )
    return changed


def build_clickhouse_profiler_workflow(
    *,
    jwt_token: str,
    username: str,
    password: str,
    host_port: str,
    databases: list[str],
    om_host_port: str,
    service_name: str = SERVICE_NAME,
    om_database: str = "default",
) -> dict[str, Any]:
    """Build Profiler workflow (row counts, column stats).

    Includes ``serviceConnection`` because metadata ingest uses
    ``storeServiceConnection: false``.

    ClickHouse maps to OM as database ``default`` with layer DBs as schemas
    (``bronze_{env}``, …). Profiler filters the OM catalog, not CH names.
    """
    return {
        "source": {
            "type": "clickhouse",
            "serviceName": service_name,
            "serviceConnection": {
                "config": {
                    "type": "Clickhouse",
                    "username": username,
                    "password": password,
                    "hostPort": host_port,
                    "scheme": "clickhouse+http",
                    "https": False,
                }
            },
            "sourceConfig": {
                "config": {
                    "type": "Profiler",
                    "computeTableMetrics": True,
                    "computeColumnMetrics": True,
                    "databaseFilterPattern": {"includes": [om_database]},
                    "schemaFilterPattern": {"includes": list(databases)},
                }
            },
        },
        "processor": {"type": "orm-profiler", "config": {}},
        "sink": {"type": "metadata-rest", "config": {}},
        "workflowConfig": {
            "loggerLevel": "INFO",
            "openMetadataServerConfig": {
                "hostPort": om_host_port,
                "authProvider": "openmetadata",
                "securityConfig": {"jwtToken": jwt_token},
                "storeServiceConnection": False,
            },
        },
    }


def marker_key(run_id: str) -> str:
    return f"{INDEX_PREFIX}{DBT_BRANCH}__{run_id}.ingested"


def wait_health(*, timeout_s: int = 180) -> None:
    import time

    started = time.time()
    while time.time() - started < timeout_s:
        if prefer_compose_network():
            try:
                subprocess.check_call(
                    [
                        "docker",
                        "exec",
                        "openmetadata-server",
                        "wget",
                        "-q",
                        "-O-",
                        "http://localhost:8586/healthcheck",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except (subprocess.CalledProcessError, FileNotFoundError):
                pass
        elif _host_url_ok(f"{om_admin_port_url()}/healthcheck", timeout=5.0):
            return
        time.sleep(2)
    raise RuntimeError(
        "OpenMetadata healthcheck not ready. "
        "Start with: ./scripts/start.sh openmetadata"
    )


def login_jwt() -> str:
    email = os.environ.get("OPENMETADATA_ADMIN_EMAIL", "admin@open-metadata.org")
    password = os.environ.get("OPENMETADATA_ADMIN_PASSWORD", "admin")
    body = json.dumps(
        {
            "email": email,
            "password": base64.b64encode(password.encode()).decode(),
        }
    ).encode()
    data = _http_json(
        "POST",
        f"{om_base_url()}/api/v1/users/login",
        headers={"Content-Type": "application/json"},
        body=body,
        timeout=30,
    )
    if not isinstance(data, dict):
        raise RuntimeError(f"OpenMetadata login returned unexpected payload: {data!r}")
    token = data.get("accessToken") or data.get("token")
    if not token:
        raise RuntimeError(f"OpenMetadata login response missing token: {data!r}")
    return token


def _s3_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=minio_endpoint(),
        aws_access_key_id=required_env("MINIO_ROOT_USER"),
        aws_secret_access_key=required_env("MINIO_ROOT_PASSWORD"),
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
    )


def _run_python_on_compose_network(script: str, *, extra_binds: list[str] | None = None) -> str:
    """Run a short Python script on the Compose network (boto3 pre-installed)."""
    network = compose_network()
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    script_path = WORK_DIR / "_compose_net_helper.py"
    script_path.write_text(script, encoding="utf-8")
    script_path.chmod(0o600)
    binds: list[str] = [docker_volume_bind(script_path, "/helper.py")]
    for bind in extra_binds or []:
        # Rewrite host side of ``host:container[:mode]`` when nested under /workspace.
        parts = bind.split(":", 2)
        if len(parts) >= 2:
            host, rest = parts[0], ":".join(parts[1:])
            binds.append(f"{docker_host_path(host)}:{rest}")
        else:
            binds.append(bind)
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        network,
        *sum((["-v", b] for b in binds), []),
        "-e",
        f"MINIO_ROOT_USER={required_env('MINIO_ROOT_USER')}",
        "-e",
        f"MINIO_ROOT_PASSWORD={required_env('MINIO_ROOT_PASSWORD')}",
        "-e",
        f"AWS_REGION={os.environ.get('AWS_REGION', 'us-east-1')}",
        "python:3.12-alpine",
        "sh",
        "-c",
        "pip install -q boto3 >/dev/null && python /helper.py",
    ]
    return subprocess.check_output(cmd, text=True)


def _s3_list_keys_via_docker(bucket: str, prefix: str) -> list[str]:
    script = f"""
import boto3, os
c = boto3.client(
    "s3",
    endpoint_url="http://minio:9000",
    aws_access_key_id=os.environ["MINIO_ROOT_USER"],
    aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"],
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)
keys = []
token = None
while True:
    kw = {{"Bucket": {bucket!r}, "Prefix": {prefix!r}}}
    if token:
        kw["ContinuationToken"] = token
    page = c.list_objects_v2(**kw)
    for item in page.get("Contents") or []:
        keys.append(item["Key"])
    if not page.get("IsTruncated"):
        break
    token = page.get("NextContinuationToken")
print("\\n".join(keys))
"""
    out = _run_python_on_compose_network(script)
    return [line for line in out.splitlines() if line.strip()]


def _s3_download_via_docker(bucket: str, key: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    script = f"""
import boto3, os
c = boto3.client(
    "s3",
    endpoint_url="http://minio:9000",
    aws_access_key_id=os.environ["MINIO_ROOT_USER"],
    aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"],
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)
c.download_file({bucket!r}, {key!r}, "/out/{dest.name}")
"""
    _run_python_on_compose_network(
        script, extra_binds=[f"{dest.parent}:/out"]
    )


def latest_dbt_run_id(client, bucket: str) -> str:
    prefix = f"artifacts/dbt/{DBT_BRANCH}/"
    run_ids: set[str] = set()
    if prefer_compose_network():
        keys = _s3_list_keys_via_docker(bucket, prefix)
        for key in keys:
            rest = key[len(prefix) :]
            if "/" not in rest:
                continue
            run_id = rest.split("/", 1)[0]
            if run_id:
                run_ids.add(run_id)
    else:
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for item in page.get("Contents") or []:
                key = item.get("Key") or ""
                rest = key[len(prefix) :]
                if "/" not in rest:
                    continue
                run_id = rest.split("/", 1)[0]
                if run_id:
                    run_ids.add(run_id)
    if not run_ids:
        raise RuntimeError(
            f"No dbt artifacts under s3://{bucket}/{prefix}. "
            "Run the products pipeline so lake artifacts exist."
        )
    return sorted(run_ids)[-1]


def download_dbt_artifacts(client, bucket: str, run_id: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for name in (
        "manifest.json",
        "catalog.json",
        "run_results.json",
        "sources.json",
    ):
        key = f"artifacts/dbt/{DBT_BRANCH}/{run_id}/{name}"
        path = dest / name
        try:
            if prefer_compose_network():
                _s3_download_via_docker(bucket, key, path)
            else:
                client.download_file(bucket, key, str(path))
        except Exception as exc:  # noqa: BLE001 — boto ClientError varies by version
            if name == "manifest.json":
                raise RuntimeError(f"Required lake object missing: {key}") from exc
            print(f"WARN: optional artifact missing ({key}): {exc}", file=sys.stderr)
    rewrite_manifest_sources_for_om(dest / "manifest.json")


def airflow_postgres_reachable() -> bool:
    """True when Airflow metadata Postgres is on the Compose network."""
    try:
        subprocess.check_call(
            [
                "docker",
                "inspect",
                "-f",
                "{{.State.Running}}",
                "airflow-postgres",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        out = subprocess.check_output(
            [
                "docker",
                "inspect",
                "-f",
                "{{.State.Running}}",
                "airflow-postgres",
            ],
            text=True,
        ).strip()
        return out.lower() == "true"
    except subprocess.CalledProcessError:
        return False


def deep_dive_public_base(subdomain: str) -> str:
    """HTTP(S) base for Elementary/dbt docs Caddy sites (backlog 9 auth later).

    OM 2.x CreateDashboard requires ``sourceUrl`` (not ``dashboardUrl``) and accepts
    normal http(s) links. Host/path can change when those sites are fully gated.
    """
    host = os.environ.get("NEXUS_PUBLIC_HOST", "localhost.com").strip() or "localhost.com"
    scheme = os.environ.get("NEXUS_CADDY_SITE_SCHEME", "http://").strip() or "http://"
    if not scheme.endswith("://"):
        scheme = f"{scheme}://"
    return f"{scheme}{subdomain}.{host}/"


def ensure_central_observability_links(jwt_token: str, *, run_id: str | None) -> None:
    """Create/update CustomDashboard entries that point at Elementary / docs deep-dives.

    OM remains the catalog hub; Elementary HTML and dbt docs stay linked readers.
    Uses OM 2.x ``sourceUrl`` field. URLs follow Caddy ``elementary.`` / ``docs.``
    hostnames (content/auth refined in backlog item 9).
    """
    base = om_base_url()
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
    }
    svc_name = "nexus_observability_links"
    # Ensure dashboard service exists (CustomDashboard).
    try:
        _http_json(
            "GET",
            f"{base}/api/v1/services/dashboardServices/name/{svc_name}",
            headers=headers,
        )
    except RuntimeError as exc:
        if "404" not in str(exc):
            raise
        body = json.dumps(
            {
                "name": svc_name,
                "serviceType": "CustomDashboard",
                "description": (
                    "NexusFlow deep-dive UIs linked from OpenMetadata "
                    "(Elementary, dbt docs). Lake remains system of record."
                ),
                "connection": {
                    "config": {
                        "type": "CustomDashboard",
                        "sourcePythonClass": (
                            "metadata.ingestion.source.dashboard."
                            "customdashboard.metadata.CustomDashboardSource"
                        ),
                    }
                },
            }
        ).encode()
        try:
            _http_json(
                "POST",
                f"{base}/api/v1/services/dashboardServices",
                headers=headers,
                body=body,
            )
            print(f"Created dashboard service {svc_name}")
        except RuntimeError as create_exc:
            if "409" not in str(create_exc) and "already exists" not in str(
                create_exc
            ).lower():
                print(
                    f"WARN: could not create dashboard service {svc_name}: {create_exc}",
                    file=sys.stderr,
                )
                return

    env = nexus_env()
    elementary_url = deep_dive_public_base("elementary")
    docs_url = deep_dive_public_base("docs")
    dashboards = [
        {
            "name": "elementary_report",
            "displayName": "Elementary dbt DQ report",
            "description": (
                "Elementary HTML for dbt test history/anomalies. "
                f"Caddy: `{elementary_url}` (basic auth / public gate = backlog item 9). "
                + (
                    f" Lake copy: artifacts/elementary/{DBT_BRANCH}/{run_id}/"
                    "elementary_report.html."
                    if run_id
                    else f" Lake prefix: artifacts/elementary/{DBT_BRANCH}/."
                )
            ),
            "sourceUrl": elementary_url,
        },
        {
            "name": "dbt_docs",
            "displayName": "dbt docs (warehouse)",
            "description": (
                "dbt documentation site for dlt_dbt_clickhouse. "
                f"Caddy: `{docs_url}` (basic auth / public gate = backlog item 9)."
            ),
            "sourceUrl": docs_url,
        },
        {
            "name": "clickhouse_warehouse",
            "displayName": f"ClickHouse warehouse ({env})",
            "description": (
                f"Catalog service {SERVICE_NAME}: bronze/silver/gold/elementary_{env} "
                "as OM schemas under database default. Profiler + dbt tests project DQ here."
            ),
            # Browser-reachable Caddy host — not Compose DNS (openmetadata-server)
            # used for in-cluster API calls during Airflow/nexus-elt ingest.
            "sourceUrl": (
                f"{deep_dive_public_base('openmetadata').rstrip('/')}"
                f"/service/databaseServices/{SERVICE_NAME}"
            ),
        },
    ]
    for dash in dashboards:
        payload = {
            "name": dash["name"],
            "displayName": dash["displayName"],
            "description": dash["description"],
            "sourceUrl": dash["sourceUrl"],
            "service": svc_name,
        }
        try:
            _http_json(
                "POST",
                f"{base}/api/v1/dashboards",
                headers=headers,
                body=json.dumps(payload).encode(),
            )
            print(f"Created dashboard link {dash['name']} → {dash['sourceUrl']}")
        except RuntimeError as exc:
            if "409" in str(exc) or "already exists" in str(exc).lower():
                try:
                    existing = _http_json(
                        "GET",
                        f"{base}/api/v1/dashboards/name/{svc_name}.{dash['name']}",
                        headers=headers,
                    )
                    patch = [
                        {
                            "op": "replace",
                            "path": "/description",
                            "value": dash["description"],
                        },
                        {
                            "op": "replace",
                            "path": "/sourceUrl",
                            "value": dash["sourceUrl"],
                        },
                    ]
                    patch_headers = {
                        **headers,
                        "Content-Type": "application/json-patch+json",
                    }
                    _http_json(
                        "PATCH",
                        f"{base}/api/v1/dashboards/{existing['id']}",
                        headers=patch_headers,
                        body=json.dumps(patch).encode(),
                    )
                    print(
                        f"Updated dashboard link {dash['name']} → {dash['sourceUrl']}"
                    )
                except RuntimeError as patch_exc:
                    print(
                        f"WARN: dashboard {dash['name']} exists but update failed: {patch_exc}",
                        file=sys.stderr,
                    )
            else:
                print(
                    f"WARN: dashboard {dash['name']}: {exc}",
                    file=sys.stderr,
                )


def ensure_bronze_silver_lineage(jwt_token: str, manifest_path: Path) -> int:
    """PUT bronze→silver lineage edges from dbt source→model parent_map.

    OM's SQL lineage parser sees ClickHouse ``bronze_dev.table`` and does not
    always resolve OM ``default.bronze_dev.table``; parent_map projection is reliable.
    """
    if not manifest_path.is_file():
        return 0
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    nodes = data.get("nodes") or {}
    sources = data.get("sources") or {}
    parent_map = data.get("parent_map") or {}
    env = nexus_env()
    base = om_base_url()
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
    }

    def om_fqn_for(unique_id: str) -> str | None:
        if unique_id.startswith("source."):
            node = sources.get(unique_id) or {}
            schema = (node.get("schema") or "").strip()
            ident = (node.get("identifier") or node.get("name") or "").strip()
            if not schema or not ident:
                return None
            return f"{SERVICE_NAME}.{OM_CLICKHOUSE_DATABASE}.{schema}.{ident}"
        if unique_id.startswith("model."):
            node = nodes.get(unique_id) or {}
            schema = (node.get("schema") or "").strip()
            ident = (node.get("alias") or node.get("name") or "").strip()
            if not schema or not ident:
                return None
            # Models often have empty database; OM stores under default.
            return f"{SERVICE_NAME}.{OM_CLICKHOUSE_DATABASE}.{schema}.{ident}"
        return None

    def get_table(fqn: str) -> dict[str, Any] | None:
        try:
            return _http_json(
                "GET",
                f"{base}/api/v1/tables/name/{fqn}",
                headers=headers,
            )
        except RuntimeError:
            return None

    created = 0
    for child_id, parents in parent_map.items():
        if not child_id.startswith("model."):
            continue
        child_node = nodes.get(child_id) or {}
        schema = (child_node.get("schema") or "")
        if not schema.startswith(f"silver_{env}"):
            continue
        child_fqn = om_fqn_for(child_id)
        if not child_fqn:
            continue
        child = get_table(child_fqn)
        if not child:
            continue
        for parent_id in parents or []:
            if not parent_id.startswith("source."):
                continue
            parent_fqn = om_fqn_for(parent_id)
            if not parent_fqn:
                continue
            parent = get_table(parent_fqn)
            if not parent:
                continue
            payload = {
                "edge": {
                    "fromEntity": {"id": parent["id"], "type": "table"},
                    "toEntity": {"id": child["id"], "type": "table"},
                    "lineageDetails": {
                        "source": "Manual",
                        "description": (
                            "dbt source() → silver (Nexus OM projection; "
                            "ClickHouse SQL uses layer DB names that OM stores "
                            f"under {OM_CLICKHOUSE_DATABASE}.)"
                        ),
                    },
                }
            }
            try:
                _http_json(
                    "PUT",
                    f"{base}/api/v1/lineage",
                    headers=headers,
                    body=json.dumps(payload).encode(),
                )
                created += 1
            except RuntimeError as exc:
                print(f"WARN: lineage {parent_fqn} → {child_fqn}: {exc}", file=sys.stderr)
    if created:
        print(f"Projected {created} bronze→silver lineage edge(s) from dbt parent_map.")
    return created


def verify_dbt_projection(jwt_token: str) -> None:
    """Soft-check lineage + test results after dbt ingest."""
    base = om_base_url()
    headers = {"Authorization": f"Bearer {jwt_token}"}
    stg = (
        f"{SERVICE_NAME}.{OM_CLICKHOUSE_DATABASE}."
        f"silver_{nexus_env()}.stg_route__products"
    )
    try:
        lineage = _http_json(
            "GET",
            f"{base}/api/v1/lineage/table/name/{stg}?upstreamDepth=2&downstreamDepth=2",
            headers=headers,
        )
        ups = lineage.get("upstreamEdges") or []
        downs = lineage.get("downstreamEdges") or []
        print(
            f"Lineage check {stg}: upstreamEdges={len(ups)} downstreamEdges={len(downs)}"
        )
        if not ups:
            print(
                "WARN: silver has no upstream lineage yet "
                "(re-run dbt + --force after sources.yml fix if still empty).",
                file=sys.stderr,
            )
    except RuntimeError as exc:
        print(f"WARN: lineage check failed: {exc}", file=sys.stderr)

    try:
        results = _http_json(
            "GET",
            f"{base}/api/v1/dataQuality/testCases/testCaseResults/search/list?limit=1",
            headers=headers,
        )
        total = (results.get("paging") or {}).get("total", 0)
        print(f"TestCaseResults in OM: {total}")
        if not total:
            print(
                "WARN: DQ dashboard will stay empty until TestCaseResults ingest "
                "(dbt run_results must be from `dbt test`, not `dbt docs generate`).",
                file=sys.stderr,
            )
    except RuntimeError as exc:
        print(f"WARN: testCaseResults check failed: {exc}", file=sys.stderr)


def compose_network(container: str = "openmetadata-server") -> str:
    out = subprocess.check_output(
        [
            "docker",
            "inspect",
            "-f",
            "{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}",
            container,
        ],
        text=True,
    ).strip()
    networks = [n for n in out.split() if n]
    if not networks:
        raise RuntimeError(
            f"Container {container} has no networks. Is OpenMetadata running?"
        )
    return networks[0]


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    # Readable inside the ingestion image (runs as non-root airflow user).
    # Files live under gitignored .nexusflow/ only.
    path.chmod(0o644)


def run_om_cli(
    *,
    network: str,
    workflow_host_path: Path,
    extra_binds: list[str],
    subcommand: str,
) -> None:
    """Run ``metadata <subcommand> -c …`` in the official ingestion image."""
    image = ingestion_image()
    # Mount the parent directory so -c /workflows/<name> resolves; override Airflow entrypoint.
    # Host-path rewrite: nested docker from nexus-elt must use NEXUS_REPO_ROOT, not /workspace.
    rewritten_binds: list[str] = []
    for bind in extra_binds:
        parts = bind.split(":", 2)
        if len(parts) >= 2:
            rewritten_binds.append(f"{docker_host_path(parts[0])}:{':'.join(parts[1:])}")
        else:
            rewritten_binds.append(bind)
    cmd = [
        "docker",
        "run",
        "--rm",
        "--network",
        network,
        "--entrypoint",
        "metadata",
        "-v",
        docker_volume_bind(workflow_host_path.parent, "/workflows"),
        *sum((["-v", b] for b in rewritten_binds), []),
        image,
        subcommand,
        "-c",
        f"/workflows/{workflow_host_path.name}",
    ]
    print(
        f"+ docker run … --entrypoint metadata {image} "
        f"{subcommand} -c /workflows/{workflow_host_path.name}"
    )
    subprocess.check_call(cmd)


def run_metadata_ingest(*, network: str, workflow_host_path: Path, extra_binds: list[str]) -> None:
    run_om_cli(
        network=network,
        workflow_host_path=workflow_host_path,
        extra_binds=extra_binds,
        subcommand="ingest",
    )


def run_profiler(*, network: str, workflow_host_path: Path) -> None:
    run_om_cli(
        network=network,
        workflow_host_path=workflow_host_path,
        extra_binds=[],
        subcommand="profile",
    )


def list_cataloged_table_names(jwt_token: str) -> set[str]:
    """Return short table names visible under the nexus_clickhouse service."""
    names: set[str] = set()
    after: str | None = None
    while True:
        q = "limit=100&fields=name"
        if after:
            q += f"&after={after}"
        payload = _http_json(
            "GET",
            f"{om_base_url()}/api/v1/tables?{q}",
            headers={"Authorization": f"Bearer {jwt_token}"},
            timeout=60,
        )
        if not isinstance(payload, dict):
            break
        for entity in payload.get("data") or []:
            name = entity.get("name")
            if name:
                names.add(name)
        paging = payload.get("paging") or {}
        after = paging.get("after")
        if not after:
            break
    return names


def verify_products_tables(jwt_token: str) -> None:
    names = list_cataloged_table_names(jwt_token)
    missing = [t for t in REQUIRED_TABLES if t not in names]
    if missing:
        raise RuntimeError(
            "OpenMetadata catalog missing required products tables: "
            f"{missing}. Found {len(names)} table(s). "
            "Ensure ClickHouse RBAC has nexus_catalog and products data exists."
        )
    print(f"Verified products tables in catalog: {', '.join(REQUIRED_TABLES)}")


def write_marker(client, bucket: str, run_id: str) -> None:
    key = marker_key(run_id)
    body = json.dumps(
        {
            "reader": "openmetadata",
            "branch": DBT_BRANCH,
            "run_id": run_id,
            "service": SERVICE_NAME,
            "tables": list(REQUIRED_TABLES),
        }
    ).encode()
    if prefer_compose_network():
        body_b64 = base64.b64encode(body).decode()
        script = f"""
import base64, boto3, os
c = boto3.client(
    "s3",
    endpoint_url="http://minio:9000",
    aws_access_key_id=os.environ["MINIO_ROOT_USER"],
    aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"],
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)
c.put_object(
    Bucket={bucket!r},
    Key={key!r},
    Body=base64.b64decode({body_b64!r}),
    ContentType="application/json",
)
"""
        _run_python_on_compose_network(script)
    else:
        client.put_object(
            Bucket=bucket, Key=key, Body=body, ContentType="application/json"
        )
    print(f"Wrote marker s3://{bucket}/{key}")


def write_dbt_success_marker_if_ok(
    client, bucket: str, run_id: str, *, dbt_ok: bool
) -> bool:
    """Write the lake success marker only when dbt OM ingest exited 0.

    Soft-fail continues the reader job but must not stamp the marker, so the
    next daily run retries without ``--force``.
    """
    if not dbt_ok:
        return False
    write_marker(client, bucket, run_id)
    return True


def marker_exists(client, bucket: str, run_id: str) -> bool:
    key = marker_key(run_id)
    if prefer_compose_network():
        keys = _s3_list_keys_via_docker(bucket, key)
        return key in keys
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:  # noqa: BLE001
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-ingest even if a lake marker already exists for the latest run",
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="dbt artifact run_id under artifacts/dbt/dlt_dbt_clickhouse/ (default: latest)",
    )
    parser.add_argument(
        "--skip-dbt",
        action="store_true",
        help="Only run ClickHouse metadata ingest (skip lake dbt artifacts)",
    )
    parser.add_argument(
        "--skip-profiler",
        action="store_true",
        help="Skip ClickHouse profiler (row counts / column stats)",
    )
    parser.add_argument(
        "--skip-airflow",
        action="store_true",
        help="Skip Airflow pipeline ingest (dlt/dbt DAG entities)",
    )
    parser.add_argument(
        "--skip-links",
        action="store_true",
        help="Skip creating Elementary/dbt CustomDashboard deep-dive links",
    )
    parser.add_argument(
        "--profiler-only",
        action="store_true",
        help="Only run the ClickHouse profiler (tables must already be cataloged)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build workflows and print paths without calling docker or writing markers",
    )
    args = parser.parse_args(argv)

    wait_health()
    jwt = login_jwt()
    # Ingestion container reaches the OM server on the Compose network.
    om_api = "http://openmetadata-server:8585/api"

    databases = layer_databases()
    pw = catalog_password()
    if not pw:
        raise RuntimeError(
            "CLICKHOUSE_CATALOG_PASSWORD (or CLICKHOUSE_PASSWORD) required. "
            "Run ./scripts/clickhouse-rbac-bootstrap.sh after setting credentials."
        )

    profiler_wf = build_clickhouse_profiler_workflow(
        jwt_token=jwt,
        username=catalog_user(),
        password=pw,
        host_port=clickhouse_host_port(),
        databases=databases,
        om_host_port=om_api,
    )
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    profiler_path = WORK_DIR / "clickhouse_profiler.yaml"
    write_yaml(profiler_path, profiler_wf)

    if args.profiler_only:
        if args.dry_run:
            print(f"dry-run: wrote {profiler_path}")
            return 0
        run_profiler(network=compose_network(), workflow_host_path=profiler_path)
        verify_products_tables(jwt)
        print("OpenMetadata profiler OK.")
        return 0

    ch_wf = build_clickhouse_workflow(
        jwt_token=jwt,
        username=catalog_user(),
        password=pw,
        host_port=clickhouse_host_port(),
        databases=databases,
        om_host_port=om_api,
    )

    ch_path = WORK_DIR / "clickhouse_metadata.yaml"
    write_yaml(ch_path, ch_wf)

    airflow_path = WORK_DIR / "airflow_pipelines.yaml"
    run_airflow = not args.skip_airflow and airflow_postgres_reachable()
    if not args.skip_airflow and not run_airflow:
        print(
            "Airflow Postgres not running; skipping pipeline ingest "
            "(./scripts/start.sh airflow).",
            file=sys.stderr,
        )
    if run_airflow:
        write_yaml(
            airflow_path,
            build_airflow_workflow(jwt_token=jwt, om_host_port=om_api),
        )

    client = None
    bucket = telemetry_bucket()
    run_id = args.run_id
    dbt_dir = WORK_DIR / "dbt"
    skip_catalog = False
    sources_file: str | None = None
    if not args.skip_dbt:
        client = _s3_client()
        if not run_id:
            run_id = latest_dbt_run_id(client, bucket)
        print(f"Using dbt lake run_id={run_id}")
        if not args.force and marker_exists(client, bucket, run_id):
            print(f"Marker exists for {run_id}; use --force to re-ingest catalog/dbt.")
            skip_catalog = True
        else:
            if dbt_dir.exists():
                shutil.rmtree(dbt_dir)
            download_dbt_artifacts(client, bucket, run_id, dbt_dir)
            if (dbt_dir / "sources.json").is_file():
                sources_file = "/dbt/sources.json"
            dbt_wf = build_dbt_workflow(
                jwt_token=jwt,
                om_host_port=om_api,
                manifest_path="/dbt/manifest.json",
                catalog_path="/dbt/catalog.json",
                run_results_path="/dbt/run_results.json",
                sources_path=sources_file,
            )
            dbt_path = WORK_DIR / "dbt_metadata.yaml"
            write_yaml(dbt_path, dbt_wf)

    if args.dry_run:
        print(f"dry-run: wrote {ch_path}")
        if not args.skip_dbt and not skip_catalog:
            print(f"dry-run: dbt artifacts in {dbt_dir}")
        if run_airflow:
            print(f"dry-run: wrote {airflow_path}")
        if not args.skip_profiler:
            print(f"dry-run: wrote {profiler_path}")
        return 0

    network = compose_network()
    if not skip_catalog:
        run_metadata_ingest(network=network, workflow_host_path=ch_path, extra_binds=[])

        if not args.skip_dbt:
            assert run_id
            dbt_path = WORK_DIR / "dbt_metadata.yaml"
            dbt_ok = False
            try:
                run_metadata_ingest(
                    network=network,
                    workflow_host_path=dbt_path,
                    extra_binds=[f"{dbt_dir}:/dbt:ro"],
                )
                dbt_ok = True
            except subprocess.CalledProcessError as exc:
                # OM dbt connector often soft-fails on smoke/elementary nodes and
                # query parse; lineage/tests may still partially land — continue,
                # but do not write the success marker so the next daily run retries
                # without requiring --force.
                print(
                    f"WARN: dbt ingest finished with errors (continuing; "
                    f"no lake marker for {run_id}): {exc}",
                    file=sys.stderr,
                )
            if dbt_ok and client is None:
                client = _s3_client()
            write_dbt_success_marker_if_ok(
                client, bucket, run_id, dbt_ok=dbt_ok
            )

    if run_airflow:
        jwt = login_jwt()
        write_yaml(
            airflow_path,
            build_airflow_workflow(jwt_token=jwt, om_host_port=om_api),
        )
        try:
            run_metadata_ingest(
                network=network, workflow_host_path=airflow_path, extra_binds=[]
            )
        except subprocess.CalledProcessError as exc:
            print(
                f"WARN: Airflow pipeline ingest failed (non-fatal): {exc}",
                file=sys.stderr,
            )

    if not args.skip_profiler:
        # Re-mint JWT; catalog/dbt can take several minutes.
        jwt = login_jwt()
        profiler_wf = build_clickhouse_profiler_workflow(
            jwt_token=jwt,
            username=catalog_user(),
            password=pw,
            host_port=clickhouse_host_port(),
            databases=databases,
            om_host_port=om_api,
        )
        write_yaml(profiler_path, profiler_wf)
        run_profiler(network=network, workflow_host_path=profiler_path)

    jwt = login_jwt()
    if not args.skip_links:
        ensure_central_observability_links(jwt, run_id=run_id or None)
    if not args.skip_dbt and (WORK_DIR / "dbt" / "manifest.json").is_file():
        ensure_bronze_silver_lineage(jwt, WORK_DIR / "dbt" / "manifest.json")
    verify_products_tables(jwt)
    if not args.skip_dbt:
        verify_dbt_projection(jwt)
    print("OpenMetadata catalog ingest OK.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
