# dlt_dbt_clickhouse — warehouse ELT

```text
Source → DLT → MinIO archive + ClickHouse raw_{source}_dev → dbt stg_{source}_dev → gold_dev
```

Standards: [docs/dlt-dbt-clickhouse.md](../../docs/dlt-dbt-clickhouse.md) (includes GitHub `pipe_one` example), [docs/environments.md](../../docs/environments.md). Env: `NEXUS_ENV` (default `dev`).

- `dlt/{source}/` — extract pipelines
- `models/` — dbt (`nexus_dbt`)

From the repo root (uses `~/.dbt/profiles.yml`):

```bash
uv run dbt debug --project-dir branches/dlt_dbt_clickhouse
```
