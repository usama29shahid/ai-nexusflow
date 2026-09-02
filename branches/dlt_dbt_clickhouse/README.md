# dlt_dbt_clickhouse — warehouse ELT

```text
Source → DLT → MinIO archive + ClickHouse raw_{source}_dev → dbt stg_{source}_dev → gold_dev
```

Standards: [docs/dlt-dbt-clickhouse.md](../../docs/dlt-dbt-clickhouse.md) (includes Route `products` example), [docs/route-ingestion.md](../../docs/route-ingestion.md), [docs/environments.md](../../docs/environments.md). Env: `NEXUS_ENV` (default `dev`).

- `dlt/{source}/` — extract pipelines
- `models/` — dbt (`nexus_clickhouse`; profile matches Compose stack `clickhouse`)

dbt does **not** load the repo `.env`. Source it first, then debug:

```bash
cd ~/projects/ai-nexusflow
set -a && source .env && set +a
uv run dbt debug --project-dir branches/dlt_dbt_clickhouse
```

Or use a project-local profile (gitignored copy of `profiles.example.yml`):

```bash
cp branches/dlt_dbt_clickhouse/profiles.example.yml branches/dlt_dbt_clickhouse/profiles.yml
set -a && source .env && set +a
uv run dbt debug --project-dir branches/dlt_dbt_clickhouse --profiles-dir branches/dlt_dbt_clickhouse
```

Smoke staging (after `uv run python tests/integration/dlt_clickhouse_smoke.py`):

```bash
export NEXUS_ENV="${NEXUS_ENV:-dev}"
export NEXUS_RUN_ID="${NEXUS_RUN_ID:-local}"
uv run dbt run --project-dir branches/dlt_dbt_clickhouse \
  --profiles-dir branches/dlt_dbt_clickhouse --target "$NEXUS_ENV" \
  --select stg_dlt_smoke_smoke --vars "{\"run_id\": \"$NEXUS_RUN_ID\"}"
uv run dbt test --project-dir branches/dlt_dbt_clickhouse \
  --profiles-dir branches/dlt_dbt_clickhouse --target "$NEXUS_ENV" \
  --select stg_dlt_smoke_smoke source:dlt_smoke_raw
```
