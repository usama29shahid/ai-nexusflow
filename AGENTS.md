# AI-NexusFlow agent guide

## Project purpose

AI-NexusFlow is a multi-branch data-engineering execution platform and learning/portfolio project. It will later become an organization-aware ELT generator, where an LLM plus RAG selects and generates artifacts for **implemented, enabled** capabilities. It is not a collection of unrelated pipelines.

Architecture and engineering standards live in `docs/`. Read the relevant document before changing a capability:

- `docs/architecture.md` — platform design, branch responsibilities, and phases.
- `docs/roadmap.md` — current delivery sequence and status.
- `docs/setup.md` — local development and service topology.
- `docs/operations.md` — daily start/stop, all services, lakehouse restore.
- `docs/vault.md` — HashiCorp Vault secrets (KV paths, Agent injection, VPS ops). Read before changing secrets or bootstrap scripts.
- `docs/dlt-dbt-clickhouse.md` and `docs/dlt-extraction.md` — warehouse ingestion rules.
- `docs/dlt-dbt-spark-iceberg.md` — lakehouse rules.
- `docs/dbt-modeling.md` — shared transformation and modeling rules.
- `docs/environments.md` and `docs/observability.md` — naming, environment, run, and logging rules.

## Current implementation priority

The repository is a documented skeleton. The immediate task is Phase 1, Milestone 1 only:

```text
REST source → dlt → MinIO JSONL archive + ClickHouse Bronze → dbt staging / Gold + tests
```

Implement and verify `dlt_dbt_clickhouse` before starting Spark/Iceberg, Databricks, Airflow, LLM/RAG, Terraform, AWS, or streaming work. Do not fill future-phase folders with speculative implementations.

## Capability boundaries

- `branches/dlt_dbt_clickhouse`: dlt → MinIO raw archive + ClickHouse → dbt-clickhouse. ClickHouse is the serving destination; MinIO is not its analytical lakehouse.
- `branches/dlt_dbt_spark_iceberg`: dlt → MinIO archive + Iceberg via Polaris → dbt-spark → Trino. It is independent from the ClickHouse capability.
- `branch_3_databricks`, `branch_4_emr`, and `branch_5_glue` are independent future backends, not children of either first branch.
- `config/branches.yaml` controls which capabilities may execute. A disabled branch must never be selected or run.
- Docker Compose profiles control available infrastructure. Keep them aligned manually with enabled branches.

## Local development

- Run Python, `uv`, dlt, and dbt on the host from the repository root; do not run `uv sync` in a bind-mounted Compose container.
- Docker Compose runs infrastructure: MinIO always; ClickHouse via `clickhouse`; Polaris/Spark Thrift/Trino via `lakehouse`; Airflow on-demand via `airflow`; CloudBeaver via `cloudbeaver`.
- Use `.env` for local configuration; secrets on the VPS come from HashiCorp Vault via Agent (see `docs/vault.md`). Local WSL may use `NEXUS_SECRETS_BACKEND=env` until Vault is running. Never commit `.env`, `profiles.yml`, credentials, API keys, or tokens.
- Default environment is `NEXUS_ENV=dev`. `prd` is a Phase 4/Terraform naming contract, not a second local stack.
- dbt does not load `.env` itself; source it before dbt commands. Keep dbt `--target` equal to `NEXUS_ENV`.

## Ingestion rules

- dlt owns REST auth, pagination, retries, rate limits, incremental state, raw archival, and Bronze loads. dbt must not call APIs.
- Extract a source once, then write to both destinations; never scrape an API separately for archive and Bronze.
- In the warehouse branch, archive immutable compressed JSONL to `nexus-dlt-dbt-clickhouse-{env}` and append Bronze rows to `raw_{source}_{env}`.
- Use one endpoint pipeline per REST endpoint. Parameter variants are separate only if their payload contract (schema, grain, auth, or incremental behavior) differs.
- Keep dlt state for cursors and schema; do not introduce a custom watermark system.
- Every load receives a new shared `NEXUS_RUN_ID`. Stamp it on Bronze rows and pass the same ID to dbt as `var('run_id')`. Do not use a permanent default run ID.
- Archive objects and historical Bronze rows are immutable/append-only. Replay reads an archive prefix, loads with a new run ID, then runs dbt.

## dbt and data-modeling rules

- dbt reads Bronze with `source()`, owns staging, intermediate, Gold, marts, and tests, and never owns extraction or archival.
- Model dependencies form a DAG, not a mandatory Bronze → staging → intermediate → Gold → mart ladder. Create only layers required by the data/consumer requirement.
- Staging folders split by REST source: `models/staging/{source}/`. Gold folders split by grain: `gold/dims`, `gold/facts`, `gold/events`.
- For ClickHouse, use per-source `raw_{source}_{env}` and `stg_{source}_{env}` databases; use shared `int_{env}`, `gold_{env}`, `marts_{env}`, and optional `pub_{env}` databases. ClickHouse has databases, not schemas.
- Gold is conformed and shared by default. Do not create a distinct `dim_*` merely because an endpoint or URL parameter differs; create one only when the requirement names a separate dimension.
- Use `dim_*`, `fct_*`, and `evt_*` according to declared grain. SCD2, facts, marts, and published tables are optional requirements, not default scaffolding.
- Keep Bronze append-only; model “current” or as-of logic downstream. Prefer natural or hashed keys over serial surrogate keys.
- Add dbt tests appropriate to type, keys, uniqueness, relationships, and accepted values. Do not add a separate data-quality platform for the first milestone.

## Orchestration and observability (future phases)

- Airflow is Phase 2 orchestration, not a transformation backend. Use one DAG per source, endpoint-level dlt tasks, then dbt selectors for downstream models.
- Airflow owns task scheduling, retries, and operational logs; dlt owns load telemetry; dbt owns run artifacts. Do not build a custom logging service or use a data table as the operational source of truth.
- Once Airflow exists, its DAG `run_id` replaces the local generator while preserving the same shared-run-ID contract.

## Future LLM/RAG behavior

- Build LLM/RAG only in Phase 3, after Branches 1–3 and Airflow are runnable.
- The LLM reasons over user requirements; RAG supplies organization-specific standards. Do not invent organization conventions or unsupported platform capabilities.
- Keep planner, ingestion, transformation, platform/branch, workflow, and validation responsibilities separate. Validation must reject disabled branches, unavailable runtimes, invalid schedules, and standards violations.

## Change discipline

- Preserve branch independence and match physical names, bucket names, folders, and environment rules in the docs.
- Prefer a small, runnable vertical slice over broad unverified scaffolding.
- Update the relevant docs and tests when a documented implementation contract changes.
- Before handing off a change, run the narrowest relevant verification (for example, `uv run dbt debug`, `dbt run`, `dbt test`, or focused tests) and report anything not verified.
