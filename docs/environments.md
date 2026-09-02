# Environments (dev / prd)

`env` is `dev` or `prd` (lowercase in object names). **Until Terraform (Phase 2), `dev` is the only environment.** Compose, dlt, dbt, MinIO, ClickHouse, and later Polaris all use `dev`. `prd` is a naming contract for later — do not stand up a second Compose “prod stack” in Phase 1.

**Same pattern on every capability.** Capability folders: `dlt_dbt_clickhouse`, `dlt_dbt_spark_iceberg`.

| Surface | `dev` (now) | `prd` (after Terraform) |
| --- | --- | --- |
| ClickHouse databases | `raw_{source}_dev`, `stg_{source}_dev`; shared `int_dev`, `gold_dev`, `marts_dev` | same with `_prd` |
| Iceberg (Polaris) | catalog `nexus_dev`; schemas `raw_{source}`, `stg_{source}`, `int`, `gold`, `marts`, `pub` | catalog `nexus_prd`; **same schema names** |
| MinIO buckets | `{purpose}-dev` | `{purpose}-prd` |
| dbt | profile target `dev` | target `prd` |
| dlt (warehouse) | `raw_{source}_dev` + `nexus-dlt-dbt-clickhouse-dev` | `raw_{source}_prd` + `nexus-dlt-dbt-clickhouse-prd` |
| dlt (lakehouse) | `nexus_dev.raw_{source}` + `nexus-dlt-dbt-spark-iceberg-archive-dev` | `nexus_prd.raw_{source}` + archive `-prd` |

One dbt project and one dlt codebase **per capability**. Env is **target / config**, not a forked repo.

**Variable:** `NEXUS_ENV` (`dev` or `prd`, default **`dev`**). Python/dlt read it. dbt `--target` must be the same value (`target.name`). Shared run id is `NEXUS_RUN_ID` (see capability docs). Until Terraform, only `dev` is used.

### Job vs table vs bucket

These are three different names. Do not reuse the dlt job name as the MinIO bucket. Prefer aligning the job/script name with the Bronze table (resource) name; do not use opaque names such as `pipe_one`.

| Name | Question it answers | Example (`dev`) |
| --- | --- | --- |
| **Job** (dlt script / later Airflow task) | Which extract ran? | `products.py` / `route_products` |
| **Table** (REST resource) | What entity is stored? | `products` |
| **Bucket** (capability + env) | Which archive owns the JSONL? | warehouse: `nexus-dlt-dbt-clickhouse-dev`; lakehouse: `nexus-dlt-dbt-spark-iceberg-archive-dev` |

Override dlt’s default “pipeline name = dataset.” Dataset/database (warehouse) or catalog.schema (lakehouse) stay env/layer names. The table stays the resource. The job stays the task id and should match the resource when practical.

A second Route endpoint (`categories`) is a new job and a new table. It still uses the **same** archive bucket for that capability+env. Prefixes inside the bucket are `{source}/{endpoint}/...`.

Same-contract URL parameters do not create a new table; they become job parameters. A new table is required only when the payload contract differs. Route source contract: [route-ingestion.md](route-ingestion.md).

Worked example (same API, both capabilities): [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md), [dlt-dbt-spark-iceberg.md](dlt-dbt-spark-iceberg.md).

Details: [dlt-extraction.md](dlt-extraction.md), [dbt-modeling.md](dbt-modeling.md).
