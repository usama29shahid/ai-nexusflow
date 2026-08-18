# Environments (dev / prd)

`env` is `dev` or `prd` (lowercase in object names). **Until Terraform (Phase 4), `dev` is the only environment.** Compose, dlt, dbt, MinIO, ClickHouse, and later Polaris all use `dev`. `prd` is a naming contract for later — do not stand up a second Compose “prod stack” in Phase 1.

**Same pattern on every capability.** Named backends use capability folders (`dlt_dbt_clickhouse`, `dlt_dbt_spark_iceberg`). Numbered folders remain for backends that are not named yet (`branch_3_databricks`, …).

| Surface | `dev` (now) | `prd` (after Terraform) |
| --- | --- | --- |
| ClickHouse databases | `raw_{source}_dev`, `stg_{source}_dev`; shared `int_dev`, `gold_dev`, `marts_dev` | same with `_prd` |
| Iceberg (Polaris) | catalog `nexus_dev`; schemas `raw_{source}`, `stg_{source}`, `int`, `gold`, `marts`, `pub` | catalog `nexus_prd`; **same schema names** |
| MinIO buckets | `{purpose}-dev` | `{purpose}-prd` |
| dbt | profile target `dev` | target `prd` |
| dlt (warehouse) | `raw_{source}_dev` + `nexus-dlt-dbt-clickhouse-dev` | `raw_{source}_prd` + `nexus-dlt-dbt-clickhouse-prd` |
| dlt (lakehouse) | `nexus_dev.raw_{source}` + `nexus-dlt-dbt-spark-iceberg-archive-dev` | `nexus_prd.raw_{source}` + archive `-prd` |

One dbt project and one dlt codebase **per capability**. Env is **target / config**, not a forked repo.

Details: [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md), [dlt-dbt-spark-iceberg.md](dlt-dbt-spark-iceberg.md), [dlt-extraction.md](dlt-extraction.md), [dbt-modeling.md](dbt-modeling.md).
