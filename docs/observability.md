# Observability and logging

Do **not** build a custom logging UI or a ClickHouse “ops log” table. Pipeline code writes to a **tool-agnostic observability data lake** on MinIO. Observability products are **optional readers** that ingest from the lake into their **own native databases** (indexes for UI speed — not the system of record).

| Concern | Owner | Where it lives |
| --- | --- | --- |
| Did the DAG/task run? duration, retries, stdout | **Airflow** | Airflow Postgres metadata + **remote task logs** in MinIO `nexus-airflow-logs-{env}` |
| Did extract/load succeed? packages, schema, row counts | **dlt** | `_dlt_*` tables in the warehouse; load **events** in the observability lake |
| Did transforms and tests succeed? | **dbt** | `target/` on host; **artifacts copied** to the observability lake after each run |
| Pipeline traces, metrics, structured events | **OpenTelemetry** → OTel Collector → lake | MinIO `nexus-telemetry-{env}/otel/` |
| Data catalog / lineage (read) | **OpenMetadata** (current) | OM Postgres + Elasticsearch — **index** fed by lake + warehouse connectors |
| Pipeline trace UI (read) | **SigNoz** (current) | SigNoz internal store — **index** fed by lake replay |
| dbt DQ history (read) | **Elementary** (current) | `elementary_{env}` in warehouse — **index**; lake holds `run_results.json` archives |
| Which rows came from which run? | **data** | `run_id` on Bronze, carried in dbt where needed |

A pipeline run is **not complete** until it writes to the observability lake (`summaries/runs/{run_id}.json`, dbt artifacts when dbt ran, OTLP batches when the collector is up). SigNoz, OpenMetadata, and Elementary **do not need to be running** during the run.

See also: [architecture.md](architecture.md), [roadmap.md](roadmap.md), [environments.md](environments.md).

---

## Observability data lake (system of record)

**Bucket:** `nexus-telemetry-{env}` (e.g. `nexus-telemetry-dev` until Terraform).

**Role:** Durable, vendor-neutral archive for migration. If SigNoz, OpenMetadata, or Elementary are replaced later, replay or re-ingest from this bucket — **do not** change dlt/dbt/Airflow emit code.

**Layout:**

```text
nexus-telemetry-{env}/
├── otel/traces|logs|metrics/...     # OTLP batches (Collector export)
├── events/pipeline/...              # nexus.telemetry/v1 JSONL (dlt, dbt)
├── events/airflow/...               # DAG/task lifecycle events
├── artifacts/dbt/
│   ├── dlt_dbt_clickhouse/{run_id}/ # manifest.json, run_results.json, catalog.json
│   └── dlt_dbt_spark_iceberg/{run_id}/
└── summaries/runs/{run_id}.json     # per-run rollup (manual or Airflow)
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

| Output | Destination |
| --- | --- |
| Spans + `dlt.load.*` events (row counts, pipeline name, status) | OTLP → OTel Collector → `nexus-telemetry-{env}/otel/` and `events/` |
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

**One DAG per source** per enabled branch (e.g. `nexus_route_clickhouse`, `nexus_route_lakehouse`):

1. Task(s) per endpoint dlt pipeline (archive + Bronze).
2. One `dbt run` / `dbt test` with **selectors** for downstream models.
3. `observability_publish` — artifact upload to lake, run summary, optional Elementary `edr report` when implemented.

Not one DAG per REST URL. Domain marts: dbt selector only. Only **enabled** branches in [config/branches.yaml](../config/branches.yaml) get DAGs.

Compose profile: `airflow`. Smoke DAG: `nexus_airflow_smoke` in [orchestration/airflow/dags/](../orchestration/airflow/dags/). Host dlt/dbt run via task commands — no `.venv` bind-mount in Airflow containers.

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

`prd` suffixes after Terraform.

---

## Reader tools (Phase 2)

SigNoz, OpenMetadata, and Elementary Compose profiles may exist locally. **Product setup** (each tool’s native config, lake→index ingest, dashboards) is Phase 2. Phase 1 still requires full lake writes via `common/observability` whether or not those UIs are running.

## Phase 3 UI and agents (future)

- **Supabase** — user auth and session memory (not pipeline telemetry).
- **Qdrant** — RAG over org standards in `docs/` (not pipeline telemetry).
- **Streamlit** — summarizes lake `summaries/` and links to Airflow, SigNoz, OpenMetadata, Elementary; does not replace them.

Validation agents must reject generated pipelines that omit `common/observability` hooks or lake artifact upload.

---

## Do not

- Build a custom logging microservice or ops dashboard as the system of record.
- Store pipeline telemetry only in Supabase, Qdrant, or ClickHouse ops tables.
- Call SigNoz / OpenMetadata / Elementary from dlt or dbt code.
- Replace SigNoz/OM/Elementary native DBs with MinIO-as-primary for those products.
- Skip lake writes when an observability UI is up.
