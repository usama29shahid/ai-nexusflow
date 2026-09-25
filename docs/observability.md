# Observability and logging

Do **not** build a custom logging UI or a ClickHouse “ops log” table. Pipeline code writes to a **tool-agnostic observability data lake** on MinIO. Observability products are **optional readers** that ingest from the lake into their **own native databases** (indexes for UI speed — not the system of record).

| Concern | Owner | Where it lives |
| --- | --- | --- |
| Did the DAG/task run? duration, retries, stdout | **Airflow** | Airflow Postgres metadata + **remote task logs** in MinIO `nexus-airflow-logs-{env}` |
| Did extract/load succeed? packages, schema, row counts | **dlt** | `_dlt_*` tables in the warehouse; load **events** in the observability lake |
| Did transforms and tests succeed? | **dbt** | `target/` on host; **artifacts copied** to the observability lake after each run |
| Pipeline traces, metrics, structured events | **OpenTelemetry** → OTel Collector → lake | MinIO `nexus-telemetry-{env}/otel/` |
| Data catalog / lineage (read) | **OpenMetadata** (current) | OM Postgres + Elasticsearch — **index** fed by lake + warehouse connectors |
| Pipeline trace UI (read) | **SigNoz** (current) | SigNoz internal store — **index** fed by **live OTLP** (collector forward) and **lake replay** (backlog item **2**; `observability-ingest.sh signoz`) |
| dbt DQ history (read) | **Elementary** (current) | `elementary_{env}` in warehouse — **index**; lake holds `run_results.json` archives |
| Which rows came from which run? | **data** | `run_id` on Bronze, carried in dbt where needed |

A pipeline run is **not complete** until it writes to the observability lake (`summaries/runs/{run_id}.json`, dbt artifacts when dbt ran, OTLP batches when the collector is up). SigNoz, OpenMetadata, and Elementary **do not need to be running** during the run.

See also: [architecture.md](architecture.md), [backlog.md](backlog.md), [roadmap.md](roadmap.md), [environments.md](environments.md).

---

## Observability data lake (system of record)

**Bucket:** `nexus-telemetry-{env}` (e.g. `nexus-telemetry-dev` until `prd` / backlog **10**).

**Role:** Durable, vendor-neutral archive for migration. If SigNoz, OpenMetadata, or Elementary are replaced later, replay or re-ingest from this bucket — **do not** change dlt/dbt/Airflow emit code.

**Layout:**

```text
nexus-telemetry-{env}/
├── otel/{YYYY}/{MM}/{DD}/{HH}/{MM}/   # OTLP batches (Collector awss3; files traces_|metrics_|logs_*.json)
├── events/pipeline/...              # nexus.telemetry/v1 JSONL (dlt, dbt)
├── events/airflow/...               # DAG/task lifecycle events
├── artifacts/dbt/
│   ├── dlt_dbt_clickhouse/{run_id}/ # manifest.json, run_results.json, catalog.json
│   └── dlt_dbt_spark_iceberg/{run_id}/
├── artifacts/elementary/{branch}/{run_id}/  # elementary_report.html
├── summaries/runs/{run_id}.json     # per-run rollup (manual or Airflow)
└── indexes/signoz/...               # lake→SigNoz ingest markers (reader bootstrap)
```

**Write contract (implementation):** host Python and Airflow tasks use `common/observability`. Pipeline code **must not** call SigNoz, OpenMetadata, or Elementary APIs directly.

**Schema:** structured events use `nexus.telemetry/v1` with required attributes: `nexus.run_id`, `nexus.env`, `nexus.branch`, `nexus.component`, optional `nexus.dag_id`, `nexus.task_id`, `nexus.source`, `nexus.endpoint`.

---

## Tool-native stores (indexes — do not replace)

| Product | Native store | Purpose |
| --- | --- | --- |
| SigNoz | Internal ClickHouse (SigNoz stack) | Trace/metric queries and UI |
| OpenMetadata | Postgres + Elasticsearch | Catalog search and lineage graph |
| Elementary | ClickHouse or Trino `elementary_{env}` | dbt test trends and anomaly UI |

Run each product’s Compose profile as upstream documents intend. Use batch ingest (`scripts/observability-ingest.sh`) to project **lake → tool native store** when reader profiles are enabled. Do **not** point those products at MinIO as their primary database.

**Lake = archive. Tool DB = index. Never skip the lake write because a tool UI is running.**

---

## What each emitter produces

### dlt

Every endpoint pipeline must emit on **success and failure** via `common.observability.publish.publish_dlt_load` (see reference [`products.py`](../branches/dlt_dbt_clickhouse/dlt/route/products.py) and [dlt-extraction.md](dlt-extraction.md)):

| Output | Destination |
| --- | --- |
| Lake events `dlt.load.completed` / `dlt.load.failed` + `summaries/runs/{run_id}.json` | Direct MinIO via `common/observability` (required path) |
| Best-effort OTLP span `dlt.load` + counter `nexus.dlt.rows_loaded` | OTLP → OTel Collector → `nexus-telemetry-{env}/otel/` (must not fail the pipeline if the collector is down) |
| Optional parent span (e.g. `route.products.load`) | Same OTLP path; setup must be best-effort; nest `publish_dlt_load` under the parent when present |
| `_dlt_loads`, `_dlt_version`, pipeline state | Warehouse `_dlt_*` tables (ingestion metadata, not the observability lake) |
| Console stdout | Airflow remote log when task is orchestrated → `nexus-airflow-logs-{env}` |

### dbt

| Output | Destination |
| --- | --- |
| `manifest.json`, `run_results.json`, `catalog.json`, `sources.json` | **MinIO direct** → `artifacts/dbt/{branch}/{run_id}/` |
| Run/test duration and summary | OTLP → Collector → `otel/` + `events/` |
| Local `target/` | Host disk; copy artifacts to lake after run |

### Airflow (Phase 1)

| Output | Destination |
| --- | --- |
| Task stdout/stderr | **`nexus-airflow-logs-{env}`** (remote logging — ops text, not duplicated into `otel/`) |
| DAG run state, retries, schedule | Airflow Postgres |
| DAG/task spans + run summary | OTLP → Collector → `otel/` + `summaries/runs/{run_id}.json` |

---

## OTel Collector vs direct MinIO writes

| Path | Contents |
| --- | --- |
| **OTLP → OTel Collector → MinIO** | Traces, metrics, structured log records (streams) |
| **SDK direct → MinIO** | dbt JSON artifacts, run summary files (blobs — wrong shape for OTLP) |

The Collector is the **ingestion gateway** (swappable). MinIO is the **durable store** (fixed layout). Collector listens on `127.0.0.1:4317` (host) and `otel-collector:4317` (Compose network for Airflow). Starts always-on with MinIO (no profile). When the SigNoz reader profile is off, the collector exports to the lake only; `./scripts/start.sh signoz` switches to `collector-config.signoz.yaml` and forwards a copy to SigNoz.

---

## Execution modes (same emit map)

| Mode | Trigger | `NEXUS_RUN_ID` |
| --- | --- | --- |
| **Manual** | `./scripts/start.sh smoke`, `./scripts/start.sh dbt ...` | `local-{utc_timestamp}` or explicit env |
| **Airflow** | DAG schedule or UI trigger | Airflow DAG **`run_id`** |

Pass the **same** `NEXUS_RUN_ID` into dlt (Bronze column), dbt `var('run_id')`, and all telemetry events.

---

## Airflow DAG grain (Phase 1)

**One DAG per source + target + endpoint** (e.g. `route_clickhouse_products`). Each file appears in the Airflow UI. Only **enabled** capabilities in [config/branches.yaml](../config/branches.yaml) may run (`assert_branch_enabled`).

Layer tasks (never `dbt build`):

1. `assert_branch_enabled`
2. `bronze` — that endpoint’s dlt pipeline (archive + Bronze, extract once)
3. `silver` — `dbt run` then `dbt test` for that endpoint’s staging tags
4. `gold` — `dbt run` then `dbt test` for that endpoint’s gold tags
5. `mart` — only when mart models exist
6. `observability` — on success: `dbt docs generate`, Elementary `edr report`, lake artifact copy, `airflow.dag.completed`
7. `observability_failed` — `trigger_rule=one_failed`: lake summary `airflow.dag.failed` (no docs/edr). Runs if any layer or the success closer fails.

Compose profile: `airflow`. Smoke DAG: `nexus_airflow_smoke`. Orchestrated dlt/dbt via ephemeral `nexus-elt` containers — no `.venv` bind-mount in Airflow. See [architecture.md](architecture.md), [orchestration/airflow/README.md](../orchestration/airflow/README.md).

The future LLM workflow agent should emit this DAG shape.

---

## Current observability stack (swappable readers)

| Layer | Current choice | Profile |
| --- | --- | --- |
| Ingestion gateway | OpenTelemetry SDK + OTel Collector | always on with MinIO |
| Pipeline UI | SigNoz | `signoz` (on-demand local; always-on VPS) |
| Data catalog | OpenMetadata | `openmetadata` |
| dbt DQ | Elementary | host `edr` + dbt package |

Readers ingest from the lake on a schedule or via `./scripts/observability-ingest.sh`. Replacing a reader does not require regenerating pipelines.

---

## Cross-branch scope

Both `dlt_dbt_clickhouse` and `dlt_dbt_spark_iceberg` use the same lake and SDK. Branch isolation: `nexus.branch` attribute and `artifacts/dbt/{branch}/{run_id}/` prefix.

| Branch | Elementary store (index) | OpenMetadata ingest |
| --- | --- | --- |
| `dlt_dbt_clickhouse` | ClickHouse `elementary_{env}` | ClickHouse connector + dbt artifacts |
| `dlt_dbt_spark_iceberg` | Trino `nexus_{env}.elementary` | Trino connector + dbt artifacts |

Milestone 1 implements the lake + instrumentation for the ClickHouse branch; lakehouse branch follows in Milestone 2.

---

## MinIO buckets (data vs logs vs observability)

| Bucket | Contents |
| --- | --- |
| `nexus-dlt-dbt-clickhouse-{env}` | Raw API JSONL — **data archive** |
| `nexus-dlt-dbt-spark-iceberg-archive-{env}` | Lakehouse JSONL archive — **data** |
| `nexus-dlt-dbt-spark-iceberg-{env}` | Iceberg warehouse — **data** |
| `nexus-airflow-logs-{env}` | Airflow task stdout — **ops logs** |
| **`nexus-telemetry-{env}`** | **Observability data lake** |

`prd` suffixes after backlog item **10**.

---

## Reader tools (backlog items 2–3)

SigNoz and OpenMetadata Compose profiles exist locally. **Product setup** is backlog items **2–3**.

**SigNoz (item 2) includes both:**

1. **Live OTLP** — collector forwards to SigNoz while the profile is up ([docker/otel/](../docker/otel/)). Start with **`./scripts/start.sh signoz`** only (not bare Compose): it writes `SIGNOZ_TOKENIZER_JWT_SECRET` when missing and runs [`scripts/signoz-ensure.sh`](../scripts/signoz-ensure.sh) so the standalone ingester listens on `:4317`/`:4318` (Compose health requires UI **and** OTLP). If the trace index is empty after a wipe, replay the lake (`observability-ingest.sh signoz -- --force --since …`) or set `SIGNOZ_AUTO_REPLAY=1`.
2. **Lake → SigNoz** — `./scripts/observability-ingest.sh signoz` lists `nexus-telemetry-{env}/otel/` JSON batches and POSTs them into SigNoz OTLP HTTP from inside the container (backfill / SigNoz-was-down). Idempotent via `indexes/signoz/*.ingested`; `--force` re-posts after a SigNoz wipe (may duplicate spans). Default window is **last 24h** — pass `--since` for older lake history.
3. **Products dashboard** — [`docker/signoz/dashboards/route-products.json`](../docker/signoz/dashboards/route-products.json) via [`scripts/signoz-bootstrap.sh`](../scripts/signoz-bootstrap.sh) (`SIGNOZ_API_KEY` preferred; `SIGNOZ_BOOTSTRAP_SQLITE=1` last resort). Edit the JSON in git, re-run bootstrap to create or update. Not run on every `start.sh signoz`. Traces filter: `serviceName = nexusflow.dlt` and attribute `nexus.run_id`.

OpenMetadata (item **3**) similarly gets warehouse connectors + catalog views; its lake projection can follow the same ingest script pattern (`openmetadata` target) when that item runs.

Local Terraform is backlog **5**; GitHub Actions / VPS / `prd` are backlog **10**. Lake writes via `common/observability` remain required whether or not those UIs are running. Pipeline code must not call those APIs. Order: [backlog.md](backlog.md).

## App UI and agents (backlog 11–12)

- **Supabase** — user auth and session memory (not pipeline telemetry) — backlog **11**.
- **Qdrant** — RAG over org standards in `docs/` (not pipeline telemetry) — backlog **12**.
- **Streamlit** — summarizes lake `summaries/` and links to Airflow, SigNoz, OpenMetadata, Elementary; does not replace them — backlog **11**.

Validation agents must reject generated pipelines that omit `common/observability` hooks or lake artifact upload.

---

## Do not

- Build a custom logging microservice or ops dashboard as the system of record.
- Store pipeline telemetry only in Supabase, Qdrant, or ClickHouse ops tables.
- Call SigNoz / OpenMetadata / Elementary from dlt or dbt code.
- Replace SigNoz/OM/Elementary native DBs with MinIO-as-primary for those products.
- Skip lake writes when an observability UI is up.
