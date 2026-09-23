# Roadmap

**Delivery order (what to build next):** [backlog.md](backlog.md) — execute one item at a time. This file is **portfolio / capability context** and a status checklist. When this file and the backlog disagree, **follow the backlog**.

Build a **working ELT foundation first**. Phases below are **labels** for the resume story (warehouse + lakehouse + ops + LLM). They are **not** hard gates: readers, MinIO IAM, and local Terraform may land before Iceberg when the backlog says so.

Each capability must be **runnable**, not a folder of stubs. Later agents generate and **select** these branches; they should not invent a platform that was never built.

```text
Portfolio labels (not a strict build gate):
  Capabilities   Warehouse + lakehouse + Airflow + lake producers
  Platform ops   Readers, MinIO IAM, local Terraform, VPS/Actions, docs auth
  App / AI       Supabase, Streamlit, RAG / multi-agent
```

Map to numbers: [backlog.md](backlog.md) items 0–12.

---

## Capabilities — warehouse, lakehouse, Airflow, lake

Same source problem, **two** independent backends — plus **orchestration** and a **tool-agnostic observability data lake**.

**Do not start `dlt_dbt_spark_iceberg` until `dlt_dbt_clickhouse` is verified** (warehouse `products` path done). Iceberg ELT is backlog **item 6**, after stack verify, readers, MinIO IAM, and local Terraform (items 1–5).

Python, uv, DLT, and dbt stay on the **host**. Docker Compose runs MinIO (always), branch stacks (`clickhouse`, `lakehouse`), **Airflow** (`airflow` profile), OTel Collector, and optional reader Compose profiles (`signoz`, `openmetadata`).

### Observability (producers vs readers)

```text
dlt / dbt / Airflow  →  common/observability  →  OTel Collector  →  MinIO nexus-telemetry-{env}
                                              →  artifacts + summaries (direct MinIO)
```

- **System of record:** MinIO `nexus-telemetry-{env}` — neutral formats for migration ([observability.md](observability.md)).
- **Required per run:** `NEXUS_RUN_ID`, run summary in lake, dbt artifacts copied after dbt, OTLP when the collector is up.
- **Airflow task stdout:** `nexus-airflow-logs-{env}` — separate from the telemetry lake.
- **Readers:** SigNoz, OpenMetadata, Elementary keep their **own DBs as indexes**. Compose profiles already exist; **product setup / dashboards** are backlog items **2–3** (and Elementary polish with docs auth in item **9**). Pipeline code must not call those tools directly.

Producers (lake writes) landed with the warehouse `products` path. Reader UIs do **not** wait for Iceberg or VPS.

### Warehouse reference — `dlt_dbt_clickhouse` + Airflow

```text
Source → DLT → MinIO archive (JSONL) + ClickHouse raw (Bronze, append)
      → dbt stg_* / Gold (ClickHouse)
      → telemetry lake (every run)
Airflow → one DAG per source + target + endpoint (nexus-elt job image via docker run)
```

- Ephemeral **`nexus-elt`** job image is the **current** worker bridge. Decision: [architecture.md](architecture.md). Copy `route_clickhouse_products` for later endpoints.
- One stable REST source: **Route API** (`route`) — catalog-first (`products`, `categories`, `brands`); see [route-ingestion.md](route-ingestion.md)
- DLT: dual destination — MinIO **archive** (`nexus-dlt-dbt-clickhouse-{env}`) + ClickHouse `bronze_{env}.raw_{source}__{endpoint}`
- **Done (backlog item 0):** Route `products` full-refresh dlt → archive + Bronze + lake events/OTLP; Airflow `route_clickhouse_products`; silver / Gold SCD2 ([gold-products-cutover.md](gold-products-cutover.md), [dlt-extraction.md](dlt-extraction.md))
- **Done (backlog item 1):** local stack health via `./scripts/start.sh verify`.
- **Next (follow [backlog.md](backlog.md)):** item **2** SigNoz → **3** OpenMetadata → … Catalog endpoints `categories` / `brands` are backlog item **7** (after Iceberg parity), not the immediate next step.
- dbt target `dev`; models and tests in `branches/dlt_dbt_clickhouse`
- Shared `NEXUS_RUN_ID` into dlt and dbt (`local-*` manual; Airflow DAG `run_id` when orchestrated)
- Enhanced modeling (SCD variants, soft delete, hash keys): later modeling notes — [enhanced-modeling-strategy.md](enhanced-modeling-strategy.md); facts/marts/semantic layer = backlog item **8**

MinIO archive buckets are **raw API replay**, not the observability lake. See [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md) and [observability.md](observability.md).

### Lakehouse — `dlt_dbt_spark_iceberg` (backlog item 6)

```text
Source → DLT → MinIO JSONL archive
      + Iceberg Bronze (Apache Polaris, nexus_dev.raw_{source})
      → dbt-spark → Iceberg gold / marts → Trino
      → same observability lake contract (branch tag dlt_dbt_spark_iceberg)
Airflow → lakehouse source DAGs when branch enabled
```

Open lakehouse. Folder: `branches/dlt_dbt_spark_iceberg`. Standards: [dlt-dbt-spark-iceberg.md](dlt-dbt-spark-iceberg.md).

**Both capabilities “done” when:** warehouse and lakehouse products-style paths run under Airflow, the lake receives every run, and you can show data in ClickHouse and Iceberg/MinIO (Trino). That aligns with backlog through item **6**, not a gate that blocks items 1–5.

---

## Platform ops — readers, IAM, Terraform, VPS (backlog 1–5, 9–10)

Compose already exists for local services. Delivery order is [backlog.md](backlog.md):

| Backlog | What |
| --- | --- |
| **1** | Stack verify (done — `./scripts/start.sh verify`) |
| **2** | SigNoz — live OTLP dashboards + lake→SigNoz ingest |
| **3** | OpenMetadata product setup / catalog |
| **4** | MinIO IAM (admin / reader / loader-style) |
| **5** | Local HashiCorp Terraform (API resources; BSL; no OpenTofu/Ansible) |
| **9** | Basic auth for Elementary + dlt/dbt docs HTML (Caddy) |
| **10** | VPS + GitHub Actions — both branches E2E, edge/DNS/`prd` naming |

**CI/CD intent (when item 10 lands):** GitHub Actions is the primary path (lint, test, build, `terraform plan/apply`, VPS deploy). Local Terraform (item **5**) configures resources against Compose; it does **not** replace Actions deploy or `./scripts/start.sh`. Details: [ci-cd.md](ci-cd.md), [edge-proxy.md](edge-proxy.md).

Readers stay indexes with their own DBs; pipeline code still must not call SigNoz/OpenMetadata APIs ([observability.md](observability.md)).

---

## App / AI — Supabase, Streamlit, RAG (backlog 11–12)

```text
Streamlit → Planner → RAG (org standards) → ELT spec
  → Ingestion / Transform / Branch / Workflow agents
  → Validation → Airflow → result
```

- **Item 11:** Supabase (auth/session) + Streamlit shell
- **Item 12:** LangGraph agents + RAG (Qdrant) over org standards and the **semantic layer** (item **8** first)
- Validation rejects pipelines missing observability hooks or disabled branches

Details: [architecture.md](architecture.md), [platform-showcase-vision.md](platform-showcase-vision.md). Do not start RAG before backlog items **8** and **11**.

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

### Not implemented yet (see [backlog.md](backlog.md) for order)

- [x] Observability foundation: `nexus-telemetry-{env}` bucket, OTel Collector, `common/observability` SDK
- [x] SigNoz / OpenMetadata reader Compose profiles (`signoz`, `openmetadata`) — containers only
- [x] Pipeline instrumentation (dlt/dbt/Airflow wired to lake on every run)
- [x] Route `products` dlt → MinIO archive + ClickHouse Bronze + lake/OTLP producers — backlog **0**
- [x] dbt silver / Gold + tests for Route products — [gold-products-cutover.md](gold-products-cutover.md)
- [x] Airflow endpoint DAG `route_clickhouse_products` + `nexus-elt` job image
- [x] Engine RBAC (ClickHouse loader/transformer/reader/admin) — [rbac.md](rbac.md)
- [x] Products Bronze → `bronze_{env}` + silver peer tables
- [x] Stack verify — `./scripts/start.sh verify` — backlog **1**
- [ ] SigNoz ready — live OTLP + dashboards + lake→SigNoz (`observability-ingest.sh signoz`) — backlog **2**
- [ ] OpenMetadata product dashboards / catalog — backlog **3**
- [ ] MinIO IAM — backlog **4**
- [ ] Local Terraform — backlog **5**
- [ ] Iceberg / Polaris / dbt-spark / Trino products path — backlog **6**
- [ ] Catalog follow-on dlt endpoints (`categories`, `brands`) — backlog **7**
- [ ] Facts, marts, semantic layer — backlog **8**
- [ ] Docs basic auth (Elementary / dbt / dlt HTML) — backlog **9**
- [ ] VPS + GitHub Actions — backlog **10**
- [ ] Supabase + Streamlit — backlog **11**
- [ ] LLM / RAG multi-agent — backlog **12**

---

## Immediate next step

**See [backlog.md](backlog.md).** Warehouse `products` + Airflow + lake are done (item 0). Stack verify is done (item 1). Next up: **2. SigNoz**, then OpenMetadata → MinIO IAM → local Terraform → Iceberg → …

```text
REST → dlt ✓ → MinIO archive + ClickHouse Bronze ✓ → dbt silver/gold ✓ → lake telemetry ✓
Airflow DAG ✓ (same scripts, DAG run_id = NEXUS_RUN_ID)
```

Guiding principle:

> **Build a simple, working ELT foundation first. Every pipeline run lands on the observability lake. Observability products are readers, not write dependencies.**

The objective is every capability as a reliable, independently selectable backend that an LLM agent can choose from a user’s data-engineering requirement.
