# dlt_dbt_clickhouse — warehouse ELT

```text
Source → dlt → MinIO archive + ClickHouse bronze_{env}.raw_{source}__{endpoint}
       → dbt silver_{env}.stg_* → gold_{env} / marts_{env} (later)
```

Standards: [docs/dlt-dbt-clickhouse.md](../../docs/dlt-dbt-clickhouse.md) (includes Route `products` example), [docs/route-ingestion.md](../../docs/route-ingestion.md), [docs/environments.md](../../docs/environments.md). Env: `NEXUS_ENV` (default `dev`).

- `dlt/{source}/` — extract pipelines
- `models/` — dbt (`nexus_clickhouse`; profile matches Compose stack `clickhouse`)
- `tests/` — `dlt/{source}/unit|regression` (Python) + `dbt/` mirroring models (see [tests/README.md](tests/README.md))

dbt does **not** load the repo `.env`. Source it first, then debug:

```bash
cd ~/projects/ai-nexusflow
set -a && source .env && set +a
uv run dbt debug --project-dir branches/dlt_dbt_clickhouse
```

Or use a project-local profile (gitignored copy of `profiles.example.yml`). Profile `schema` is `silver_dev` / `silver_prd` per target (not `NEXUS_ENV`). Re-copy or edit `profiles.yml` when the example changes:

```bash
cp branches/dlt_dbt_clickhouse/profiles.example.yml branches/dlt_dbt_clickhouse/profiles.yml
set -a && source .env && source scripts/load-secrets.sh && set +a
uv run dbt debug --project-dir branches/dlt_dbt_clickhouse --profiles-dir branches/dlt_dbt_clickhouse --target "$NEXUS_ENV"
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
