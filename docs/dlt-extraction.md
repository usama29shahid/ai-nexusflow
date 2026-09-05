# dlt extraction (dlt_dbt_clickhouse)

dlt is the **REST extraction and load** layer. It is not the dimensional model.

For **dlt_dbt_clickhouse**, runnable pipelines live under `branches/dlt_dbt_clickhouse/dlt/{source}/`. Repo `ingestion/sources/` stays a stub until another backend needs the same REST client. They run on the **host** with `uv run`, not inside Docker.

This document is the org standard for RAG, agents, and every new endpoint script. Primary source (Route API): [route-ingestion.md](route-ingestion.md). Warehouse layout: [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md).

---

## Reference pipeline (mandatory norms)

**Canonical implementation:** [`branches/dlt_dbt_clickhouse/dlt/route/products.py`](../branches/dlt_dbt_clickhouse/dlt/route/products.py).

That script is the first real warehouse dlt pipeline. The next endpoint (`categories`, `brands`, or another source under `dlt/{source}/`) **must** follow the same norms unless this document is updated first. Do not invent a parallel pattern.

| Norm | Rule |
| --- | --- |
| **One script per endpoint** | Name the file after the resource (`categories.py`, not `pipe_two.py`) under `dlt/{source}/`. |
| **Extract once** | Paginate/collect into memory (or one normalize pass), then dual-write the **same** stamped rows. Never scrape the API separately for archive and Bronze. |
| **Dual-write order** | **MinIO archive first**, then ClickHouse Bronze. Fail before Bronze if archive load is incomplete. |
| **Assert load success** | After each `pipeline.run`, check `LoadInfo.has_failed_jobs` and call `raise_on_failed_jobs()`. dlt does not always raise on terminal job failure. |
| **Zero rows** | Empty extract after pagination is a **failure** — do not publish success. |
| **Shared `run_id`** | Resolve `--run-id` > `NEXUS_RUN_ID` env > mint `local-{UTC}`. Set `os.environ["NEXUS_RUN_ID"]` for lake / later dbt. Validate allowlist `[A-Za-z0-9][A-Za-z0-9._:+-]*` (no `/`, spaces, or empty). Warn on env reuse (append-only Bronze + lake summary overwrite). |
| **Audit / lineage columns** | Stamp every row: `run_id`, `_extracted_at`, `_source`, `_endpoint`, `_nexus_env`. No business casts in dlt — typing and flatten belong in `stg_*`. |
| **HTTP client** | Explicit connect/read timeouts, retries on 429/5xx, honor `Retry-After`. |
| **MinIO endpoint** | Use `MINIO_ENDPOINT_URL` (default `http://localhost:{MINIO_API_PORT}`). Inside Compose/Airflow set e.g. `http://minio:9000`. |
| **Missing secrets** | Raise `RuntimeError` (not bare `sys.exit`) so the failure path can still publish lake `status=failed`. |
| **Observability every run** | Call `publish_dlt_load` on success **and** failure (`dlt.load.completed` / `dlt.load.failed`). OTLP via that helper is best-effort. If you wrap a parent span, setup must not abort ingest when OTel is down; nest `publish_dlt_load` under the parent when present; set parent `StatusCode.OK` / `ERROR` explicitly (do not rely on `SystemExit` for ERROR). |
| **Unit tests** | Branch guards under `branches/dlt_dbt_clickhouse/tests/dlt/{source}/unit/` (not root `tests/`, not dbt `test-paths`). Cover run_id, LoadInfo, HTTP session, and OTel fallback as applicable. |

Checklist + runbook for Route: [`branches/dlt_dbt_clickhouse/dlt/route/README.md`](../branches/dlt_dbt_clickhouse/dlt/route/README.md).

---

## What dlt does

1. Call the REST API (auth, pagination, retries, rate limits).
2. Optionally apply **incremental** state (cursor / `updated_at` / since).
3. Stamp rows with a shared **`run_id`** (CLI / env / mint; Airflow DAG `run_id` when orchestrated).
4. Write **once** to two destinations:
   - MinIO: immutable JSONL archive (replay) in `nexus-dlt-dbt-clickhouse-{env}`.
   - ClickHouse `raw_{source}_{env}` (e.g. `raw_route_dev`): append-only Bronze.
5. Publish observability lake events (and best-effort OTLP) via `common/observability`.
6. Keep **pipeline state** (incremental cursors, schema) in dlt — not a custom watermark table.

**dlt stops at archive + Bronze (+ telemetry).** Staging, intermediate, Gold, marts, and tests are dbt-only. dlt may create nested/child tables from JSON; leave them in Bronze and flatten in dbt `stg_*`.

---

## Pipeline grain

| Grain | Rule |
| --- | --- |
| **Source** | `route` (primary), later secondary REST sources — Airflow DAG grain |
| **Endpoint pipeline** | One dlt script (or REST resource) per endpoint; name the script after the resource (`products.py`, not `pipe_one.py`) |
| **Param variant** | Separate pipeline/table only if payload **contract** differs (schema, grain, auth, incremental). Same schema, different URL id → parameters on one pipeline; later Airflow may run multiple jobs with different params |

Code layout:

```text
branches/dlt_dbt_clickhouse/dlt/{source}/   # endpoint pipelines → raw_{source}_{env}
  # e.g. route/products.py, route/categories.py, route/brands.py
branches/dlt_dbt_clickhouse/tests/dlt/{source}/unit/   # Python unit guards
ingestion/sources/                          # stub until a second backend shares REST defs
```

---

## Authentication

Configure per source. Secrets from the environment — injected by [HashiCorp Vault Agent](vault.md) on the VPS (`NEXUS_SECRETS_BACKEND=vault`) or from `.env` for local bootstrap (`NEXUS_SECRETS_BACKEND=env`). Never commit keys.

| Pattern | When |
| --- | --- |
| None / public | e.g. Route catalog (`products`, `categories`, `brands`) |
| API key header or query | Many SaaS REST APIs |
| Bearer token | `Authorization: Bearer …` |
| HTTP Basic | Rare; still supported |
| OAuth2 | Token URL + client credentials or refresh; dlt REST source can hold the token flow |

dlt REST source: declare auth on the client (`api_key`, `bearer`, `http_basic`, `oauth2`). Rotate via Vault KV (see [vault.md](vault.md)) or env vars — not hardcoded config.

---

## Pagination

The API dictates the strategy. Declare it on the resource; do not hand-roll page loops unless the API is nonstandard.

| Strategy | Typical signal |
| --- | --- |
| Page number | `?page=` / `?pageSize=` |
| Offset / limit | `?offset=` / `?limit=` |
| Cursor / next token | `next`, `cursor`, `pageToken` in body |
| Link header | RFC 5988 `Link: rel="next"` |
| JSON next URL | `next` / `links.next` as a full URL |

Stop when the page is empty or `next` is null. Respect `max_table_nesting` / data selector so each resource maps to one Bronze table (plus children).

---

## Retries, timeouts, rate limits

Use dlt HTTP retry behavior (exponential backoff on 429 and 5xx). Set:

- Connect/read **timeouts** per source (reference: connect 10s / read 60s on Route products).
- **Retry** on transient failures; do not retry 401/403/404 as if they were flakes (fix auth or the path).
- **429:** honor `Retry-After` when present.
- Optional **rate limiter** if the API publishes a quota.

Airflow (Phase 1) retries the **task**. dlt retries **HTTP calls inside** the task. Those are different layers; both are valid. Do not build a third retry daemon.

---

## Incremental extraction

When the API supports it:

- dlt `incremental` on a cursor field (`updated_at`, `id`, `since`).
- State stored by dlt pipeline name + dataset.
- Each run still **appends** Bronze with a new `run_id`. Incremental reduces API volume; it does not overwrite history.

When the API is full-refresh only (Route catalog today): extract the snapshot, archive it, append Bronze. dbt dedupes to “current” using `run_id` / business keys.

---

## Dual destination and archive keys

Extract once in memory (or one normalize pass), then:

1. **Filesystem / S3 destination** → MinIO bucket `nexus-dlt-dbt-clickhouse-{env}` from `NEXUS_ENV` (default `dev` → `nexus-dlt-dbt-clickhouse-dev`; see [environments.md](environments.md)). The dlt **job name** is not the bucket. Layout: `{source}/{endpoint}/dt=…/run_id=…/part-*.jsonl.gz`.
2. **ClickHouse destination** → dataset / database `raw_{source}_{env}` (e.g. `raw_route_dev`), MergeTree-style append. Physical table id under `CLICKHOUSE_DB` may appear as `raw_{source}_{env}___{table}` depending on dlt naming — declare the identifier explicitly in dbt `sources.yml`.

Replay mode (later): **do not call the API**. Read JSONL from the prefix, load Bronze with a **new** `run_id`, run dbt.

---

## Metadata on Bronze rows

Every load must carry at least:

| Column | Meaning |
| --- | --- |
| `run_id` | Shared run id (CLI / env / mint; Airflow DAG `run_id` when orchestrated) |
| `_extracted_at` | Extract timestamp (UTC ISO) |
| `_source` | Source id (e.g. `route`) |
| `_endpoint` | Endpoint / resource id (e.g. `products`) |
| `_nexus_env` | `NEXUS_ENV` (e.g. `dev`) |
| `_dlt_load_id` / `_dlt_id` | dlt package / row ids (system; may differ from `run_id`) |

dlt also writes `_dlt_*` system tables (loads, version, pipeline state). Keep them. They are ingestion telemetry, not a logging product.

---

## Schema evolution

dlt may add columns when the JSON grows. Bronze stays wide/variant-friendly. Breaking renames are a **new resource or a dbt mapping**, not silent overwrites of history. Downstream `stg_*` binds types and names.

---

## Out of scope for dlt

SCD1/SCD2, conformed keys, facts, events grain, domain marts, dbt tests as the quality gate. Those are [dbt-modeling.md](dbt-modeling.md).
