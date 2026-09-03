# dlt_dbt_spark_iceberg — open lakehouse ELT

Public name: **dlt_dbt_spark_iceberg** (dlt → dbt on Spark → Iceberg). This is the open lakehouse **capability**, not a git branch. Trino is serving/BI. Apache Polaris is the Iceberg REST catalog. ClickHouse is not on this path (a later optional feature may query Iceberg; it is not required here).

The five-backend platform story lives in [architecture.md](architecture.md). Extraction policy: [dlt-extraction.md](dlt-extraction.md). Route source contract: [route-ingestion.md](route-ingestion.md). Modeling DAG: [dbt-modeling.md](dbt-modeling.md). Enhanced modeling backlog: [enhanced-modeling-strategy.md](enhanced-modeling-strategy.md). Env: [environments.md](environments.md). Secrets: [vault.md](vault.md). Lakehouse engine RBAC: **held** — [rbac.md](rbac.md). Warehouse peer: [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md).

dbt project: `branches/dlt_dbt_spark_iceberg` (`nexus_lakehouse`). Config key: `dlt_dbt_spark_iceberg` in [`config/branches.yaml`](../config/branches.yaml).

**Independent of `dlt_dbt_clickhouse`.** Same primary API (`route`), separate Python/dlt/dbt code. Shared infrastructure only (Compose, MinIO **service**, later Polaris / Spark / Trino). Isolation is buckets and catalogs, not shared pipeline modules. Docker profile for this stack is **`lakehouse`** (not `spark`); MinIO is unprofiled. See [setup.md](setup.md).

```text
REST API
  → dlt (extract once)
       ├─ MinIO `nexus-dlt-dbt-spark-iceberg-archive-{env}` (immutable JSONL archive)
       └─ Iceberg Bronze via Apache Polaris
            nexus_{env}.raw_{source}.{table}
            → dbt-spark target `{env}` (DAG, not a ladder)
                 stg_* → int_* → Conformed Gold (dim / fct / evt)
                      → domain int_* → domain marts
                      → optional published
            → Trino reads Iceberg (BI / analysts)
```

Until source DAGs exist, the path runs on the host with `uv run` or via Airflow (Phase 1) against Docker Spark/Thrift (Milestone 2). Generate **one `run_id` per run** (`NEXUS_RUN_ID`) and pass it to **both** dlt and dbt. When Airflow orchestrates, the DAG **`run_id`** is `NEXUS_RUN_ID`. Env is **`NEXUS_ENV` (default `dev`) until Terraform**.

Spark writes and maintains Iceberg (industry lakehouse pattern). Trino does **not** run dbt. Do not use the dbt-trino adapter on this capability.

---

## Responsibility split

| Layer | Owns | Does not own |
| --- | --- | --- |
| **dlt** | REST auth, pagination, retries, incremental cursors, archive write, Iceberg Bronze via Polaris, `run_id` on rows | Kimball models, SCD, marts, department metrics |
| **MinIO archive bucket** | Byte-stable raw payloads for replay | Iceberg data files |
| **MinIO warehouse bucket** | Iceberg data + metadata files | JSONL archive |
| **Apache Polaris** | REST catalog: `nexus_{env}` catalog, namespaces, table commits | Compute |
| **Iceberg Bronze** | Queryable **history of loads** | Business grain, SCD2 |
| **dbt-spark** | Staging, intermediates, Gold, domain marts, tests (SQL default; Python/PySpark only when SQL is a poor fit) | Hitting REST APIs; serving BI |
| **Spark** | Transform compute, Iceberg writes | Durable storage of record |
| **Trino** | Interactive SQL / BI on Iceberg | dbt transforms |
| **Airflow (later)** | Schedule, retries of **tasks**, per-source DAGs, remote task logs | Replacing dlt/dbt as the transform engine |

Extract **once**. Dual destination (archive + Bronze). Do not scrape the API twice. dlt writes Iceberg Bronze through Polaris — no extra Parquet-then-convert job.

---

## MinIO: same service, separate buckets

Until Terraform, only `-dev` exists.

| Bucket | Role |
| --- | --- |
| `nexus-dlt-dbt-clickhouse-dev` | Branch 1 JSONL archive. Not this capability. |
| `nexus-dlt-dbt-spark-iceberg-archive-dev` | This capability’s raw API archive (replay). Not Iceberg. |
| `nexus-dlt-dbt-spark-iceberg-dev` | Iceberg warehouse root for Polaris catalog `nexus_dev`. |
| `nexus-airflow-logs-dev` | Airflow remote task logs (Phase 1). Not data. |
| `nexus-telemetry-dev` | Observability data lake (Phase 1). Not raw API archive. |

Archive keys (same logic as the warehouse capability; different bucket):

```text
s3://nexus-dlt-dbt-spark-iceberg-archive-dev/
  {source}/
    {endpoint}/
      [{param_variant}/]
        dt=YYYY-MM-DD/
          run_id={run_id}/
            part-*.jsonl.gz
```

Archive objects are **immutable**. Format: **JSONL** (compressed). Do not put Iceberg on this archive.

**Replay:** read the prefix, load Iceberg Bronze as a **new `run_id` (append)**, then `dbt run`. Do not mutate archive objects.

Warehouse (catalog-managed):

```text
s3://nexus-dlt-dbt-spark-iceberg-dev/warehouse/
  {namespace}/{table}/data/...
  {namespace}/{table}/metadata/...
```

---

## Three-level names (Polaris)

ClickHouse is two-level (`gold_dev.dim_repo`). Iceberg is three-level. **Apache Polaris** owns the catalog.

```text
catalog . schema . table
nexus_{env} . {schema} . {table}
```

| Level | Polaris / Iceberg | Trino | This platform |
| --- | --- | --- | --- |
| 1 | Polaris catalog | catalog | **environment** (`nexus_dev`, later `nexus_prd`) |
| 2 | namespace | schema | **layer** (and source for landing) |
| 3 | table | table | **model name** |

Do **not** encode env in schema or table (`gold_dev`). Do **not** nest namespaces (`gold.dev.dim_repo`). Spark and Trino must use the **same** Polaris catalog name.

| Schema | Layer | Writer | Example |
| --- | --- | --- | --- |
| `raw_{source}` | Bronze | dlt | `nexus_dev.raw_route.products` |
| `stg_{source}` | Silver staging | dbt-spark | `nexus_dev.stg_route.stg_route_products` |
| `int` | Shared + domain int | dbt-spark | `nexus_dev.int.int_product_keys` |
| `gold` | Conformed gold | dbt-spark | `nexus_dev.gold.dim_product` |
| `marts` | Domain marts | dbt-spark | `nexus_dev.marts.mart_product_performance` |
| `pub` | Published (optional) | dbt-spark | `nexus_dev.pub.pub_catalog` |

Do **not** create `gold_route`. Shared Gold cannot live in a source schema.

Table prefixes: `stg_*`, `int_*`, `dim_*`, `fct_*`, `evt_*`, `mart_*`, `pub_*`. Same DAG as [dbt-modeling.md](dbt-modeling.md). Gold is already queryable in Trino; add `pub` when a BI/app contract exists.

Same logical table vs ClickHouse:

| `dlt_dbt_clickhouse` | `dlt_dbt_spark_iceberg` |
| --- | --- |
| `gold_dev.dim_product` | `nexus_dev.gold.dim_product` |
| `raw_route_dev.products` | `nexus_dev.raw_route.products` |
| `stg_route_dev.stg_route_products` | `nexus_dev.stg_route.stg_route_products` |

---

## dbt-spark

Project `nexus_lakehouse`. Profile target = `NEXUS_ENV` (`dev` until Terraform). Adapter **`dbt-spark`**. Model `+schema` maps to Iceberg namespaces above.

SQL models by default. Python/PySpark models only when SQL is a poor fit.

### Thrift (default) vs PySpark (complex models only)

Thrift is the **dbt client protocol**, not a replacement for PySpark. Both talk to the **same** Spark SQL engine. dbt stays on the host; Spark stays in Docker (Milestone 2).

| Model | Connection | Why |
| --- | --- | --- |
| `.sql` (default) | `dbt-spark` **`method: thrift`** → Spark Thrift / HiveServer2 in Docker | dbt prefers SQL; Airflow later runs `dbt run` against this endpoint |
| `.py` (exception) | PySpark **SparkSession** (`method: session`) | Thrift accepts SQL only, not DataFrame programs |

`spark.sql(...)` in PySpark is the same Spark SQL as Thrift. Do not put the Spark driver in `.venv` or use PySpark for every model on this branch.

Pass `var('run_id')` on every run (same value as dlt).

`{{ target.name }}` is the Polaris **catalog** (`nexus_{{ target.name }}`). Model `+schema` stays `stg_route`, `int`, `gold`, … — **do not** copy ClickHouse `stg_route_{{ target.name }}` / `gold_{{ target.name }}`.

---

## Worked example: Route `products`

Same job and table as the warehouse example. **Separate code** under `branches/dlt_dbt_spark_iceberg`. Do not write the ClickHouse archive bucket or `raw_route_dev`. Warehouse peer: [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md). Source contract: [route-ingestion.md](route-ingestion.md). Pipelines are **not implemented yet**.

Public catalog endpoint — no JWT. Opaque job names such as `pipe_one` are not used.

**Three names** ([environments.md](environments.md)):

```text
Job           products.py / route_products
Table         products
Archive       nexus-dlt-dbt-spark-iceberg-archive-{env}
Warehouse S3  nexus-dlt-dbt-spark-iceberg-{env}     # Iceberg files; not JSONL; not per-job
Prefix        route/products/dt=.../run_id=.../part-*.jsonl.gz
Bronze        nexus_{env}.raw_route.products
```

Do not name the catalog, schema, table, or either MinIO bucket after the job. Script name, Bronze table, and archive `{endpoint}` segment stay aligned (`products`).

**Archive (`NEXUS_ENV=dev`):**

```text
s3://nexus-dlt-dbt-spark-iceberg-archive-dev/
  route/products/dt=2026-08-18/run_id=local-20260818T175000Z/part-000.jsonl.gz
```

**dbt** — `--target` = env. Catalog from target; schemas are layer names without env.

`models/staging/route/sources.yml` (proposed):

```yaml
version: 2
sources:
  - name: route_raw
    database: nexus_{{ target.name }}
    schema: raw_route
    tables:
      - name: products
```

`dbt_project.yml` (proposed fragment; already the folder `+schema` intent):

```yaml
models:
  nexus_lakehouse:
    staging:
      route:
        +schema: stg_route
    intermediate:
      +schema: int
    gold:
      +schema: gold
    marts:
      +schema: marts
    published:
      +schema: pub
```

Spark profile target `dev` / `prd` must attach catalog `nexus_dev` / `nexus_prd`. Staging: `nexus_dev.stg_route.stg_route_products`. dlt ends at archive + Bronze; post-Bronze work is dbt-only.

From the repo root (when Spark Thrift and code exist):

```bash
export NEXUS_ENV=dev
export NEXUS_RUN_ID=local-$(date -u +%Y%m%dT%H%M%SZ)
uv run python branches/dlt_dbt_spark_iceberg/dlt/route/products.py
uv run dbt run --project-dir branches/dlt_dbt_spark_iceberg --target "$NEXUS_ENV" \
  --vars "{\"run_id\": \"$NEXUS_RUN_ID\"}"
```

`prd` later: same files, `NEXUS_ENV=prd` → archive `-prd`, catalog `nexus_prd`, schemas unchanged.

---

## Compose (Milestone 2)

Python/dlt/dbt on the **host**. Polaris, Spark Thrift, Trino, and MinIO in Docker. ClickHouse stays on profile `clickhouse` only.

Profiles: `clickhouse` (ClickHouse + MinIO), `lakehouse` (MinIO + Polaris + Spark Thrift + Trino). Default `.env`: `COMPOSE_PROFILES=clickhouse,lakehouse`. Config under `docker/lakehouse/`. See [setup.md](setup.md).

---

## Folder layout

```text
branches/dlt_dbt_spark_iceberg/
  dlt/route/                   # primary; other sources get their own folders later
  models/staging/{source}/     → schema stg_{source}
  models/intermediate/         → schema int
  models/gold/{dims,facts,events}/ → schema gold
  models/marts/                → schema marts
  models/published/            → schema pub
```
