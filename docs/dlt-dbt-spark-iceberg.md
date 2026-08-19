# dlt_dbt_spark_iceberg — open lakehouse ELT

Public name: **dlt_dbt_spark_iceberg** (dlt → dbt on Spark → Iceberg). This is the open lakehouse **capability**, not a git branch. Trino is serving/BI. Apache Polaris is the Iceberg REST catalog. ClickHouse is not on this path (a later optional feature may query Iceberg; it is not required here).

The five-backend platform story lives in [architecture.md](architecture.md). Extraction policy: [dlt-extraction.md](dlt-extraction.md). Modeling DAG: [dbt-modeling.md](dbt-modeling.md). Env: [environments.md](environments.md). Warehouse peer: [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md).

dbt project: `branches/dlt_dbt_spark_iceberg` (`nexus_lakehouse`). Config key: `dlt_dbt_spark_iceberg` in [`config/branches.yaml`](../config/branches.yaml).

**Independent of `dlt_dbt_clickhouse`.** Same first APIs (github, dataforseo, pokeapi), separate Python/dlt/dbt code. Shared infrastructure only (Compose, MinIO **service**, later Polaris / Spark / Trino). Isolation is buckets and catalogs, not shared pipeline modules. Docker profile for this stack is **`lakehouse`** (not `spark`); MinIO is unprofiled. See [setup.md](setup.md).

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

Until Airflow exists (Phase 2), the path runs on the host with `uv run` against Docker Spark/Thrift (added in Milestone 2). Generate **one `run_id` per local run** (`NEXUS_RUN_ID`) and pass it to **both** dlt and dbt. Env is **`NEXUS_ENV` (default `dev`) until Terraform**.

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
| `nexus-airflow-logs-dev` | Phase 2 Airflow remote task logs. Not data. |

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
| `raw_{source}` | Bronze | dlt | `nexus_dev.raw_github.repos` |
| `stg_{source}` | Silver staging | dbt-spark | `nexus_dev.stg_github.stg_github_repos` |
| `int` | Shared + domain int | dbt-spark | `nexus_dev.int.int_repo_keys` |
| `gold` | Conformed gold | dbt-spark | `nexus_dev.gold.dim_repo` |
| `marts` | Domain marts | dbt-spark | `nexus_dev.marts.mart_engineering` |
| `pub` | Published (optional) | dbt-spark | `nexus_dev.pub.pub_pokedex` |

Do **not** create `gold_github`. Shared Gold cannot live in a source schema.

Table prefixes: `stg_*`, `int_*`, `dim_*`, `fct_*`, `evt_*`, `mart_*`, `pub_*`. Same DAG as [dbt-modeling.md](dbt-modeling.md). Gold is already queryable in Trino; add `pub` when a BI/app contract exists.

Same logical table vs ClickHouse:

| `dlt_dbt_clickhouse` | `dlt_dbt_spark_iceberg` |
| --- | --- |
| `gold_dev.dim_repo` | `nexus_dev.gold.dim_repo` |
| `raw_github_dev.repos` | `nexus_dev.raw_github.repos` |
| `stg_github_dev.stg_github_repos` | `nexus_dev.stg_github.stg_github_repos` |

---

## dbt-spark

Project `nexus_lakehouse`. Profile target = `NEXUS_ENV` (`dev` until Terraform). Adapter **`dbt-spark`**. Model `+schema` maps to Iceberg namespaces above.

SQL models by default. Python/PySpark models only when SQL is a poor fit.

### Thrift (default) vs PySpark (complex models only)

Thrift is the **dbt client protocol**, not a replacement for PySpark. Both talk to the **same** Spark SQL engine. dbt stays on the host; Spark stays in Docker (Milestone 2).

| Model | Connection | Why |
| --- | --- | --- |
| `.sql` (default) | `dbt-spark` **`method: thrift`** → Spark Thrift / HiveServer2 in Docker | dbt prefers SQL; Airflow later runs `dbt run` against this endpoint |
| `.py` (exception) | PySpark **SparkSession** (`method: session`, or later Databricks) | Thrift accepts SQL only, not DataFrame programs |

`spark.sql(...)` in PySpark is the same Spark SQL as Thrift. Do not put the Spark driver in `.venv` or use PySpark for every model on this branch. Standalone PySpark **jobs** belong to Branch 4 (EMR), not this default path.

Pass `var('run_id')` on every run (same value as dlt).

`{{ target.name }}` is the Polaris **catalog** (`nexus_{{ target.name }}`). Model `+schema` stays `stg_github`, `int`, `gold`, … — **do not** copy ClickHouse `stg_github_{{ target.name }}` / `gold_{{ target.name }}`.

---

## Worked example: GitHub `pipe_one`

Same job and table as the warehouse example. **Separate code** under `branches/dlt_dbt_spark_iceberg`. Do not write the ClickHouse archive bucket or `raw_github_dev`. Warehouse peer: [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md). Pipelines are **not implemented yet**.

`{param1}` is a URL id with the same payload contract → one parameterized pipeline.

**Three names** ([environments.md](environments.md)):

```text
Job           pipe_one
Table         pull_request
Archive       nexus-dlt-dbt-spark-iceberg-archive-{env}
Warehouse S3  nexus-dlt-dbt-spark-iceberg-{env}     # Iceberg files; not JSONL; not per-job
Prefix        github/pull_request/dt=.../run_id=.../part-*.jsonl.gz
Bronze        nexus_{env}.raw_github.pull_request
```

Do not name the catalog, schema, table, or either MinIO bucket `pipe_one`.

**Archive (`NEXUS_ENV=dev`):**

```text
s3://nexus-dlt-dbt-spark-iceberg-archive-dev/
  github/pull_request/dt=2026-08-18/run_id=local-20260818T175000Z/part-000.jsonl.gz
```

**dbt** — `--target` = env. Catalog from target; schemas are layer names without env.

`models/staging/github/sources.yml` (proposed):

```yaml
version: 2
sources:
  - name: github_raw
    database: nexus_{{ target.name }}
    schema: raw_github
    tables:
      - name: pull_request
```

`dbt_project.yml` (proposed fragment; already the folder `+schema` intent):

```yaml
models:
  nexus_lakehouse:
    staging:
      github:
        +schema: stg_github
    intermediate:
      +schema: int
    gold:
      +schema: gold
    marts:
      +schema: marts
    published:
      +schema: pub
```

Spark profile target `dev` / `prd` must attach catalog `nexus_dev` / `nexus_prd`. Staging: `nexus_dev.stg_github.stg_github_pull_request`.

From the repo root (when Spark Thrift and code exist):

```bash
export NEXUS_ENV=dev
export NEXUS_RUN_ID=local-$(date -u +%Y%m%dT%H%M%SZ)
uv run python branches/dlt_dbt_spark_iceberg/dlt/github/pipe_one.py
uv run dbt run --project-dir branches/dlt_dbt_spark_iceberg --target "$NEXUS_ENV" \
  --vars "{\"run_id\": \"$NEXUS_RUN_ID\"}"
```

`prd` later: same files, `NEXUS_ENV=prd` → archive `-prd`, catalog `nexus_prd`, schemas unchanged.

---

## Compose (Milestone 2)

Python/dlt/dbt on the **host**. Polaris, Spark (Thrift), Trino, MinIO in Docker. ClickHouse stays for the warehouse capability only.

Profiles (when services are added): `warehouse` (ClickHouse + MinIO), `lakehouse` (MinIO + Polaris + Spark + Trino).

---

## Folder layout

```text
branches/dlt_dbt_spark_iceberg/
  dlt/{github,dataforseo,pokeapi}/
  models/staging/{source}/     → schema stg_{source}
  models/intermediate/         → schema int
  models/gold/{dims,facts,events}/ → schema gold
  models/marts/                → schema marts
  models/published/            → schema pub
```
