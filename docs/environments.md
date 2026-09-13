# Environments (dev / prd)

`env` is `dev` or `prd` (lowercase in object names). **Until Terraform, `dev` is the only environment in use.** Compose, dlt, dbt, MinIO, ClickHouse, and later Polaris all use `dev`. `prd` is a naming contract for later — do not stand up a second Compose “prod stack” before Terraform.

**Same pattern on every capability.** Capability folders: `dlt_dbt_clickhouse`, `dlt_dbt_spark_iceberg`.

## Warehouse ClickHouse naming

Env on **databases only**; table names have **no** env suffix. Implementation record: [bronze-silver-cutover.md](bronze-silver-cutover.md).

| Layer | Database | Table pattern | Example (`dev`) |
| --- | --- | --- | --- |
| Bronze | `bronze_{env}` | `raw_{source}__{endpoint}` | `bronze_dev.raw_route__products` |
| Silver | `silver_{env}` | `stg_{source}__{endpoint}` | `silver_dev.stg_route__products` |
| Intermediate | `intermediate_{env}` | `int_*` | later |
| Gold | `gold_{env}` | `dim_*` / `brg_*` / `fct_*` / `evt_*` | products SCD2 live |

| Marts | `marts_{env}` | `mart_*` | later |
| Published | `published_{env}` | `pub_*` | later |
| Elementary | `elementary_{env}` | Elementary package models | with dbt |

**dlt physical naming:**

```text
{database}.{dataset_name}{separator}{table_name}
```

- `database` = `bronze_{env}`
- `dataset_name` = `raw_{source}` (no env; e.g. `raw_route`)
- `dataset_table_separator` = `__` (not default `___`)
- table/resource = `{endpoint}` → `bronze_dev.raw_route__products`
- Nested arrays (dlt): `raw_route__products__images`, `raw_route__products__subcategory`

Archive MinIO layout is unchanged: `nexus-dlt-dbt-clickhouse-{env}/{source}/{endpoint}/...`.

**Legacy:** `warehouse.raw_route_{env}___products` — obsolete after cutover; optional DROP after verify.

| Surface | `dev` | `prd` (after Terraform) |
| --- | --- | --- |
| ClickHouse (warehouse) | `bronze_dev`, `silver_dev`, … | `bronze_prd`, `silver_prd`, … |
| Iceberg (Polaris) | catalog `nexus_dev`; schemas `raw_{source}`, `stg_{source}`, `int`, `gold`, `marts`, `pub` | catalog `nexus_prd`; **same schema names** |
| MinIO buckets | `{purpose}-dev` | `{purpose}-prd` |
| dbt | profile target `dev` | target `prd` |
| dlt (warehouse) | `bronze_dev` + `nexus-dlt-dbt-clickhouse-dev` | `bronze_prd` + bucket `-prd` |
| dlt (lakehouse) | `nexus_dev.raw_{source}` + archive `-dev` | `nexus_prd.raw_{source}` + archive `-prd` |

One dbt project and one dlt codebase **per capability**. Env is **target / config**, not a forked repo.

**Variable:** `NEXUS_ENV` (`dev` or `prd`, default **`dev`**). Python/dlt read it. dbt `--target` must be the same value (`target.name`). Shared run id is `NEXUS_RUN_ID` (see capability docs).

ClickHouse process users for warehouse: see [rbac.md](rbac.md) (`nexus_loader` / `nexus_transformer` / …).

### Job vs table vs bucket

These are three different names. Do not reuse the dlt job name as the MinIO bucket. Prefer aligning the job/script name with the Bronze table (resource) name; do not use opaque names such as `pipe_one`.

| Name | Question it answers | Example (`dev`) |
| --- | --- | --- |
| **Job** (dlt script / later Airflow task) | Which extract ran? | `products.py` / `route_products` |
| **Table** (REST resource / physical) | What entity is stored? | `raw_route__products` |
| **Bucket** (capability + env) | Which archive owns the JSONL? | `nexus-dlt-dbt-clickhouse-dev` |

A second Route endpoint (`categories`) is a new job and a new table under the same `bronze_{env}` database. Prefixes inside the archive bucket stay `{source}/{endpoint}/...`.

Same-contract URL parameters do not create a new table; they become job parameters. Route source contract: [route-ingestion.md](route-ingestion.md).

Worked example: [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md), [dlt-dbt-spark-iceberg.md](dlt-dbt-spark-iceberg.md). Details: [dlt-extraction.md](dlt-extraction.md), [dbt-modeling.md](dbt-modeling.md).

## Phase 2 is additive (Terraform / GitHub Actions)

Phase 2 **adds** workflow files and Terraform modules. It does **not** rewrite dlt, dbt, DAGs, or `./scripts/start.sh`. If a later change would rename Bronze tables, invent a second ELT runner, or fork the repo per env, the design is wrong.

| Phase 2 adds | Reuses (already locked) |
| --- | --- |
| `.github/workflows/` (lint, test, optional VPS deploy) | `uv run`, existing tests, `./scripts/start.sh` |
| Terraform modules (create `bronze_{env}`, `silver_{env}`, `{purpose}-{env}` buckets, ClickHouse users) | Names in this document; [rbac.md](rbac.md) `nexus_loader` / `nexus_transformer` |
| Secret injection on the VPS or in CI | Same env var names Vault Agent already renders ([vault.md](vault.md)) |

Rules:

- **One execution path.** Airflow (or a manual host command) runs `./scripts/start.sh` → dlt / dbt / observability. GitHub Actions **lints, tests, and optionally deploys** (`git pull` + `start.sh` on the VPS). Actions is not a second place that runs ingest or transform.
- **One codebase.** `NEXUS_ENV` / dbt `--target` select `dev` or `prd`. Do not add a `prd` git branch or a second Compose “prod stack.”
- **Same names.** Terraform creates the databases and buckets already listed above. It does not introduce `prod` suffixes or `raw_*_prd` table names.
- **Same secrets contract.** Apps read `os.environ` / dbt `env_var`. They never call Vault or the GitHub API. If CI injects credentials, they are still `CLICKHOUSE_LOADER_*` / `CLICKHOUSE_TRANSFORMER_*` into `start.sh`.

VPS deploy uses the same Compose + host `uv` model as WSL ([setup.md](setup.md), [orchestration/airflow/README.md](../orchestration/airflow/README.md)). Set `NEXUS_HOST_USER` / `NEXUS_REPO_ROOT` to that machine’s user and clone path.

Public UIs on a hostname (capstone): **Caddy + subdomains**, designed in [edge-proxy.md](edge-proxy.md). Not implemented yet. Do not add a Caddyfile to the Airflow host-exec commit.
