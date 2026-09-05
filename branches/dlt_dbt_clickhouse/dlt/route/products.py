"""Route products — full-refresh dlt load → MinIO archive + ClickHouse Bronze.

Extract once from GET /api/v1/products (paginated), stamp audit/lineage, dual-write,
then publish observability lake events. No dbt, no incremental.

Run from repo root:

    set -a && source .env && set +a
    export NEXUS_ENV="${NEXUS_ENV:-dev}"
    unset NEXUS_RUN_ID   # leftover export overrides minting
    uv run python branches/dlt_dbt_clickhouse/dlt/route/products.py
    # Optional override (Airflow / replay / intentional dlt→dbt chain):
    uv run python branches/dlt_dbt_clickhouse/dlt/route/products.py --run-id local-20260905T120000Z
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import dlt
from dlt.destinations import clickhouse, filesystem
from dlt.sources.helpers.rest_client import RESTClient
from dlt.sources.helpers.rest_client.paginators import PageNumberPaginator

REPO_ROOT = Path(__file__).resolve().parents[4]
ROUTE_BASE_URL = "https://ecommerce.routemisr.com/api/v1"
SOURCE_ID = "route"
ENDPOINT = "products"
PIPELINE_NAME = "route_products"
# Safe for MinIO key segments and Airflow-style run_ids (no / or ..).
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+-]*$")
_RUN_ID_MAX_LEN = 128


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
        # Raise (not sys.exit) so main()'s except path can publish status=failed.
        raise RuntimeError(f"Missing {name}. Source .env from the repo root first.")
    return value


def _route_rest_session():
    """Explicit connect/read timeouts + dlt retries on 429/5xx (honors Retry-After)."""
    from dlt.sources.helpers.requests.retry import Client

    return Client(
        raise_for_status=False,
        request_timeout=(10, 60),
        request_max_attempts=5,
        respect_retry_after_header=True,
    ).session


def _extract_products(
    *,
    run_id: str,
    env: str,
    extracted_at: str,
) -> list[dict[str, Any]]:
    """Full-refresh: paginate all products once; stamp audit/lineage; no business casts."""
    client = RESTClient(
        base_url=ROUTE_BASE_URL,
        session=_route_rest_session(),
        paginator=PageNumberPaginator(
            base_page=1,
            page=1,
            page_param="page",
            total_path="metadata.numberOfPages",
            stop_after_empty_page=True,
        ),
    )

    rows: list[dict[str, Any]] = []
    for page in client.paginate(
        f"/{ENDPOINT}",
        params={"limit": 40},
        data_selector="data",
    ):
        for item in page:
            row = dict(item)
            row["run_id"] = run_id
            row["_extracted_at"] = extracted_at
            row["_source"] = SOURCE_ID
            row["_endpoint"] = ENDPOINT
            row["_nexus_env"] = env
            rows.append(row)
    return rows


def _clickhouse_destination():
    return clickhouse(
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


def _filesystem_destination(*, env: str, run_id: str, dt: str):
    minio_port = os.environ.get("MINIO_API_PORT", "9002")
    minio_endpoint = f"http://localhost:{minio_port}"
    bucket = f"s3://nexus-dlt-dbt-clickhouse-{env}"
    return filesystem(
        bucket_url=bucket,
        destination_name="minio_archive",
        layout="{table_name}/dt={dt}/run_id={run_id}/part-{file_id}.{ext}",
        extra_placeholders={"dt": dt, "run_id": run_id},
        credentials={
            "aws_access_key_id": _required("MINIO_ROOT_USER"),
            "aws_secret_access_key": _required("MINIO_ROOT_PASSWORD"),
            "endpoint_url": minio_endpoint,
            "region_name": os.environ.get("AWS_REGION", "us-east-1"),
        },
    ), bucket, minio_endpoint


def _products_resource(rows: list[dict[str, Any]]):
    @dlt.resource(name=ENDPOINT, write_disposition="append")
    def products():
        yield from rows

    return products()


def _assert_load_ok(load_info: Any) -> None:
    """dlt does not raise on terminal job failure — LoadInfo must be checked."""
    if load_info.has_failed_jobs:
        load_info.raise_on_failed_jobs()


def _products_load_span_cm(*, run_id: str, env: str):
    """Best-effort parent span for the load; never blocks ingest if OTel is down."""
    from contextlib import nullcontext

    try:
        from common.observability.otel import get_tracer

        tracer = get_tracer("nexusflow.dlt", **{"nexus.branch": "dlt_dbt_clickhouse"})
        return tracer.start_as_current_span(
            "route.products.load",
            attributes={
                "nexus.run_id": run_id,
                "nexus.env": env,
                "nexus.branch": "dlt_dbt_clickhouse",
                "nexus.source": SOURCE_ID,
                "nexus.endpoint": ENDPOINT,
                "pipeline_name": PIPELINE_NAME,
            },
        )
    except Exception as otel_exc:  # noqa: BLE001 — never block ingest on OTel setup
        print(
            f"WARNING: OTel parent span unavailable (continuing without it): {otel_exc}",
            file=sys.stderr,
        )
        return nullcontext()


def _mint_local_run_id(now: datetime | None = None) -> str:
    ts = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"local-{ts}"


def _validate_run_id(value: str, *, source: str) -> str:
    """Reject empty / path-like ids that break archive prefixes or lake keys."""
    cleaned = value.strip()
    if not cleaned:
        raise RuntimeError(
            f"Invalid run_id from {source}: empty after strip. "
            "Pass --run-id <id>, unset NEXUS_RUN_ID to mint, or set a non-empty id."
        )
    if len(cleaned) > _RUN_ID_MAX_LEN:
        raise RuntimeError(
            f"Invalid run_id from {source}: length {len(cleaned)} > {_RUN_ID_MAX_LEN}."
        )
    if not _RUN_ID_RE.fullmatch(cleaned):
        raise RuntimeError(
            f"Invalid run_id from {source}: {cleaned!r}. "
            "Use letters, digits, and . _ : + - only (no spaces or /)."
        )
    return cleaned


def _resolve_run_id(
    cli_run_id: str | None,
    *,
    env_run_id: str | None = None,
    now: datetime | None = None,
) -> tuple[str, str]:
    """Resolve shared load id: --run-id > NEXUS_RUN_ID env > mint local-{UTC}.

    Returns (run_id, source) where source is "cli", "env", or "generated".
    When --run-id is present (including empty string), it wins and is validated.
    """
    if cli_run_id is not None:
        return _validate_run_id(cli_run_id, source="--run-id"), "cli"
    if env_run_id is not None and env_run_id.strip() != "":
        return _validate_run_id(env_run_id, source="NEXUS_RUN_ID"), "env"
    return _mint_local_run_id(now), "generated"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Route products full-refresh → MinIO archive + ClickHouse Bronze",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help=(
            "Shared NEXUS_RUN_ID for this load (Bronze, archive, lake, later dbt). "
            "If omitted: use NEXUS_RUN_ID when set, else mint local-{UTC}. "
            "A leftover shell NEXUS_RUN_ID overrides minting — unset it for a fresh id."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    _load_dotenv(REPO_ROOT / ".env")
    secrets_file = REPO_ROOT / ".nexusflow" / "secrets.env"
    if os.environ.get("NEXUS_SECRETS_BACKEND", "env") == "vault" and secrets_file.is_file():
        _load_dotenv(secrets_file, overwrite=True)

    env = os.environ.get("NEXUS_ENV", "dev")
    now = datetime.now(timezone.utc)
    try:
        run_id, run_id_source = _resolve_run_id(
            args.run_id,
            env_run_id=os.environ.get("NEXUS_RUN_ID"),
            now=now,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    os.environ["NEXUS_RUN_ID"] = run_id
    extracted_at = now.isoformat()
    dt = now.strftime("%Y-%m-%d")
    bronze_dataset = f"raw_{SOURCE_ID}_{env}"
    archive_dataset = SOURCE_ID  # → s3://…/route/products/dt=…/run_id=…/

    print(f"run_id={run_id} source={run_id_source}")
    if run_id_source == "env":
        print(
            f"WARNING: Reusing NEXUS_RUN_ID={run_id!r} from the environment. "
            "Bronze is append-only (new _extracted_at + another row batch); "
            "lake summaries/runs/{run_id}.json is overwritten for the same id. "
            "For a new load: unset NEXUS_RUN_ID (default mints local-{{UTC}}) "
            "or pass --run-id <new-id>.",
            file=sys.stderr,
        )

    from common.observability.publish import publish_dlt_load

    status = "ok"
    row_count = 0
    lake_uri = ""
    span_cm = _products_load_span_cm(run_id=run_id, env=env)

    with span_cm as load_span:
        try:
            rows = _extract_products(run_id=run_id, env=env, extracted_at=extracted_at)
            row_count = len(rows)
            if load_span is not None:
                load_span.set_attribute("row_count", row_count)
            if row_count == 0:
                raise RuntimeError("Route products extract returned 0 rows")

            # Archive first, then Bronze: fail before Bronze if archive is incomplete.
            # Green run requires both destinations with zero failed jobs (same extract).
            fs_dest, bucket, minio_endpoint = _filesystem_destination(
                env=env, run_id=run_id, dt=dt
            )
            fs_pipeline = dlt.pipeline(
                pipeline_name=f"{PIPELINE_NAME}_archive",
                destination=fs_dest,
                dataset_name=archive_dataset,
            )
            fs_info = fs_pipeline.run(_products_resource(rows))
            _assert_load_ok(fs_info)
            print("MinIO archive load:", fs_info)
            print(f"  bucket={bucket} endpoint={minio_endpoint}")
            print(f"  prefix={SOURCE_ID}/{ENDPOINT}/dt={dt}/run_id={run_id}/")

            ch_pipeline = dlt.pipeline(
                pipeline_name=PIPELINE_NAME,
                destination=_clickhouse_destination(),
                dataset_name=bronze_dataset,
            )
            ch_info = ch_pipeline.run(_products_resource(rows))
            _assert_load_ok(ch_info)
            print("ClickHouse load:", ch_info)
            print(f"  dataset={bronze_dataset} table={ENDPOINT}")
            print(f"  dlt table={bronze_dataset}___{ENDPOINT}")

            # Publish while parent span is current so dlt.load nests under it.
            lake_uri = publish_dlt_load(
                branch="dlt_dbt_clickhouse",
                component="dlt",
                pipeline_name=PIPELINE_NAME,
                status=status,
                run_id=run_id,
                row_count=row_count,
                source=SOURCE_ID,
                endpoint=ENDPOINT,
            )
            if load_span is not None:
                load_span.set_attribute("status", "ok")
        except Exception as exc:
            status = "failed"
            print(f"ERROR: {exc}", file=sys.stderr)
            if load_span is not None:
                load_span.set_attribute("status", "failed")
            publish_dlt_load(
                branch="dlt_dbt_clickhouse",
                component="dlt",
                pipeline_name=PIPELINE_NAME,
                status=status,
                run_id=run_id,
                row_count=row_count,
                source=SOURCE_ID,
                endpoint=ENDPOINT,
            )
            raise SystemExit(1) from exc

    print(f"  observability lake: {lake_uri}")
    print(f"  run_id={run_id} rows={row_count}")
    print("OK")


if __name__ == "__main__":
    main()
