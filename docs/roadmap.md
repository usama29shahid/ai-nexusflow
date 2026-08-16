# Roadmap

Build a **working ELT foundation first**. Add Spark, cloud, orchestration, and LLM only when the previous layer is runnable and has a clear purpose.

Each phase must be **runnable**, not a folder of stubs. Later agents generate and **select** these branches; they should not invent a platform that was never built.

```text
Phase 1  Branch 1 → Branch 2 → Branch 3   (each must run end-to-end)
Phase 2  Airflow
Phase 3  LLM: multi-agent + RAG + Streamlit (live app)
Phase 4  Terraform (dev / prod) + infra
Phase 5  AWS EMR + AWS Glue
Phase 6  Kafka + Spark Streaming
```

This shows **senior DE** (warehouse, open lakehouse, Databricks, Airflow, later AWS and streaming) **and** **LLM/AI** (agents that consume those capabilities).

The LLM layer is Phase 3 — after Branches 1–3 and Airflow exist — not after all five cloud branches, and not before any pipeline runs.

---

## Phase 1 — Branches 1, 2, and 3 up and running

Same source problem, three independent backends.

**Do not start Branch 2 until Branch 1 is verified. Do not start Branch 3 until Branch 2 is verified.**

Python, uv, DLT, and dbt stay on the **host**. ClickHouse and MinIO are already in Docker Compose. Spark for Branch 2 is added as Docker infra when Milestone 2 starts.

### Milestone 1 — Branch 1 (first pipeline)

```text
Source → DLT → ClickHouse (RAW / bronze) → dbt → ClickHouse (TRANS / silver)
```

- One stable REST (or similar) source
- DLT ClickHouse destination
- dbt models and tests in `branches/branch_1_clickhouse/dbt`
- Verify row counts and tests

MinIO is **not** the Branch 1 destination (that is Branch 2).

### Milestone 2 — Branch 2

```text
Source → DLT → MinIO (Parquet) → Iceberg → PySpark → Iceberg gold
```

Open-source lakehouse without Databricks. Gold lives in Iceberg on MinIO.

### Milestone 3 — Branch 3

```text
Source → DLT → Databricks Spark → Delta Lake → Unity Catalog gold
```

Independent of Branch 1 and 2. Aligns with Databricks coursework.

**Phase 1 done when:** all three pipelines run and you can show data in ClickHouse, Iceberg/MinIO, and Databricks Delta.

---

## Phase 2 — Airflow

- DAGs that trigger enabled Branch 1 / 2 / 3
- Schedule, retries, clear task boundaries
- On/off in config: Airflow only runs **enabled** branches
- Add Airflow in Docker here (not in Phase 1)

This is the execution surface Phase 3 agents will target.

---

## Phase 3 — LLM, multi-agent, RAG, Streamlit

```text
Streamlit → Planner → RAG (org standards) → ELT spec
  → Ingestion / Transform / Branch / Workflow agents
  → Validation → Airflow → result
```

- LangGraph specialized agents (not one mega-prompt)
- RAG: naming, bronze/silver, DLT/dbt/Spark/Databricks, Airflow rules
- Streamlit: request, retrieved rules, spec, generated artifacts, run status
- Host on AWS or a Hostinger **VPS** (not shared PHP hosting)

Details: [architecture.md](architecture.md).

---

## Phase 4 — Terraform and infra

Compose already exists for local services. This phase is **env promotion**.

- Terraform **dev** and **prod**
- Repeatable ClickHouse / MinIO / Airflow (and later AWS) wiring
- Secrets and networking; no keys in git

---

## Phase 5 — AWS EMR and Glue (Branches 4 and 5)

- Branch 4: DLT → S3 → EMR/PySpark → Iceberg → S3 (optional Redshift)
- Branch 5: DLT → S3 → Glue → Iceberg → S3 (optional Redshift)

Same on/off router. Do not leave clusters on 24/7 for a demo; run jobs on demand.

---

## Phase 6 — Streaming

Kafka + Spark Structured Streaming, after batch (and AWS batch paths) are stable.

---

## Current status

### Completed

- [x] GitHub repository `ai-nexusflow`
- [x] WSL2 + Docker Desktop WSL integration
- [x] Docker Compose: ClickHouse + MinIO
- [x] Python project with uv (`pyproject.toml`, `uv.lock`)
- [x] DLT, dbt-core, dbt-clickhouse
- [x] dbt project `nexus_dbt` initialized (`branches/branch_1_clickhouse/dbt`)
- [x] End-goal folder skeleton and `scripts/setup.sh`
- [x] Python / DLT / dbt versions verified
- [x] `.venv` permission issue identified and resolved
- [x] Development architecture documented (`docs/`)

### Current versions

```text
Python          3.12.12
DLT             1.30.0
dbt-core        1.11.13
dbt-clickhouse  1.10.2
```

### Not implemented yet

- [ ] DLT ingestion pipeline (Branch 1)
- [ ] ClickHouse bronze / dbt silver + tests
- [ ] MinIO / Parquet / Iceberg / PySpark (Branch 2)
- [ ] Databricks / Delta / Unity Catalog (Branch 3)
- [ ] Airflow
- [ ] LLM ELT generator, RAG, Streamlit
- [ ] Terraform dev/prod
- [ ] AWS EMR / Glue
- [ ] Kafka / Spark Streaming

---

## Immediate next step

**Phase 1 Milestone 1:** implement and verify Branch 1 (DLT → ClickHouse → dbt). No Spark, Databricks, Airflow, or LLM in that slice.

Guiding principle:

> **Build a simple, working ELT foundation first. Add advanced technologies only when the foundation is stable and the new technology has a clear purpose.**

The objective is every branch as a reliable, independently selectable capability that an LLM agent can choose from a user’s data-engineering requirement.
