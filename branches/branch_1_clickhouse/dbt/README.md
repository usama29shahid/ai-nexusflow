# Branch 1 dbt (nexus_dbt)

Warehouse transformations for **Branch 1** (ClickHouse). Run from the repository root with host uv:

```bash
uv run dbt run --project-dir branches/branch_1_clickhouse/dbt
uv run dbt test --project-dir branches/branch_1_clickhouse/dbt
```

Profiles and ClickHouse connection are not wired yet (Phase 1 Milestone 1).
