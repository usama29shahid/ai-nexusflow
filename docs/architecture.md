# Architecture

AI-NexusFlow is a **multi-branch data engineering execution platform**. The same ingestion requirement can be routed to the most appropriate implementation. It is one platform with two selectable backends, not a pile of unrelated pipelines.

The project is a hands-on DE learning and portfolio platform. It later becomes an **organization-aware, LLM-powered ELT generator**. The LLM is a **consumer of branch capabilities**. It is built in **Phase 3**, after Phase 1 (two capabilities, Airflow, and observability producers) is runnable and Phase 2 (Terraform, CI, reader tools) supports the ops story.

End state:

```text
User Request
     ↓
LLM Agent
     ↓
Understand source / target / scale / requirements
     ↓
Capability & Branch Router
     ↓
Select an enabled execution branch
     ↓
Airflow / branch execution
     ↓
Data ingestion + transformation
     ↓
Validation / data quality
     ↓
Result
```

Examples:

```text
"Ingest this REST API into ClickHouse"
        ↓
LLM selects dlt_dbt_clickhouse
        ↓
dlt → MinIO archive + ClickHouse Bronze → dbt (Silver / Gold / marts)
```

```text
"Ingest this REST API into Iceberg / Trino"
        ↓
LLM selects dlt_dbt_spark_iceberg
        ↓
dlt → MinIO archive + Iceberg Bronze (Polaris) → dbt-spark → Trino
```

Routing can depend on volume, distributed processing, existing infra, cost, performance, and organization rules. The agent must not select a **disabled** branch.

---

## ELT generator

A user should describe an ELT requirement in natural language, for example:

```text
Ingest this XYZ REST API into ClickHouse and store raw data
into schema RAW as the Bronze layer and output into TRANS as
the Silver layer. Use organization norms for transformation
and Bronze-layer preparation and schedule this pipeline daily
at 6 AM.
```

The system retrieves organization-specific rules, creates an ELT plan, selects an enabled branch, generates artifacts, validates them, and orchestrates execution.

```text
User Request
     ↓
Planner Agent
     ↓
RAG / Organization Knowledge
     ↓
ELT Plan / Specification
     ↓
Branch / Capability Selection
     ↓
Specialized Agents
     ↓
Generated ELT Artifacts
     ↓
Validation Agent
     ↓
Airflow
     ↓
Execution
     ↓
Data Quality / Result
```

The generator must **not invent organization conventions**. The user may give `RAW`, `TRANS`, and `daily at 6 AM`; RAG supplies naming, bronze/silver/gold, flattening, deduplication, incremental loading, shared vs domain models, tool selection, and Airflow standards.

Warehouse capability rules (DAG vs ladder, archive, dlt vs dbt, run ids): [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md), [dlt-extraction.md](dlt-extraction.md), [dbt-modeling.md](dbt-modeling.md), [observability.md](observability.md).

> **The LLM provides reasoning; RAG provides organization-specific rules and standards.**

> **The agent does not generate code from the prompt alone. It generates from the prompt plus retrieved organizational rules.**

---

## RAG as the organization standards layer

RAG is not a general chatbot knowledge base. It is the **policy / engineering standards** layer for the ELT generator.

```text
Naming conventions
├── Pipeline names
├── DAG names
├── Database/schema names
├── Table names
└── Column names

Data-layer rules
├── Bronze / Silver / Gold (DAG, not a ladder)
├── Staging stg_* / intermediate int_*
├── Conformed dims, facts, events
├── Domain marts (dbt-only)
├── Flattening
├── Deduplication
└── Incremental processing

Technology rules
├── DLT, dbt, Spark / Iceberg / Trino
└── Tool-selection rules

Platform rules
├── Runtime, infrastructure, environment

Orchestration rules
├── Airflow DAGs, schedule, retries, dependencies, alerting

Data quality rules
├── Tests, validation, schema checks, reconciliation
```

```text
Organization Documents → Chunking / Indexing → RAG Retrieval
        → Relevant Rules → Specialized Agent → Generated Artifact
```

---

## Multi-agent design

Use specialized agents rather than one agent that does everything. Names can change; responsibilities should stay separate.

```text
USER → PLANNER AGENT → RAG / Rules → ELT PLAN / SPECIFICATION
         │
         ├── Ingestion Agent      → DLT code
         ├── Transformation Agent → dbt / Spark artifacts
         ├── Branch/Platform Agent → capability selection
         └── Workflow Agent       → Airflow DAG
         │
         └── Validation Agent → PASS → Execute → Validate result
                              → FAIL → revise
```

| Agent | Role |
| --- | --- |
| **Planner** | Source, target, layers, transformations, schedule, scale, constraints, required capabilities. Does not generate every implementation detail. |
| **Ingestion** | REST pagination, auth, retries, incremental, DLT dual load (MinIO archive + Bronze). ClickHouse Bronze for **dlt_dbt_clickhouse**; Iceberg Bronze via Polaris for **dlt_dbt_spark_iceberg**. Separate dlt code per capability. |
| **Transformation** | **dlt_dbt_clickhouse**: dbt-clickhouse. **dlt_dbt_spark_iceberg**: dbt-spark, **Thrift default** for SQL models; PySpark only for complex `.py` models. |
| **Branch / Platform** | ClickHouse warehouse → **dlt_dbt_clickhouse**. Open Iceberg lakehouse → **dlt_dbt_spark_iceberg**. |
| **Validation** | Naming, layers, flattening, required tests, branch enabled, runtime available, schedule valid. Fail returns to planning/generation. |
| **Workflow** | Airflow DAG from schedule plus org rules. **dlt_dbt_clickhouse**: **one DAG per source**, tasks per endpoint, dbt selectors. Not one DAG per URL. |

The two branches are **capabilities** (execution backends), not fixed pipelines. The generator considers target, scale, compute/storage, cost, org rules, and **enabled** branches.

---

## Two independent capabilities

All backends start from the **same REST APIs**. Primary source: **Route API** (`route` — ecommerce catalog and later transactional entities). Future secondary sources (for example DataForSEO) keep isolated Bronze/staging and may feed shared Gold. Each capability owns **its own** dlt and dbt code. Source contract: [route-ingestion.md](route-ingestion.md).

```text
              Same REST APIs (route primary; others later)
                               │
              ┌────────────────┼────────────────┐
              │                                 │
              ▼                                 ▼
        dlt_dbt_clickhouse              dlt_dbt_spark_iceberg
           warehouse                         lakehouse
              │                                 │
              ▼                                 ▼
         ClickHouse                      MinIO + Polaris
         + archive                       Iceberg + Spark
              │                                 │
              ▼                                 ▼
             dbt                            dbt-spark
              │                                 │
              ▼                                 ▼
         ClickHouse                      Iceberg + Trino
```

| Capability | Focus | Compute | Primary storage / format | Final / serving |
| --- | --- | --- | --- | --- |
| **dlt_dbt_clickhouse** | Warehouse ELT | dlt + dbt | ClickHouse | **ClickHouse** |
| **dlt_dbt_spark_iceberg** | Open-source lakehouse | dbt-spark | MinIO + Iceberg (Polaris) | **Trino on Iceberg** |

**dlt_dbt_clickhouse** — warehouse ELT: dlt → MinIO **raw archive** **and** ClickHouse `raw_{source}_{env}` → dbt `stg_{source}_{env}` → shared `int_{env}` / `gold_{env}` / marts. ClickHouse is the analytical destination. MinIO is not this capability’s Gold. Env: [environments.md](environments.md). Details: [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md). Path: `branches/dlt_dbt_clickhouse/`.

**dlt_dbt_spark_iceberg** — open lakehouse: dlt → MinIO JSONL archive **and** Iceberg Bronze via **Apache Polaris** (`nexus_{env}.raw_{source}`) → dbt-spark (**Thrift** for `.sql`; PySpark only for complex `.py`) → Iceberg gold/marts → **Trino**. ClickHouse is not this capability’s destination. Details: [dlt-dbt-spark-iceberg.md](dlt-dbt-spark-iceberg.md). Path: `branches/dlt_dbt_spark_iceberg/`.

Each capability demonstrates a different pattern (warehouse vs open lakehouse). Do not force every capability to the same destination.

---

## Branch on/off

Branches are independent capabilities. They must not always run. A registry such as `config/branches.yaml` controls **execution**, not whether the branch exists.

```yaml
branches:
  dlt_dbt_clickhouse:
    enabled: true
  dlt_dbt_spark_iceberg:
    enabled: false   # enable when Milestone 2 starts
```

Only enabled capabilities participate. Combinations can change over time (for example flip lakehouse to `true` after M1 is verified). A disabled capability stays implemented. The LLM must treat enabled/disabled as the available set.

---

## Cross-cutting layers

**Airflow (Phase 1)** orchestrates enabled capabilities. It is not another processing backend. **dlt_dbt_clickhouse**: **one DAG per source**, endpoint dlt tasks, then dbt with selectors. Remote task logs in MinIO (`nexus-airflow-logs-{env}`). Pipeline telemetry goes to the observability data lake (`nexus-telemetry-{env}`). See [observability.md](observability.md).

```text
Airflow → dlt_dbt_clickhouse | dlt_dbt_spark_iceberg
```

**Observability producers (Phase 1)** — every run writes via `common/observability` to MinIO `nexus-telemetry-{env}` (summaries, artifacts, OTLP when the collector is up). Airflow remote logs stay in `nexus-airflow-logs-{env}`.

**Terraform, GitHub Actions, reader tools (Phase 2)** — env promotion (`dev`/`prd`), CI, and SigNoz / OpenMetadata / Elementary product setup so those tools ingest from the lake. Readers do not replace the lake write contract.

**LLM / RAG / Streamlit (Phase 3)** — agents that select and generate against enabled capabilities.

---

## Development vs production

**Development and VPS/EC2:** infrastructure in Docker; Python, uv, DLT, and dbt on the **host** (WSL locally, Ubuntu on Hostinger or EC2). Same `./scripts/setup.sh`. **Secrets on the VPS:** HashiCorp Vault (KV v2) + Vault Agent → env injection — see [vault.md](vault.md). Engine RBAC (ClickHouse / MinIO / Polaris) is **held** — see [rbac.md](rbac.md). See [setup.md](setup.md).

**Compose profiles** (one file at the repo root). Name profiles after **stacks**, not every container. MinIO has **no** profile so it always starts. Isolation between capabilities is buckets and catalogs on that MinIO, not a second Compose project.

| Profile | Starts | Capability |
| --- | --- | --- |
| *(none)* | MinIO | Shared object store |
| `clickhouse` | ClickHouse | `dlt_dbt_clickhouse` |
| `lakehouse` | Polaris, Spark Thrift, Trino | `dlt_dbt_spark_iceberg` |
| `airflow` | Airflow (on-demand) | Orchestration (Phase 1) |
| `signoz` | SigNoz | Pipeline trace reader (Phase 2 product setup) |
| `openmetadata` | OpenMetadata | Data catalog reader (Phase 2 product setup) |
| `vault` | HashiCorp Vault + Agent | Secrets — [vault.md](vault.md) |

Set `COMPOSE_PROFILES` in `.env` (`clickhouse`, `lakehouse`, `cloudbeaver`, `airflow`, or comma-separated). Airflow is optional; start with `docker compose --profile airflow up -d` when needed. That is which **containers** run. [config/branches.yaml](../config/branches.yaml) is which **pipelines** may execute. Keep them aligned by hand. Commands: [setup.md](setup.md).

**Production (later):** optional CI image for Python. Terraform in Phase 2. Not part of Phase 1.

---

## Dependency boundary

The root `pyproject.toml` / `uv.lock` currently include DLT, dbt-core, and dbt-clickhouse. That is the **host** environment.

> A package in the shared local env does not mean every branch needs it at runtime.

- **dlt_dbt_clickhouse**: DLT + dbt-clickhouse + ClickHouse
- **dlt_dbt_spark_iceberg**: DLT Iceberg dest + dbt-spark (host); Spark cluster, Polaris, Trino in Docker

dbt-clickhouse is required for **dlt_dbt_clickhouse** now. dbt-spark is added when Milestone 2 starts. Spark **jobs** do not run inside `.venv`. For the lakehouse capability, **Thrift is the dbt SQL client**; PySpark is only for complex dbt Python models (see [dlt-dbt-spark-iceberg.md](dlt-dbt-spark-iceberg.md)).

---

## Repository layout

This tree is the end-goal skeleton. Folders exist now; fill them when the phase has real code. Compose stays at the **repo root**. Python stays on the **host**. Agents are **one** package (not both `llm/` and `eltax_agent/`). `docs/` stays flat until there are many ADRs.

```text
ai-nexusflow/
├── README.md
├── docker-compose.yml
├── pyproject.toml
├── scripts/setup.sh
├── config/
│   ├── branches.yaml
│   ├── dev.yaml
│   └── prod.yaml
├── common/
├── ingestion/
│   ├── sources/
│   └── dlt/pipelines/
├── branches/
│   ├── dlt_dbt_clickhouse/
│   └── dlt_dbt_spark_iceberg/
├── orchestration/airflow/dags/
├── agents/
├── ui/
├── docker/clickhouse/init/
├── infrastructure/
│   └── terraform/environments/{dev,prod}/
├── tests/
└── docs/
```

| Area | Responsibility |
| --- | --- |
| `common/` | Config, schemas, logging, utilities |
| `ingestion/` | Optional shared source **contracts**; each capability still owns dlt code |
| `branches/` | Independent execution implementations |
| `branches/dlt_dbt_clickhouse/` | Warehouse ELT (dlt + dbt-clickhouse) |
| `branches/dlt_dbt_spark_iceberg/` | Lakehouse ELT (dlt + dbt-spark + Iceberg) |
| `orchestration/airflow/` | DAGs for enabled branches |
| `agents/` | Planner, router, generator, validator, executor (Phase 3) |
| `ui/` | Streamlit (Phase 3) |
| `docker/` | Init scripts; Compose file stays at root (profiles in that file) |
| `infrastructure/` | Terraform (Phase 2) |
| `config/` | Env and branch activation |
| `docs/` | Platform architecture, warehouse, lakehouse, dlt, dbt, observability, environments, roadmap, setup |
