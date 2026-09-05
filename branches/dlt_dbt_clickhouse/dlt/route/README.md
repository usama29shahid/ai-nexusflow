# Route — dlt endpoint pipelines → raw_route_{env}

Primary REST source: [Route API](https://ecommerce.routemisr.com/) (synthetic ecommerce demo data). Shared source contract: [docs/route-ingestion.md](../../../../docs/route-ingestion.md).

This folder belongs to `dlt_dbt_clickhouse`. Endpoint pipelines write ClickHouse Bronze `raw_route_{env}` and MinIO archive `nexus-dlt-dbt-clickhouse-{env}`.

**Org standard:** [docs/dlt-extraction.md](../../../../docs/dlt-extraction.md) — **Reference pipeline**. [`products.py`](products.py) is the canonical implementation; the next script here must follow it.

## Checklist for the next endpoint script

Copy these from `products.py` / the docs (do not invent a parallel pattern):

1. One file named after the resource (`categories.py`, …).
2. Extract once → stamp `run_id`, `_extracted_at`, `_source`, `_endpoint`, `_nexus_env` → **archive then Bronze**.
3. Assert `LoadInfo.has_failed_jobs` / `raise_on_failed_jobs()` on each destination; treat 0 rows as failure.
4. `--run-id` > `NEXUS_RUN_ID` > mint `local-{UTC}`; validate allowlist; set `NEXUS_RUN_ID` for lake / dbt.
5. Explicit HTTP timeouts + retries + `Retry-After`; `_required` raises `RuntimeError` (not bare `sys.exit`).
6. MinIO via `MINIO_ENDPOINT_URL` (host default `http://localhost:$MINIO_API_PORT`; Compose/Airflow often `http://minio:9000`).
7. `publish_dlt_load` on ok **and** fail; OTel parent span best-effort only if used.
8. Unit guards under `tests/dlt/route/unit/` (not root `tests/`, not dbt `test-paths`).

## Implemented

| Script | Mode | Notes |
|---|---|---|
| [`products.py`](products.py) | Full refresh | Paginated `GET /api/v1/products` → MinIO JSONL + ClickHouse Bronze + telemetry |

```bash
set -a && source .env && set +a
export NEXUS_ENV="${NEXUS_ENV:-dev}"
# Leftover NEXUS_RUN_ID in the shell overrides minting (WARNING + append-only duplicates).
unset NEXUS_RUN_ID
# OTLP → always-on otel-collector → lake otel/ (default endpoint below)
export OTEL_EXPORTER_OTLP_ENDPOINT="${OTEL_EXPORTER_OTLP_ENDPOINT:-http://127.0.0.1:4317}"
uv run python branches/dlt_dbt_clickhouse/dlt/route/products.py

# Explicit shared id (Airflow DAG run_id, replay, or intentional dlt→dbt chain):
uv run python branches/dlt_dbt_clickhouse/dlt/route/products.py --run-id local-20260905T120000Z
```

Resolution: `--run-id` > `NEXUS_RUN_ID` env > mint `local-{UTC}`.  
Ids must match `[A-Za-z0-9][A-Za-z0-9._:+-]*` (no `/` or spaces). Reusing an id appends Bronze and overwrites `summaries/runs/{run_id}.json`.

Unit guards (no Compose):

```bash
uv run python branches/dlt_dbt_clickhouse/tests/dlt/route/unit/test_products_guards.py
```

### dlt schema / dashboard (pipeline metrics only — not Bronze SQL)

Use the Workspace Dashboard for **dlt** loads, inferred schema, and local pipeline state. It is **not** wired for ClickHouse; do not use its SQL / dataset browser for data. Query Bronze with CloudBeaver or `clickhouse-client`.

```bash
# Inferred schema YAML (local pipeline state; no destination reconnect)
uv run dlt pipeline --pipelines-dir ~/.dlt/pipelines route_products schema --format yaml

# Workspace UI — metrics / schema / loads only (no CH credentials)
uv sync --extra dlt-dashboard   # once (pulls dlt[hub] + marimo/…)
./scripts/dlt-dashboard-route-products.sh
# → http://localhost:2718 (script stops prior marimo instances first)
# If the UI shows a skew-protection warning: close old tabs and open the new URL.
```

### ClickHouse Bronze table names (CloudBeaver / clickhouse-client)

ClickHouse has **no schemas**. dlt stores the dataset as a **table name prefix** with `___`, inside `CLICKHOUSE_DB` (usually `warehouse`). Logical resource names (`products`) ≠ physical tables (`NEXUS_ENV=dev` → `raw_route_dev`):

```sql
-- works (physical tables in warehouse)
SELECT * FROM raw_route_dev___products LIMIT 1000;
SELECT * FROM raw_route_dev___products__images LIMIT 100;
SELECT * FROM raw_route_dev___products__subcategory LIMIT 100;
SELECT * FROM raw_route_dev____dlt_loads ORDER BY inserted_at DESC LIMIT 20;

-- fails (no table literally named products)
-- SELECT * FROM products;
```

## Not yet implemented

`categories`, `brands` (catalog follow-ons — **same norms as products**). Authenticated cart / wishlist / orders / addresses come after catalog is solid.

Secondary REST sources (for example DataForSEO) get their own `dlt/{source}/` folders. They must not modify pipelines here. Shared Gold may combine sources; see [docs/enhanced-modeling-strategy.md](../../../../docs/enhanced-modeling-strategy.md).
