# dlt_dbt_clickhouse — warehouse ELT

```text
Source → DLT → MinIO nexus-dlt-dbt-clickhouse-dev + ClickHouse raw_dev → dbt target dev → Gold / marts
```

Standards: [docs/dlt-dbt-clickhouse.md](../../docs/dlt-dbt-clickhouse.md), [docs/environments.md](../../docs/environments.md).

This directory **is** the dbt project (`nexus_dbt`). Pipeline code is not implemented yet.

From the repo root (uses `~/.dbt/profiles.yml`):

```bash
uv run dbt debug --project-dir branches/dlt_dbt_clickhouse
```
