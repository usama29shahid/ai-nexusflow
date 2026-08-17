# Environments (dev / prd)

`env` is `dev` or `prd` (lowercase in object names). **Until Terraform (Phase 4), `dev` is the only environment.** Compose, dlt, dbt, MinIO, and ClickHouse all use `dev`. `prd` is a naming contract for later — do not stand up a second Compose “prod stack” in Phase 1.

**Same pattern on every capability.** Until other backends are named, they still use numbered folders (`branch_2_iceberg`, …).

| Surface | `dev` (now) | `prd` (after Terraform) |
| --- | --- | --- |
| ClickHouse databases | `raw_{source}_dev`, `stg_{source}_dev`; shared `int_dev`, `gold_dev`, `marts_dev` | same with `_prd` |
| MinIO buckets | `{purpose}-dev` | `{purpose}-prd` |
| dbt | profile target `dev` | target `prd` |
| dlt | `raw_{source}_dev` + `nexus-dlt-dbt-clickhouse-dev` | `raw_{source}_prd` + `nexus-dlt-dbt-clickhouse-prd` |

One dbt project and one dlt codebase. Env is **target / config**, not a forked repo.

Details: [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md) (ClickHouse + MinIO + run_id), [dlt-extraction.md](dlt-extraction.md), [dbt-modeling.md](dbt-modeling.md).
