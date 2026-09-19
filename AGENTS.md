# AI-NexusFlow agent guide

## Project purpose

AI-NexusFlow is a multi-branch data-engineering execution platform and learning/portfolio project. It will later become an organization-aware ELT generator, where an LLM plus RAG selects and generates artifacts for **implemented, enabled** capabilities. It is not a collection of unrelated pipelines.

Architecture and engineering standards live in `docs/`. Read the relevant document before changing a capability:

- `docs/architecture.md` — platform design, branch responsibilities, and phases.
- `docs/roadmap.md` — current delivery sequence and status.
- `docs/setup.md` — local development and service topology.
- `docs/operations.md` — daily start/stop, all services, lakehouse restore.
- `docs/vault.md` — HashiCorp Vault secrets (KV paths, Agent injection, VPS ops). Read before changing secrets or bootstrap scripts.
- `docs/edge-proxy.md` — Caddy edge; local vs VPS modes; deploy checklist for Actions/Terraform. When Caddy exits or VPS ports look wrong, use the **Debug: Caddy exit / NEXUS_PUBLISH_BIND** section before inventing a new failure mode.
- `docs/ci-cd.md` — GitHub Actions + Terraform intent; production-shaped local; day-one deploy.
- `docs/rbac.md` — ClickHouse loader/transformer/reader/admin (accepted; implement with Bronze cutover). MinIO IAM held.
- `docs/bronze-silver-cutover.md` — implementation record for warehouse Bronze rename, RBAC, and silver peer tables (canonical rules in environments / dbt-modeling / dlt-dbt-clickhouse / rbac).
- `docs/dlt-dbt-clickhouse.md` and `docs/dlt-extraction.md` — warehouse ingestion rules.
- `docs/dlt-dbt-spark-iceberg.md` — lakehouse rules.
- `docs/dbt-modeling.md` — shared transformation and modeling rules.
- `docs/environments.md` and `docs/observability.md` — naming, environment, run, and logging rules.

## Current implementation priority

Phase 1, Milestone 1 — warehouse branch first. Route **`products`** dlt (archive + Bronze + observability producers) is the **reference endpoint pipeline**; document and copy its norms for the next scripts. Products silver / Gold and Airflow DAG `route_clickhouse_products` are in place. Still ahead: catalog follow-ons (`categories` / `brands`), then SigNoz / OpenMetadata look-and-feel.

```text
REST source → dlt → MinIO JSONL archive + ClickHouse Bronze → dbt staging / Gold + tests
              → observability data lake (MinIO nexus-telemetry-{env})
Airflow DAG → same dlt/dbt via nexus-elt job image (DAG run_id = NEXUS_RUN_ID)
```

Implement and verify `dlt_dbt_clickhouse` with full observability producers (lake writes on every run) before starting Spark/Iceberg, Terraform/CI, reader-tool dashboards, or LLM/RAG. Warehouse Bronze/RBAC/silver for products is implemented — see [docs/bronze-silver-cutover.md](docs/bronze-silver-cutover.md). Airflow smoke/source DAGs are part of Milestone 1. Do not fill future-phase folders with speculative implementations. MinIO IAM and lakehouse RBAC stay deferred.

## Capability boundaries

- `branches/dlt_dbt_clickhouse`: dlt → MinIO raw archive + ClickHouse → dbt-clickhouse. ClickHouse is the serving destination; MinIO is not its analytical lakehouse.
- `branches/dlt_dbt_spark_iceberg`: dlt → MinIO archive + Iceberg via Polaris → dbt-spark → Trino. It is independent from the ClickHouse capability.
- `config/branches.yaml` controls which capabilities may execute. A disabled branch must never be selected or run.
- Docker Compose profiles control available infrastructure. Keep them aligned manually with enabled branches.

## Local development

- Run Python, `uv`, dlt, and dbt on the host from the repository root; do not run `uv sync` in a bind-mounted Compose container.
- Docker Compose runs infrastructure: MinIO + OTel Collector always; ClickHouse via `clickhouse`; Polaris/Spark Thrift/Trino via `lakehouse`; Airflow on-demand via `airflow`; CloudBeaver via `cloudbeaver`; SigNoz / OpenMetadata via `signoz` / `openmetadata`.
- Use `.env` for local configuration; secrets on the VPS come from HashiCorp Vault via Agent (see `docs/vault.md`). Local WSL may use `NEXUS_SECRETS_BACKEND=env` until Vault is running. Never commit `.env`, `profiles.yml`, credentials, API keys, or tokens.
- Default environment is `NEXUS_ENV=dev`. `prd` is a Phase 2/Terraform naming contract, not a second local stack.
- dbt does not load `.env` itself; source it before dbt commands. Keep dbt `--target` equal to `NEXUS_ENV`.

## Ingestion rules

- **Reference implementation:** `branches/dlt_dbt_clickhouse/dlt/route/products.py`. Every new warehouse endpoint script must follow the same norms in [docs/dlt-extraction.md](docs/dlt-extraction.md) (Reference pipeline section). Do not invent a second style for `categories` / `brands` / other sources.
- dlt owns REST auth, pagination, retries, rate limits, incremental state, raw archival, and Bronze loads. dbt must not call APIs.
- Extract a source once, then write to both destinations (archive **first**, then Bronze); never scrape an API separately for archive and Bronze. Assert `LoadInfo` after each destination run.
- In the warehouse branch, archive immutable compressed JSONL to `nexus-dlt-dbt-clickhouse-{env}` and append Bronze rows to `bronze_{env}` as `raw_{source}__{endpoint}` (see [docs/environments.md](docs/environments.md), [docs/bronze-silver-cutover.md](docs/bronze-silver-cutover.md); legacy `raw_{source}_{env}` / `___` naming is obsolete).
- Use one endpoint pipeline per REST endpoint. Parameter variants are separate only if their payload contract (schema, grain, auth, or incremental behavior) differs.
- Keep dlt state for cursors and schema; do not introduce a custom watermark system.
- Every load receives a shared `NEXUS_RUN_ID` (`--run-id` > env > mint `local-{UTC}`). Stamp it on Bronze rows and pass the same ID to dbt as `var('run_id')`. Do not use a permanent default run ID.
- Archive objects and historical Bronze rows are immutable/append-only. Replay reads an archive prefix, loads with a new run ID, then runs dbt.
- Every dlt run publishes lake events via `publish_dlt_load` on success and failure; OTLP is best-effort and must not abort ingest.

## dbt and data-modeling rules

- dbt reads Bronze with `source()`, owns staging, intermediate, Gold, marts, and tests, and never owns extraction or archival.
- Model dependencies form a DAG, not a mandatory Bronze → staging → intermediate → Gold → mart ladder. Create only layers required by the data/consumer requirement.
- Staging folders split by REST source: `models/staging/{source}/`. Gold folders split by grain: `gold/dims`, `gold/facts`, `gold/events`.
- For ClickHouse, use shared layer databases `bronze_{env}`, `silver_{env}`, `intermediate_{env}`, `gold_{env}`, `marts_{env}`, `published_{env}`, `elementary_{env}` (env on DB only; tables like `raw_route__products`, `stg_route__products`). ClickHouse has databases, not schemas. See [docs/environments.md](docs/environments.md), [docs/bronze-silver-cutover.md](docs/bronze-silver-cutover.md).
- Gold is conformed and shared by default. Do not create a distinct `dim_*` merely because an endpoint or URL parameter differs; create one only when the requirement names a separate dimension.
- Use `dim_*`, `fct_*`, and `evt_*` according to declared grain. SCD2, facts, marts, and published tables are optional requirements, not default scaffolding.
- Keep Bronze append-only; model “current” or as-of logic downstream. Prefer natural or hashed keys over serial surrogate keys.
- Add dbt tests appropriate to type, keys, uniqueness, relationships, and accepted values. Do not add a separate data-quality platform for the first milestone.

## Orchestration and observability

- Airflow is **Phase 1** orchestration, not a transformation backend. Use **one DAG per source + target + endpoint** with layer tasks (`assert_branch_enabled` → bronze → silver → gold → observability). Never `dbt build` (always `run` then `test`).
- **Airflow runtime (locked):** Dockerized **Airflow 3.3** (`api-server` + `dag-processor` + LocalExecutor); dlt/dbt in ephemeral **`nexus-elt`** job containers (`docker run` on the Compose network). Cursor still uses host `uv`. Never install dlt/dbt into the Airflow image. One UI for all branches. Do not bind-mount `.venv`. See [docs/architecture.md](docs/architecture.md), [docker/elt/README.md](docker/elt/README.md).
- **Observability data lake:** MinIO `nexus-telemetry-{env}` is the system of record. Pipeline code uses `common/observability` only — never SigNoz, OpenMetadata, or Elementary directly.
- Airflow owns task scheduling, retries, and remote stdout (`nexus-airflow-logs-{env}`); dlt owns load telemetry in warehouse `_dlt_*` tables; dbt owns local `target/` plus artifact copy to the lake.
- Phase 1 requires full producers: lake summaries, OTLP when the collector is up, dbt artifact copy, Elementary HTML, Airflow remote logs. SigNoz and OpenMetadata are **readers** (product setup after the first Airflow E2E) with their own native DBs; ingest from the lake; do not replace their storage with MinIO. Pipeline code must not call those APIs.
- Airflow DAG `run_id` = `NEXUS_RUN_ID` when orchestrated; `local-{timestamp}` for manual runs until then.
- **`nexus_elt_exec` env quoting:** `docker run -e NEXUS_RUN_ID='{{ run_id }}'` (and DAG/task id) assumes Airflow ids have **no single quote**. Default / manual Airflow `run_id`s are fine. Do not introduce custom run ids with `'`; the remote `bash -lc` fragment is `shlex.quote`d, but those `-e` lines are not. See `orchestration/airflow/dags/nexus_elt_exec.py`.
- Do not build a custom logging service or use a ClickHouse table as the ops system of record.

## Future LLM/RAG behavior

- Build LLM/RAG only in **Phase 3**, after Phase 1 (capabilities, Airflow, observability producers) is runnable and Phase 2 (Terraform, CI, reader tools) is in place. Do not start Phase 3 before Phase 1.
- The LLM reasons over user requirements; RAG supplies organization-specific standards. Do not invent organization conventions or unsupported platform capabilities.
- Keep planner, ingestion, transformation, platform/branch, workflow, and validation responsibilities separate. Validation must reject disabled branches, unavailable runtimes, invalid schedules, and standards violations.

## Change discipline

- Preserve branch independence and match physical names, bucket names, folders, and environment rules in the docs.
- Prefer a small, runnable vertical slice over broad unverified scaffolding.
- Update the relevant docs and tests when a documented implementation contract changes.
- Before handing off a change, run the narrowest relevant verification (for example, `uv run dbt debug`, `dbt run`, `dbt test`, or focused tests) and report anything not verified.
