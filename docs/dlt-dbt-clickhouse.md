# dlt_dbt_clickhouse — warehouse ELT

Public name: **dlt_dbt_clickhouse** (dlt → dbt → ClickHouse). This is the warehouse ELT **capability**, not a git branch.

The five-backend platform story lives in [architecture.md](architecture.md). Extraction: [dlt-extraction.md](dlt-extraction.md). Route source contract: [route-ingestion.md](route-ingestion.md). Modeling: [dbt-modeling.md](dbt-modeling.md). Enhanced modeling backlog: [enhanced-modeling-strategy.md](enhanced-modeling-strategy.md). Logs: [observability.md](observability.md). Env: [environments.md](environments.md).

dbt project: `branches/dlt_dbt_clickhouse`. Config key: `dlt_dbt_clickhouse` in [`config/branches.yaml`](../config/branches.yaml). Docker profile: **`clickhouse`** (MinIO always on). See [setup.md](setup.md).

This capability is **ClickHouse-primary**. MinIO here is a **raw API archive**, not the Iceberg lakehouse backend.

```text
REST API
  → dlt (extract once)
       ├─ MinIO `nexus-dlt-dbt-clickhouse-{env}` (immutable JSONL archive)
       └─ ClickHouse `raw_{source}_{env}` (append-only Bronze, run_id on every row)
            → dbt target `{env}` (DAG, not a ladder)
                 stg_* → int_* → Conformed Gold (dim / fct / evt)
                      → domain int_* → domain marts
                      → optional published
```

Until source DAGs exist, the same path runs on the host with `uv run` or via Airflow (Phase 1). Generate **one `run_id` per run** (`NEXUS_RUN_ID`) and pass it to **both** dlt and dbt. When Airflow orchestrates, the DAG **`run_id`** is `NEXUS_RUN_ID`. Env is **`NEXUS_ENV` (default `dev`) until Terraform**.

---

## Responsibility split

| Layer | Owns | Does not own |
| --- | --- | --- |
| **dlt** | REST auth, pagination, retries, incremental cursors, archive write, Bronze load, `run_id` on rows | Kimball models, SCD, marts, department metrics |
| **MinIO** | Byte-stable raw payloads for replay | Analytical Gold |
| **ClickHouse Bronze** | Queryable **history of loads** | Business grain, SCD2 |
| **dbt** | Staging, intermediates, Gold, domain marts, tests | Hitting REST APIs |
| **Airflow (later)** | Schedule, retries of **tasks**, per-source DAGs, remote task logs | Replacing dlt/dbt as the transform engine |

Extract **once**. Dual destination (archive + Bronze). Do not scrape the API twice for the two stores.

---

## MinIO: local S3, one bucket per capability **and env**

Same MinIO **service**. Isolation is **one bucket per capability per env**. Until Terraform, only `-dev` exists.

| Bucket | Role |
| --- | --- |
| `nexus-dlt-dbt-clickhouse-dev` | This capability’s raw API archive (replay). Not Iceberg. |
| `nexus-dlt-dbt-spark-iceberg-archive-dev` | Lakehouse JSONL archive (`dlt_dbt_spark_iceberg`). Not this Bronze. |
| `nexus-dlt-dbt-spark-iceberg-dev` | Iceberg warehouse for Polaris catalog `nexus_dev`. Not this Bronze. |
| `nexus-airflow-logs-dev` | Airflow remote task logs (Phase 1). Not data. |
| `nexus-telemetry-dev` | Observability data lake (Phase 1). Not raw API archive. |

Later: the same names with `-prd`.

Object keys inside the archive bucket:

```text
s3://nexus-dlt-dbt-clickhouse-dev/
  {source}/
    {endpoint}/
      [{param_variant}/]
        dt=YYYY-MM-DD/
          run_id={run_id}/
            part-*.jsonl.gz
```

Examples of `{source}`: `route` (primary), later secondary sources such as `dataforseo`. `{endpoint}` is the REST resource. `{param_variant}` is used only when the **payload contract** differs, not for every id in a URL.

Archive objects are **immutable**. Format: **JSONL** (compressed). Do not put Iceberg on this archive.

**Replay:** read the prefix, load Bronze as a **new `run_id` (append)**, then `dbt run`. Do not mutate archive objects. Do not delete prior Bronze rows.

---

## ClickHouse databases

ClickHouse has **no schemas** (only `database.table`). **Hybrid:** per-source databases for landing (raw/stg); **shared** databases for int, gold, marts, pub.

Do **not** create `gold_route_dev`. Shared Conformed Gold cannot live inside a source database.

Until Terraform, `env=dev`.

```text
raw_{source}_{env}     raw_route_dev.products
stg_{source}_{env}     stg_route_dev.stg_route_products
int_{env}              int_dev.int_product_keys
gold_{env}             gold_dev.dim_product
marts_{env}            marts_dev.mart_product_performance
pub_{env}              pub_dev.pub_...              -- optional
```

| Database | Maps to | Who writes |
| --- | --- | --- |
| `raw_{source}_{env}` | bronze / raw | dlt |
| `stg_{source}_{env}` | silver staging | dbt `stg_*` for that source |
| `int_{env}` | shared int + domain int | dbt `int_*` |
| `gold_{env}` | conformed gold | dbt `dim_*` / `fct_*` / `evt_*` — **all sources** |
| `marts_{env}` | domain marts | dbt |
| `pub_{env}` | published | dbt, optional |

Gold table names are **conformed** (`dim_product`, not `route_dim_product`) unless the requirement explicitly names a separate dim.

Gold in ClickHouse is already queryable. Do not add `pub` on the first pipeline unless a BI/app contract exists.

### Repo folders (match databases)

```text
branches/dlt_dbt_clickhouse/
  dlt/{source}/                 → raw_{source}_{env}
  models/staging/{source}/      → stg_{source}_{env}
  models/intermediate/shared/   → int_{env}
  models/gold/dims|facts|events → gold_{env}
  models/marts/{domain}/        → marts_{env}
  models/published/             → pub_{env}
```

Staging splits by **API**. Gold splits by **grain** (dims/facts/events), not by route/dataforseo. See [dbt-modeling.md](dbt-modeling.md).

---

## Pipelines: dlt unit vs Gold

A **dlt pipeline** is per REST **endpoint** (and per `{param}` only when schema/grain/auth/incremental **contract** differs). Same path, same schema, different id → one parameterized pipeline, not two Gold tables.

A **source** (`route`, later others) groups those endpoint pipelines. Airflow later: **one DAG per source**, tasks per endpoint, then **one dbt run with selectors**.

**Gold is requirement-driven, shared by default:**

```text
url/v1/{param1}  +  "create separate dim_any_name1"  →  dim_any_name1
url/v1/{param2}  +  "create separate dim_any_name2"  →  dim_any_name2

url/v1/{param1}  (no separate-dim instruction)  ─┐
url/v1/{param2}  (no separate-dim instruction)  ─┴─►  one dim_name
```

A URL param is an extract variant. A **named** dim in the requirement is a modeling decision. Do not infer a new `dim_*` from the URL alone.

**Domain marts are dbt-only.** No extra dlt, no extra archive, no second Bronze. They `ref()` Gold (and/or domain `int_*`).

---

## Run id

One correlation id for a run, used by **both dlt and dbt**. Do not invent a second id system.

**Manual runs:** generate one id per invocation — `local-{utc_timestamp}` or a UUID. **Airflow runs:** use the DAG `run_id` as `NEXUS_RUN_ID`. Pass the **same** value into dlt (Bronze column) and dbt (`var('run_id')`). Do **not** reuse a single eternal string like `"default"` on every load — Bronze is append-only history.

If dbt is run alone, `var('run_id')` may fall back to `'local'` for that ad-hoc run. **Loads** must still get a unique id.

**After Airflow:** DAG `run_id` replaces the generator. Same column, same dbt var.

Flow:

1. Create or receive `run_id`.
2. Pass into dlt; store on every Bronze row (`run_id` / `_ingest_run_id`). Keep `_dlt_load_id` as dlt telemetry (may differ).
3. Pass into dbt for lineage, incremental windows, as-of logic.

---

## DAG, not a ladder

Which models exist depends on the **requirement**. There is no mandatory full stack. See [dbt-modeling.md](dbt-modeling.md).

---

## Worked example: Route `products`

Illustration of the rules above. Pipelines are **not implemented yet**. Full Route source contract: [route-ingestion.md](route-ingestion.md). Lakehouse copy of the same API: [dlt-dbt-spark-iceberg.md](dlt-dbt-spark-iceberg.md).

Assumptions: source Route API, endpoint `GET /api/v1/products`, resource `products`. Public catalog — no JWT. Opaque job names such as `pipe_one` are not used. First Milestone 1 slice is catalog-only (`products`, `categories`, `brands`).

**Three names** ([environments.md](environments.md)):

```text
Job     products.py / route_products   # script now; Airflow task id later
Table   products
Bucket  nexus-dlt-dbt-clickhouse-{env}            # all warehouse JSONL for this env
Prefix  route/products/dt=.../run_id=.../part-*.jsonl.gz
Bronze  raw_route_{env}.products
```

Do not name the ClickHouse database or MinIO bucket after the job. dlt dataset = `raw_route_{env}`, not the script name. Script name, Bronze table, and archive `{endpoint}` segment stay aligned (`products`).

**Archive (`NEXUS_ENV=dev`):** one MinIO service; dlt writes objects (prefixes, not mkdir):

```text
s3://nexus-dlt-dbt-clickhouse-dev/
  route/products/dt=2026-08-18/run_id=local-20260818T175000Z/part-000.jsonl.gz
```

**dbt** — env is `--target` (`target.name`). ClickHouse `schema` in dbt is the **database**. Physical names are `stg_route_dev`, `gold_dev`, etc.

- **`sources.yml`:** put `_{{ target.name }}` in `database` / `schema` explicitly.
- **`dbt_project.yml` `+schema`:** use the **unsuffixed** layer name (`stg_route`, `gold`, …). This project’s `generate_schema_name` macro appends `_{{ target.name }}`. Do **not** also write `stg_route_{{ target.name }}` in `+schema` — that would become `stg_route_dev_dev`.

`models/staging/route/sources.yml` (proposed):

```yaml
version: 2
sources:
  - name: route_raw
    database: raw_route_{{ target.name }}
    schema: raw_route_{{ target.name }}
    tables:
      - name: products
```

`dbt_project.yml` (proposed fragment; matches the live macro):

```yaml
models:
  nexus_clickhouse:
    staging:
      route:
        +schema: stg_route          # → stg_route_{{ target.name }}
    intermediate:
      +schema: int                  # → int_{{ target.name }}
    gold:
      +schema: gold                 # → gold_{{ target.name }}
    marts:
      +schema: marts                # → marts_{{ target.name }}
    published:
      +schema: pub                  # → pub_{{ target.name }}
```

Staging: `stg_route_dev.stg_route_products` via `{{ source('route_raw', 'products') }}`. Gold only if a requirement **names** a model (for example `dim_product`). dlt ends at MinIO + Bronze; all post-Bronze work is dbt-only.

From the repo root (when code exists):

```bash
export NEXUS_ENV=dev
export NEXUS_RUN_ID=local-$(date -u +%Y%m%dT%H%M%SZ)
uv run python branches/dlt_dbt_clickhouse/dlt/route/products.py
uv run dbt run --project-dir branches/dlt_dbt_clickhouse --target "$NEXUS_ENV" \
  --vars "{\"run_id\": \"$NEXUS_RUN_ID\"}"
```

`prd` later: same files, `NEXUS_ENV=prd` and `--target prd` → bucket `-prd`, databases `*_prd`.

---

## First pipeline (implementation later)

Working path: the example above (or one similar REST source) → dlt → MinIO `nexus-dlt-dbt-clickhouse-dev` + ClickHouse `raw_{source}_dev` → dbt `--target dev`. Facts, SCD2, marts, and `pub` only when the requirement needs them. No Spark, Databricks, Airflow, or LLM in that slice.
