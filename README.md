# AI-NexusFlow

Multi-branch data engineering platform that will later become an **organization-aware ELT generator** (LLM + RAG + Airflow).

The same ingestion requirement can be routed to different backends. It is one platform with two selectable backends, not a pile of unrelated pipelines. The LLM is a **consumer of capabilities** you actually run — it does not invent a stack that was never built.

```text
User request → LLM + RAG (org rules) → select enabled branch → Airflow → ELT → validate
```

| Capability | Pattern | Primary output |
| --- | --- | --- |
| **dlt_dbt_clickhouse** | dlt → ClickHouse → dbt | ClickHouse |
| **dlt_dbt_spark_iceberg** | dlt → Iceberg (Polaris) → dbt-spark → Trino | Iceberg on MinIO (AIStor Free) |

Platform design: [docs/architecture.md](docs/architecture.md). Warehouse: [docs/dlt-dbt-clickhouse.md](docs/dlt-dbt-clickhouse.md). Lakehouse: [docs/dlt-dbt-spark-iceberg.md](docs/dlt-dbt-spark-iceberg.md).

---

## Current delivery order

**Source of truth:** [docs/backlog.md](docs/backlog.md) (one item at a time). Historical phases: [docs/roadmap.md](docs/roadmap.md).

Warehouse Route `products` + Airflow + lake producers are **done**. Next: stack verify → SigNoz (OTLP + lake ingest) → OpenMetadata → MinIO IAM → local Terraform → Iceberg parity → remaining endpoints → facts/marts/semantic layer → docs auth → VPS/Actions → Streamlit/Supabase → RAG later.

## Portfolio labels (not build order)

Prefer [docs/backlog.md](docs/backlog.md) for what to build next. Rough resume story:

| Label | Themes (mapped to backlog) |
| --- | --- |
| **Capabilities** | Warehouse + lakehouse + Airflow + lake producers (items **0**, **6**) |
| **Platform ops** | Readers **2–3**, MinIO IAM **4**, local TF **5**, docs auth **9**, VPS/Actions **10** |
| **App / AI** | Supabase/Streamlit **11**, RAG **12** (after semantic layer **8**) |

---

## Current status

Route `products` warehouse ELT (dlt archive + ClickHouse Bronze/silver/Gold + Airflow DAG + lake producers) is live. Full ordered backlog: [docs/backlog.md](docs/backlog.md).

- Host uv (Python 3.12, DLT, dbt-clickhouse) — not inside Docker
- Docker Compose: MinIO AIStor Free always (license `.nexusflow/minio.license`); `COMPOSE_PROFILES=clickhouse,lakehouse` (ClickHouse + Polaris + Spark Thrift + Trino)
- dbt project: `branches/dlt_dbt_clickhouse`
- Lakehouse skeleton: `branches/dlt_dbt_spark_iceberg` (disabled until backlog item **6**)
- Branch switches: `config/branches.yaml`

**Next:** [docs/backlog.md](docs/backlog.md) item **1** (stack verify), then SigNoz (OTLP + lake ingest) → OpenMetadata → …

---

## Quick start

Same on **WSL**, **Hostinger VPS**, and **AWS EC2**. Copy `.env`, then bootstrap. Details: [docs/setup.md](docs/setup.md).

```bash
cd ~/projects/ai-nexusflow
cp .env.example .env          # or paste your existing .env
mkdir -p .nexusflow
cp /path/to/aistor-license .nexusflow/minio.license   # gitignored
chmod +x scripts/setup.sh
./scripts/setup.sh
```

That is `docker compose up -d` (profiles from `.env`) plus `uv sync` on the host. Python/DLT/dbt never run inside Compose. The AIStor license must exist as a file before `setup.sh` — [docs/setup.md](docs/setup.md), [docker/minio/README.md](docker/minio/README.md).

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
│   └── dlt_dbt_spark_iceberg/
├── orchestration/airflow/
├── agents/
├── ui/
├── docker/                     # init scripts; compose stays at root
├── infrastructure/             # Terraform (local backlog 5; VPS 10)
├── tests/
└── docs/
```

Empty capability folders have short READMEs. Fill them when that backlog item has real code.

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
- [Observability](docs/observability.md) — observability data lake, dlt/dbt emit contract, swappable readers (SigNoz, OpenMetadata, Elementary)
- [Backlog](docs/backlog.md) — delivery order (source of truth)
- [Roadmap](docs/roadmap.md) — portfolio context + status checklist
- [Setup](docs/setup.md) — WSL / VPS / EC2, Docker, uv, troubleshooting
