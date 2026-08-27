# Architecture

AI-NexusFlow is a **multi-branch data engineering execution platform**. The same ingestion requirement can be routed to the most appropriate implementation. It is not five unrelated pipelines.

The project is a hands-on DE learning and portfolio platform. It later becomes an **organization-aware, LLM-powered ELT generator**. The LLM is a **consumer of branch capabilities**. It is built in Phase 3, after Branches 1–3 run and Airflow can orchestrate them. Branches 4–5 (EMR, Glue) follow Terraform.

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

```text
"Ingest this REST API into Redshift"
        ↓
LLM gathers more context
        ↓
   Branch 4 (EMR)  or  Branch 5 (Glue)
        ↓
     Redshift
```

Routing can depend on volume, distributed processing, serverless vs cluster, existing infra, cost, performance, and organization rules. The agent must not select a **disabled** branch.

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

The generator must **not invent organization conventions**. The user may give `RAW`, `TRANS`, and `daily at 6 AM`; RAG supplies naming, bronze/silver/gold, flattening, deduplication, incremental loading, shared vs domain models, tool selection, serverless rules, and Airflow standards.

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
├── DLT, dbt, Spark, Databricks, EMR, Glue
└── Tool-selection rules

Platform rules
├── Serverless, runtime, infrastructure, environment

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
| **Transformation** | **dlt_dbt_clickhouse**: dbt-clickhouse. **dlt_dbt_spark_iceberg**: dbt-spark, **Thrift default** for SQL models; PySpark only for complex `.py` models. Later branches: EMR/Glue PySpark, Databricks. |
| **Branch / Platform** | ClickHouse warehouse → **dlt_dbt_clickhouse**. Open Iceberg lakehouse → **dlt_dbt_spark_iceberg**. Redshift + Spark/serverless/scale → Branch 4 or 5. |
| **Validation** | Naming, layers, flattening, required tests, branch enabled, runtime available, schedule valid. Fail returns to planning/generation. |
| **Workflow** | Airflow DAG from schedule plus org rules. **dlt_dbt_clickhouse**: **one DAG per source**, tasks per endpoint, dbt selectors. Not one DAG per URL. |

The five branches are **capabilities** (execution backends), not fixed pipelines. The generator considers target, scale, compute/storage, open-source vs managed vs serverless, cost, org rules, and **enabled** branches.

---

## Five independent branches

All backends start from the **same REST APIs** (github, dataforseo, pokeapi first). Each capability owns **its own** dlt and dbt code. Branch 3, 4, and 5 are **not** children of dlt_dbt_clickhouse or dlt_dbt_spark_iceberg.

```text
                         Same REST APIs (github, dataforseo, pokeapi)
                                           │
        ┌──────────────┬───────────────────┼────────────┬──────────────┐
        │              │                   │            │              │
        ▼              ▼                   ▼            ▼              ▼
  dlt_dbt_CH    dlt_dbt_spark_iceberg   BRANCH 3    BRANCH 4      BRANCH 5
  warehouse     lakehouse               Databricks  AWS EMR       AWS Glue
        │              │                   │            │              │
        ▼              ▼                   ▼            ▼              ▼
   ClickHouse     MinIO + Polaris      Databricks      S3             S3
   + archive      Iceberg + Spark          │            │              │
        │              │                   ▼            ▼              ▼
        ▼              ▼               Spark/Delta   EMR/Spark     Glue/Spark
       dbt         dbt-spark               │            │              │
        │              │                   ▼            ▼              ▼
        ▼              ▼               Unity/Delta  S3/Iceberg    S3/Iceberg
   ClickHouse      Iceberg + Trino                      │              │
                                                        ▼              ▼
                                                     Redshift       Redshift
                                                     (optional)     (optional)
```

| Capability | Focus | Compute | Primary storage / format | Final / serving |
| --- | --- | --- | --- | --- |
| **dlt_dbt_clickhouse** | Warehouse ELT | dlt + dbt | ClickHouse | **ClickHouse** |
| **dlt_dbt_spark_iceberg** | Open-source lakehouse | dbt-spark | MinIO + Iceberg (Polaris) | **Trino on Iceberg** |
| **3** | Databricks lakehouse | Databricks + Spark | Delta + Unity Catalog | **Delta / Databricks** |
| **4** | AWS managed Spark | EMR + PySpark | S3 + Iceberg / Parquet | **S3 + optional Redshift** |
| **5** | AWS serverless ETL | Glue + Spark | S3 + Iceberg / Parquet | **S3 + optional Redshift** |

**dlt_dbt_clickhouse** — warehouse ELT: dlt → MinIO **raw archive** **and** ClickHouse `raw_{source}_{env}` → dbt `stg_{source}_{env}` → shared `int_{env}` / `gold_{env}` / marts. ClickHouse is the analytical destination. MinIO is not this capability’s Gold. Env: [environments.md](environments.md). Details: [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md). Path: `branches/dlt_dbt_clickhouse/`.

**dlt_dbt_spark_iceberg** — open lakehouse: dlt → MinIO JSONL archive **and** Iceberg Bronze via **Apache Polaris** (`nexus_{env}.raw_{source}`) → dbt-spark (**Thrift** for `.sql`; PySpark only for complex `.py`) → Iceberg gold/marts → **Trino**. ClickHouse is not this capability’s destination. Details: [dlt-dbt-spark-iceberg.md](dlt-dbt-spark-iceberg.md). Path: `branches/dlt_dbt_spark_iceberg/`.

**Branch 3** — Databricks: DLT → Spark → Delta → Unity Catalog gold. Compute = Databricks, storage = Delta, catalog = Unity Catalog. PostgreSQL/ClickHouse are not primary destinations.

**Branch 4** — EMR: DLT → S3 → EMR/PySpark → Iceberg/Parquet on S3 → optional Redshift.

**Branch 5** — Glue: DLT → S3 → Glue Spark → Iceberg/Parquet on S3 → optional Redshift. Serverless is a **compute characteristic**, not a sixth branch. Databricks serverless can be evaluated later.

Each branch demonstrates a different pattern (warehouse vs open lakehouse vs Databricks vs EMR vs Glue). Do not force every branch to the same destination.

---

## Branch on/off

Branches are independent capabilities. They must not always run. A registry such as `config/branches.yaml` controls **execution**, not whether the branch exists.

```yaml
branches:
  dlt_dbt_clickhouse:
    enabled: true
  dlt_dbt_spark_iceberg:
    enabled: false
  branch_3_databricks:
    enabled: false
  branch_4_emr:
    enabled: false
  branch_5_glue:
    enabled: false
```

Only enabled capabilities participate. Combinations can change over time (for example dlt_dbt_clickhouse + dlt_dbt_spark_iceberg). A disabled capability stays implemented. The LLM must treat enabled/disabled as the available set.

---

## Cross-cutting layers

**Airflow (Phase 2)** orchestrates enabled capabilities. It is not another processing backend. **dlt_dbt_clickhouse**: **one DAG per source**, endpoint dlt tasks, then dbt with selectors. Remote task logs in MinIO (`nexus-airflow-logs-{env}`). See [observability.md](observability.md).

```text
Airflow → dlt_dbt_clickhouse | dlt_dbt_spark_iceberg | Branch 3/4/5 (cloud jobs)
```

**Streaming (Phase 6)** — Kafka → Spark Structured Streaming → Iceberg / Delta / ClickHouse. Add only after batch is stable.

**Terraform (Phase 4)** — dev and prod environments; not the first Docker Compose setup.

---

## Development vs production

**Development and VPS/EC2:** infrastructure in Docker; Python, uv, DLT, and dbt on the **host** (WSL locally, Ubuntu on Hostinger or EC2). Same `./scripts/setup.sh`. See [setup.md](setup.md).

**Compose profiles** (one file at the repo root). Name profiles after **stacks**, not every container. MinIO has **no** profile so it always starts. Isolation between capabilities is buckets and catalogs on that MinIO, not a second Compose project.

| Profile | Starts | Capability |
| --- | --- | --- |
| *(none)* | MinIO | Shared object store |
| `clickhouse` | ClickHouse | `dlt_dbt_clickhouse` |
| `lakehouse` | Polaris, Spark Thrift, Trino | `dlt_dbt_spark_iceberg` |
| `airflow` | Airflow (on-demand) | Orchestration |

Set `COMPOSE_PROFILES` in `.env` (`clickhouse`, `lakehouse`, `cloudbeaver`, `airflow`, or comma-separated). Airflow is optional; start with `docker compose --profile airflow up -d` when needed. That is which **containers** run. [config/branches.yaml](../config/branches.yaml) is which **pipelines** may execute. Keep them aligned by hand. Commands: [setup.md](setup.md).

**Production (later):** optional CI image for Python. Terraform in Phase 4. Not part of Phase 1.

---

## Dependency boundary

The root `pyproject.toml` / `uv.lock` currently include DLT, dbt-core, and dbt-clickhouse. That is the **host** environment.

> A package in the shared local env does not mean every branch needs it at runtime.

- **dlt_dbt_clickhouse**: DLT + dbt-clickhouse + ClickHouse
- **dlt_dbt_spark_iceberg**: DLT Iceberg dest + dbt-spark (host); Spark cluster, Polaris, Trino in Docker
- Branch 3: Databricks Spark + Delta
- Branch 4: EMR Spark + libraries
- Branch 5: Glue Spark + libraries

dbt-clickhouse is required for **dlt_dbt_clickhouse** now. dbt-spark is added when Milestone 2 starts. Databricks, EMR, and Glue must **not** use the host `.venv` as their runtime. Spark **jobs** do not run inside `.venv`. For this capability, **Thrift is the dbt SQL client**; PySpark is only for complex dbt Python models (see [dlt-dbt-spark-iceberg.md](dlt-dbt-spark-iceberg.md)).

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
│   ├── dlt_dbt_spark_iceberg/
│   ├── branch_3_databricks/
│   ├── branch_4_emr/
│   └── branch_5_glue/
├── orchestration/airflow/dags/
├── agents/
├── ui/
├── docker/clickhouse/init/
├── infrastructure/
│   ├── terraform/environments/{dev,prod}/
│   ├── aws/{emr,glue,s3,redshift}/
│   └── databricks/
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
| `agents/` | Planner, router, generator, validator, executor |
| `ui/` | Streamlit (Phase 3) |
| `docker/` | Init scripts; Compose file stays at root (profiles in that file) |
| `infrastructure/` | Terraform, AWS, Databricks |
| `config/` | Env and branch activation |
| `docs/` | Platform architecture, warehouse, lakehouse, dlt, dbt, observability, environments, roadmap, setup |
