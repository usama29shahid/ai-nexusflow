# dlt extraction (dlt_dbt_clickhouse)

dlt is the **REST extraction and load** layer. It is not the dimensional model.

For **dlt_dbt_clickhouse**, runnable pipelines live under `branches/dlt_dbt_clickhouse/dlt/{source}/`. Repo `ingestion/sources/` stays a stub until another backend needs the same REST client. They run on the **host** with `uv run`, not inside Docker.

This document is the org standard for RAG and for future generated pipelines. Pipelines are **not implemented yet**. GitHub source semantics: [github-ingestion.md](github-ingestion.md).

---

## What dlt does

1. Call the REST API (auth, pagination, retries, rate limits).
2. Optionally apply **incremental** state (cursor / `updated_at` / since).
3. Stamp rows with a shared **`run_id`** (see [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md): local generator until Airflow, then DAG run_id).
4. Write **once** to two destinations:
   - MinIO: immutable JSONL archive (replay) in `nexus-dlt-dbt-clickhouse-{env}`.
   - ClickHouse `raw_{source}_{env}` (e.g. `raw_github_dev`): append-only Bronze.
5. Keep **pipeline state** (incremental cursors, schema) in dlt — not a custom watermark table.

**dlt stops at archive + Bronze.** Staging, intermediate, Gold, marts, and tests are dbt-only. dlt may create nested/child tables from JSON; leave them in Bronze and flatten in dbt `stg_*`.

---

## Pipeline grain

| Grain | Rule |
| --- | --- |
| **Source** | pokeapi, dataforseo, github, … — Airflow DAG grain later |
| **Endpoint pipeline** | One dlt script (or REST resource) per endpoint; name the script after the resource (`pull_requests.py`, not `pipe_one.py`) |
| **Param variant** | Separate pipeline/table only if payload **contract** differs (schema, grain, auth, incremental). Same schema, different URL id → parameters on one pipeline; later Airflow may run multiple jobs with different params |

Code layout (when implemented):

```text
branches/dlt_dbt_clickhouse/dlt/{source}/   # endpoint pipelines → raw_{source}_{env}
  # e.g. github/commits.py, github/pull_requests.py, github/issues.py
ingestion/sources/                          # stub until a second backend shares REST defs
```

---

## Authentication

Configure per source. Secrets from the environment — injected by [HashiCorp Vault Agent](vault.md) on the VPS (`NEXUS_SECRETS_BACKEND=vault`) or from `.env` for local bootstrap (`NEXUS_SECRETS_BACKEND=env`). Never commit keys.

| Pattern | When |
| --- | --- |
| None / public | e.g. pokeapi |
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

- Connect/read **timeouts** per source.
- **Retry** on transient failures; do not retry 401/403/404 as if they were flakes (fix auth or the path).
- **429:** honor `Retry-After` when present.
- Optional **rate limiter** if the API publishes a quota.

Airflow (Phase 2) retries the **task**. dlt retries **HTTP calls inside** the task. Those are different layers; both are valid. Do not build a third retry daemon.

---

## Incremental extraction

When the API supports it:

- dlt `incremental` on a cursor field (`updated_at`, `id`, `since`).
- State stored by dlt pipeline name + dataset.
- Each run still **appends** Bronze with a new `run_id`. Incremental reduces API volume; it does not overwrite history.

When the API is full-refresh only: extract the snapshot, archive it, append Bronze. dbt dedupes to “current” using `run_id` / business keys.

---

## Dual destination and archive keys

Extract once in memory (or one normalize pass), then:

1. **Filesystem / S3 destination** → MinIO bucket `nexus-dlt-dbt-clickhouse-{env}` from `NEXUS_ENV` (default `dev` → `nexus-dlt-dbt-clickhouse-dev`; see [environments.md](environments.md)). The dlt **job name** is not the bucket.
2. **ClickHouse destination** → database `raw_{source}_{env}` (e.g. `raw_github_dev`), MergeTree-style append.

Replay mode (later): **do not call the API**. Read JSONL from the prefix, load Bronze with a **new** `run_id`, run dbt.

---

## Metadata on Bronze rows

Every load should carry at least:

| Column | Meaning |
| --- | --- |
| `run_id` / `_ingest_run_id` | Shared run id (local generator until Airflow; then DAG run_id) |
| `_extracted_at` | Extract timestamp (UTC) |
| `_dlt_load_id` | dlt package id (telemetry; may differ from `run_id`) |
| source + resource names | pokeapi / pokemon, etc. |

dlt also writes `_dlt_*` system tables (loads, version, pipeline state). Keep them. They are ingestion telemetry, not a logging product.

---

## Schema evolution

dlt may add columns when the JSON grows. Bronze stays wide/variant-friendly. Breaking renames are a **new resource or a dbt mapping**, not silent overwrites of history. Downstream `stg_*` binds types and names.

---

## Out of scope for dlt

SCD1/SCD2, conformed keys, facts, events grain, domain marts, dbt tests as the quality gate. Those are [dbt-modeling.md](dbt-modeling.md).
