# AI-NexusFlow

Multi-branch data engineering platform that will later become an **organization-aware ELT generator** (LLM + RAG + Airflow).

The same ingestion requirement can be routed to different backends. It is not five unrelated pipelines. The LLM is a **consumer of capabilities** you actually run — it does not invent a stack that was never built.

```text
User request → LLM + RAG (org rules) → select enabled branch → Airflow → ELT → validate
```

| Capability | Pattern | Primary output |
| --- | --- | --- |
| **dlt_dbt_clickhouse** | dlt → ClickHouse → dbt | ClickHouse |
| **dlt_dbt_spark_iceberg** | dlt → Iceberg (Polaris) → dbt-spark → Trino | Iceberg on MinIO |
| 3 | DLT → Databricks → Delta → Unity Catalog | Delta |
| 4 | DLT → S3 → EMR → Iceberg | S3 (+ optional Redshift) |
| 5 | DLT → S3 → Glue → Iceberg | S3 (+ optional Redshift) |

Platform design: [docs/architecture.md](docs/architecture.md). Warehouse: [docs/dlt-dbt-clickhouse.md](docs/dlt-dbt-clickhouse.md). Lakehouse: [docs/dlt-dbt-spark-iceberg.md](docs/dlt-dbt-spark-iceberg.md).

---

## Phases

| Phase | What ships |
| --- | --- |
| **1** | Branches **1 → 2 → 3**, each up and running (in that order) |
| **2** | Airflow over enabled branches |
| **3** | Multi-agent LangGraph, RAG, Streamlit (live app) |
| **4** | Terraform dev/prod and infra |
| **5** | AWS EMR and Glue (Branches 4 and 5) |
| **6** | Kafka + Spark Structured Streaming |

Details and checklists: [docs/roadmap.md](docs/roadmap.md).

---

## Current status

**Environment and repo skeleton are ready.** Pipelines are not.

- Host uv (Python 3.12, DLT, dbt-clickhouse) — not inside Docker
- Docker Compose: MinIO always; `COMPOSE_PROFILES=clickhouse,lakehouse` (ClickHouse + Polaris + Spark Thrift + Trino)
- dbt project: `branches/dlt_dbt_clickhouse`
- Lakehouse skeleton: `branches/dlt_dbt_spark_iceberg` (disabled until M2)
- Branch switches: `config/branches.yaml`

**Next:** Phase 1 Milestone 1 — first **dlt_dbt_clickhouse** pipeline.

---

## Quick start

Same on **WSL**, **Hostinger VPS**, and **AWS EC2**. Copy `.env`, then bootstrap. Details: [docs/setup.md](docs/setup.md).

```bash
cd ~/projects/ai-nexusflow
cp .env.example .env          # or paste your existing .env
chmod +x scripts/setup.sh
./scripts/setup.sh
```

That is `docker compose up -d` (profiles from `.env`) plus `uv sync` on the host. Python/DLT/dbt never run inside Compose.

```bash
curl http://localhost:8123/ping
uv run python --version
uv run dlt --version
uv run dbt --version
```

---

## Repository

```text
ai-nexusflow/
├── README.md
├── docker-compose.yml          # infra only; profiles for optional stacks
├── pyproject.toml              # host uv
├── scripts/setup.sh
├── config/branches.yaml
├── common/
├── ingestion/                  # optional shared contracts; dlt lives per branch
├── branches/
│   ├── dlt_dbt_clickhouse/
│   ├── dlt_dbt_spark_iceberg/
│   ├── branch_3_databricks/
│   ├── branch_4_emr/
│   └── branch_5_glue/
├── orchestration/airflow/
├── agents/
├── ui/
├── docker/                     # init scripts; compose stays at root
├── infrastructure/             # Terraform, AWS, Databricks
├── tests/
└── docs/
```

Empty capability folders have short READMEs. Fill them when that phase has real code.

---

## Docs

- [Architecture](docs/architecture.md) — branches, RAG, agents, on/off router
- [Environments](docs/environments.md) — `NEXUS_ENV` (`dev` default); job vs table vs bucket; `prd` later
- [Route ingestion](docs/route-ingestion.md) — primary REST source (ecommerce catalog-first)
- [dlt_dbt_clickhouse](docs/dlt-dbt-clickhouse.md) — archive, Bronze, Gold, run ids
- [dlt_dbt_spark_iceberg](docs/dlt-dbt-spark-iceberg.md) — Polaris, Iceberg, dbt-spark, Trino
- [dlt extraction](docs/dlt-extraction.md) — REST auth, pagination, retries, dual load
- [dbt modeling](docs/dbt-modeling.md) — medallion + dimensional DAG
- [Enhanced modeling strategy](docs/enhanced-modeling-strategy.md) — proposal backlog (SCD / soft delete / keys)
- [Observability](docs/observability.md) — observability data lake, Airflow Phase 1, dlt/dbt emit contract, swappable readers (SigNoz, OpenMetadata, Elementary)
- [Roadmap](docs/roadmap.md) — phases, status, next milestone
- [Setup](docs/setup.md) — WSL / VPS / EC2, Docker, uv, troubleshooting
