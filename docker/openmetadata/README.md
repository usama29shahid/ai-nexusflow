# OpenMetadata (profile: openmetadata)

Central **data catalog / lineage / DQ / governance** hub (backlog items **3** + **3.1**). **Reader only** — pipeline code writes to the observability lake and ClickHouse; catalog ingest is operator-driven via `./scripts/observability-ingest.sh openmetadata`.

Elementary HTML, dbt docs, and OpenObserve remain deep-dive UIs; OM is where warehouse assets, dbt tests, and Airflow (dlt/dbt) pipelines are projected for a single catalog.

| | |
| --- | --- |
| UI | http://127.0.0.1:8585 |
| Login | `OPENMETADATA_ADMIN_EMAIL` / `OPENMETADATA_ADMIN_PASSWORD` (default `admin@open-metadata.org` / `admin`) |
| Postgres (host) | `127.0.0.1:5433` |
| Elasticsearch (host) | `127.0.0.1:9200` (9.3.0) |
| Images | `openmetadata/*:2.0.3` (`OPENMETADATA_VERSION`) |

Default stack is the catalog UI only (Postgres + Elasticsearch 9 + server). Typical local RAM is about **3–4 GB** (ES heap defaults to 1 GB). OpenMetadata’s **internal** Airflow (profile `openmetadata-ingestion`) stays optional and heavy — catalog jobs use a one-shot ingestion image instead.

## Upgrade from 1.8.x

Postgres and Elasticsearch volumes from OpenMetadata **1.8.x** are incompatible with **2.0.x**. Before the first 2.0 start, remove only the OpenMetadata volumes:

```bash
./scripts/start.sh stop-openmetadata
docker volume rm ai-nexusflow_openmetadata_postgres_data ai-nexusflow_es-data
# volume names may include a Compose project prefix — check: docker volume ls | grep -E 'openmetadata|es-data'
```

## Patch upgrade (e.g. 2.0.2 → 2.0.3)

Same major/minor line: bump `OPENMETADATA_VERSION` in `.env`, recreate the profile (migrate job runs on start). **Do not** wipe volumes for a patch.

```bash
# in .env
OPENMETADATA_VERSION=2.0.3

./scripts/start.sh stop-openmetadata
./scripts/start.sh openmetadata
# confirm: curl -s http://127.0.0.1:8585/api/v1/system/version
# then refresh catalog (manual or unpause observability_openmetadata_ingest)
./scripts/observability-ingest.sh openmetadata -- --force
```

## Start

```bash
./scripts/start.sh openmetadata
```

Catalog ingest (ClickHouse + dbt lineage/DQ + profiler + optional Airflow pipelines + deep-dive links):

```bash
./scripts/clickhouse-rbac-bootstrap.sh   # nexus_catalog (+ elementary grants)
./scripts/observability-ingest.sh openmetadata
./scripts/observability-ingest.sh openmetadata -- --force
```

Or schedule via Airflow (reader DAG, not chained to products):

```bash
./scripts/start.sh openmetadata
./scripts/start.sh airflow   # rebuilds nexus-elt (Docker CLI) + refreshes airflow_elt.env
# Unpause DAG: observability_openmetadata_ingest (daily)
# Manual re-ingest same lake run_id:
#   UI: Trigger → param force=true
#   CLI: airflow dags trigger observability_openmetadata_ingest --conf '{"force": true}'
```


CLI flags (manual ingest): `-- --profiler-only`, `-- --skip-profiler`, `-- --skip-airflow`, `-- --skip-links`.

What lands in OM:

| Signal | Source |
| --- | --- |
| Tables / schemas | ClickHouse `bronze_/silver_/gold_/elementary_{env}` (OM DB `default`) |
| Lineage | dbt `manifest` + `run_results` (bronze→silver→gold) |
| Data Quality dashboard | dbt **TestCaseResults** from lake `run_results.json` (**must** be from `dbt test`, not `dbt docs generate` — `observability-publish-run.sh` preserves the test artifact) |
| Table Profile | `metadata profile` |
| Pipelines | Airflow DAGs (`route_clickhouse_products`, …) when `airflow` profile is up |
| Elementary / dbt docs | CustomDashboard links under `nexus_observability_links` with OM 2.x `sourceUrl` → Caddy `elementary.` / `docs.` (auth gate = backlog **9**) |

The profiler embeds the ClickHouse connection in the workflow YAML because catalog ingest uses `storeServiceConnection: false`. Older lake manifests with `database: bronze_{env}` on sources are rewritten at ingest so lineage resolves.

**Lineage UI empty but ingest OK:** the Lineage tab can show an isolated node while `/api/v1/lineage/table/name/...` still returns edges (OM 2.0.3 UI glitch/cache). Hard-refresh the browser on `openmetadata.localhost.com` (Windows/Linux: `Ctrl+Shift+R`; macOS: `Cmd+Shift+R`), or clear site data for that origin, then reopen the table Lineage tab. Confirm edges via API before re-running ingest. Pipeline assets (e.g. `nexus_airflow_smoke`) do not show table lineage — check **Tables**, not **Pipelines**.

If published host ports are unreachable from the agent host (rare WSL isolation), set `OPENMETADATA_USE_COMPOSE_NETWORK=1` so login/MinIO use the Compose network via short-lived helpers. Normal local WSL with Docker Desktop does not need this.

Optional OM Airflow (UI-driven connectors only; not required for item 3/3.1):

```bash
docker compose --profile openmetadata-ingestion up -d
# UI: http://127.0.0.1:8089
```

Elasticsearch heap defaults to 1 GB (`OPENMETADATA_ES_JAVA_OPTS`). See [docs/observability.md](../../docs/observability.md), [docs/vault.md](../../docs/vault.md).
