# Branch 1 dbt (nexus_dbt)

Warehouse transformations for **Branch 1** (ClickHouse). Run from the repository root with host uv:

```bash
uv run dbt run --project-dir branches/branch_1_clickhouse/dbt --profiles-dir branches/branch_1_clickhouse/dbt
uv run dbt test --project-dir branches/branch_1_clickhouse/dbt --profiles-dir branches/branch_1_clickhouse/dbt
```

Copy `profiles.example.yml` to `profiles.yml` in this folder before the first run. Do not commit `profiles.yml`.
