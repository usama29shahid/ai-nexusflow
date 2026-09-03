# Roadmap

Build a **working ELT foundation first**. Add Terraform/CI, reader-tool dashboards, and LLM only when the previous layer is runnable and has a clear purpose.

Each phase must be **runnable**, not a folder of stubs. Later agents generate and **select** these branches; they should not invent a platform that was never built.

```text
Phase 1  Two capabilities + Airflow + observability producers
Phase 2  Terraform (dev/prd) + GitHub Actions + reader tools
Phase 3  LLM: multi-agent + RAG + Streamlit (live app)
```

This shows **senior DE** (warehouse, open lakehouse, Airflow, observability lake) **and** later **ops polish** (Terraform, CI, SigNoz/OpenMetadata/Elementary) **and** **LLM/AI** (agents that consume those capabilities).

Complete Phase 1 before Phase 2 or Phase 3 work.

---

## Phase 1 — Capabilities, Airflow, and observability producers

Same source problem, **two** independent backends — plus **orchestration** and a **tool-agnostic observability data lake** from the first milestone.

**Do not start dlt_dbt_spark_iceberg until dlt_dbt_clickhouse is verified.**

Python, uv, DLT, and dbt stay on the **host**. Docker Compose runs MinIO (always), branch stacks (`clickhouse`, `lakehouse`), **Airflow** (`airflow` profile), OTel Collector, and optional reader Compose profiles (`signoz`, `openmetadata`).

### Observability (Phase 1 — all milestones)

```text
dlt / dbt / Airflow  →  common/observability  →  OTel Collector  →  MinIO nexus-telemetry-{env}
                                              →  artifacts + summaries (direct MinIO)
```

- **System of record:** MinIO `nexus-telemetry-{env}` — neutral formats for migration ([observability.md](observability.md)).
- **Required per run:** `NEXUS_RUN_ID`, run summary in lake, dbt artifacts copied after dbt, OTLP when collector is up.
- **Airflow task stdout:** `nexus-airflow-logs-{env}` — separate from the telemetry lake.
- **Readers (Phase 2):** SigNoz, OpenMetadata, Elementary keep their **own DBs as indexes**; product setup and lake→tool ingest belong in Phase 2. Pipeline code still must not call those tools directly.

Implementation order within Phase 1: telemetry bucket + Collector + SDK first; **instrument dlt/dbt/Airflow so every run writes to the lake**.

### Milestone 1 — dlt_dbt_clickhouse + Airflow + observability foundation

```text
Source → DLT → MinIO archive (JSONL) + ClickHouse raw (Bronze, append)
      → dbt stg_* / Gold (ClickHouse)
      → telemetry lake (every run)
Airflow → DAG per source (smoke, then first REST source) → same dlt/dbt on host
```

- One stable REST source: **Route API** (`route`) — catalog-first (`products`, `categories`, `brands`); see [route-ingestion.md](route-ingestion.md)
- DLT: dual destination — MinIO **archive** (`nexus-dlt-dbt-clickhouse-dev`) + ClickHouse `raw_{source}_dev`
- dbt target `dev`; models and tests in `branches/dlt_dbt_clickhouse`
- Shared `NEXUS_RUN_ID` into dlt and dbt (`local-*` manual; Airflow DAG `run_id` when orchestrated)
- Observability lake writes verified for manual and Airflow-triggered runs
- Airflow: smoke DAG + first source DAG for enabled `dlt_dbt_clickhouse`; remote logs to MinIO
- Verify row counts, dbt tests, and lake objects under `nexus-telemetry-dev/`
- Enhanced modeling (SCD variants, soft delete, hash keys): backlog only — [enhanced-modeling-strategy.md](enhanced-modeling-strategy.md)

MinIO archive buckets are **raw API replay**, not the observability lake. See [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md) and [observability.md](observability.md).

### Milestone 2 — dlt_dbt_spark_iceberg

```text
Source → DLT → MinIO JSONL archive
      + Iceberg Bronze (Apache Polaris, nexus_dev.raw_{source})
      → dbt-spark → Iceberg gold / marts → Trino
      → same observability lake contract (branch tag dlt_dbt_spark_iceberg)
Airflow → lakehouse source DAGs when branch enabled
```

Open-source lakehouse. Folder: `branches/dlt_dbt_spark_iceberg`. Standards: [dlt-dbt-spark-iceberg.md](dlt-dbt-spark-iceberg.md).

**Phase 1 done when:** both pipelines run, Airflow orchestrates enabled branches, the observability lake receives every run, and you can show data in ClickHouse and Iceberg/MinIO (Trino).

---

## Phase 2 — Terraform, GitHub Actions, and reader tools

Compose already exists for local services. This phase is **env promotion**, **CI**, and **reader product setup**.

- Terraform **dev** and **prd** (prd is when `-prd` buckets and `*_prd` databases are created)
- GitHub Actions for lint/test/deploy as appropriate
- Repeatable ClickHouse / MinIO / Airflow / observability stack wiring
- Secrets and networking; no keys in git
- SigNoz, OpenMetadata, and Elementary: each tool’s install/config and lake→native-store ingest so dashboards work ([observability.md](observability.md))

Phase 1 already writes the lake; Phase 2 makes the reader UIs useful.

---

## Phase 3 — LLM, multi-agent, RAG, Streamlit

```text
Streamlit → Planner → RAG (org standards) → ELT spec
  → Ingestion / Transform / Branch / Workflow agents
  → Validation → Airflow → result
```

- LangGraph specialized agents (not one mega-prompt)
- RAG (Qdrant): naming, bronze/silver, DLT/dbt/Spark, Airflow and **observability contract** rules
- Supabase: auth and user session memory
- Streamlit: request, retrieved rules, spec, generated artifacts, run status from lake summaries
- Validation agent rejects pipelines missing observability hooks or disabled branches

Details: [architecture.md](architecture.md), [platform-showcase-vision.md](platform-showcase-vision.md).

---

## Current status

### Completed

- [x] GitHub repository `ai-nexusflow`
- [x] WSL2 + Docker Desktop WSL integration
- [x] Docker Compose: ClickHouse + MinIO
- [x] Docker Compose profile `airflow` (Postgres + LocalExecutor + MinIO remote logs + `nexus_airflow_smoke`)
- [x] Python project with uv (`pyproject.toml`, `uv.lock`)
- [x] DLT, dbt-core, dbt-clickhouse
- [x] dbt project `nexus_clickhouse` initialized (`branches/dlt_dbt_clickhouse`)
- [x] End-goal folder skeleton and `scripts/setup.sh`
- [x] Python / DLT / dbt versions verified
- [x] `.venv` permission issue identified and resolved
- [x] Development architecture documented (`docs/`)
- [x] Observability architecture documented (data lake, Airflow Phase 1, reader model)

### Current versions

```text
Python          3.12.12
DLT             1.30.0
dbt-core        1.11.13
dbt-clickhouse  1.10.2
```

### Not implemented yet

- [x] Observability foundation: `nexus-telemetry-{env}` bucket, OTel Collector, `common/observability` SDK
- [x] SigNoz / OpenMetadata reader Compose profiles (`signoz`, `openmetadata`) — containers only; product setup is Phase 2
- [ ] Pipeline instrumentation (dlt/dbt/Airflow wired to lake on every run) — Phase 1
- [ ] DLT ingestion pipeline (dlt_dbt_clickhouse) — Phase 1
- [ ] ClickHouse bronze / dbt silver + tests — Phase 1
- [ ] MinIO archive + Iceberg / Polaris / dbt-spark / Trino (dlt_dbt_spark_iceberg) — Phase 1
- [ ] Airflow source/ELT DAGs beyond smoke (profile + smoke DAG exist) — Phase 1
- [ ] Engine RBAC cutover — **held** (not Milestone 1); intent only in [rbac.md](rbac.md)
- [ ] Terraform dev/prod — Phase 2
- [ ] GitHub Actions — Phase 2
- [ ] SigNoz / OpenMetadata / Elementary lake ingest and dashboards — Phase 2
- [ ] LLM ELT generator, RAG, Streamlit — Phase 3

---

## Immediate next step

**Phase 1 Milestone 1:** implement and verify **dlt_dbt_clickhouse** with the **observability data lake contract** and **Airflow** source DAGs:

```text
REST → dlt → MinIO archive + ClickHouse Bronze → dbt → lake telemetry
Airflow DAG (same scripts, DAG run_id = NEXUS_RUN_ID)
```

No Spark or LLM in that slice. Reader tool dashboards (SigNoz, OpenMetadata, Elementary) are Phase 2 after lake writes are proven.

Guiding principle:

> **Build a simple, working ELT foundation first. Every pipeline run lands on the observability lake. Observability products are readers, not write dependencies.**

The objective is every capability as a reliable, independently selectable backend that an LLM agent can choose from a user’s data-engineering requirement.
