# dlt_dbt_clickhouse — warehouse ELT

Public name: **dlt_dbt_clickhouse** (dlt → dbt → ClickHouse). This is the warehouse ELT **capability**, not a git branch.

The five-backend platform story lives in [architecture.md](architecture.md). Extraction: [dlt-extraction.md](dlt-extraction.md). Route source contract: [route-ingestion.md](route-ingestion.md). Modeling: [dbt-modeling.md](dbt-modeling.md). Enhanced modeling backlog: [enhanced-modeling-strategy.md](enhanced-modeling-strategy.md). Logs: [observability.md](observability.md). Env: [environments.md](environments.md). Secrets: [vault.md](vault.md). Warehouse engine RBAC: **implemented (dev)** — [rbac.md](rbac.md). Bronze/silver record: [bronze-silver-cutover.md](bronze-silver-cutover.md).

dbt project: `branches/dlt_dbt_clickhouse`. Config key: `dlt_dbt_clickhouse` in [`config/branches.yaml`](../config/branches.yaml). Docker profile: **`clickhouse`** (MinIO always on). See [setup.md](setup.md).

This capability is **ClickHouse-primary**. MinIO here is a **raw API archive**, not the Iceberg lakehouse backend.

```text
REST API
  → dlt (extract once) as nexus_loader
       ├─ MinIO `nexus-dlt-dbt-clickhouse-{env}` (immutable JSONL archive)
       └─ ClickHouse `bronze_{env}.raw_{source}__{endpoint}` (append-only Bronze, run_id on every row)
            → dbt as nexus_transformer, target `{env}` (DAG, not a ladder)
                 silver_{env}.stg_* → intermediate_* → Conformed Gold (dim / fct / evt)
                      → domain int_* → domain marts
                      → optional published
```

The same path runs on the host with `uv run` or via Airflow (`route_clickhouse_products`). Generate **one `run_id` per run** (`NEXUS_RUN_ID`) and pass it to **both** dlt and dbt. When Airflow orchestrates, the DAG **`run_id`** is `NEXUS_RUN_ID`. Env is **`NEXUS_ENV` (default `dev`) until Terraform**.

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

ClickHouse has **no schemas** (only `database.table`). Env suffix on **shared layer databases only**. Table names have **no** env suffix. Do **not** create `gold_route_dev` — shared Conformed Gold cannot live inside a source database.

Until Terraform, `env=dev`. Full naming: [environments.md](environments.md).

```text
bronze_{env}           bronze_dev.raw_route__products
silver_{env}           silver_dev.stg_route__products
intermediate_{env}     intermediate_dev.int_product_keys
gold_{env}             gold_dev.dim_product
marts_{env}            marts_dev.mart_product_performance
published_{env}        published_dev.pub_...           -- optional
elementary_{env}       elementary_dev.*                -- Elementary package
```

| Database | Maps to | Who writes |
| --- | --- | --- |
| `bronze_{env}` | bronze / raw | dlt as `nexus_loader` |
| `silver_{env}` | silver staging | dbt `stg_*` as `nexus_transformer` |
| `intermediate_{env}` | shared int + domain int | dbt `int_*` |
| `gold_{env}` | conformed gold | dbt `dim_*` / `fct_*` / `evt_*` — **all sources** |
| `marts_{env}` | domain marts | dbt |
| `published_{env}` | published | dbt, optional |
| `elementary_{env}` | Elementary | dbt |

**dlt physical naming:** `database=bronze_{env}`, `dataset_name=raw_{source}`, `dataset_table_separator=__` → `bronze_dev.raw_route__products`. Nested: `raw_route__products__images`, `raw_route__products__subcategory`.

Gold table names are **conformed** (`dim_product`, not `route_dim_product`) unless the requirement explicitly names a separate dim.

Gold in ClickHouse is already queryable. Do not add `published` on the first pipeline unless a BI/app contract exists.

### Repo folders (match databases)

```text
branches/dlt_dbt_clickhouse/
  dlt/{source}/                 → bronze_{env}
  models/staging/{source}/      → silver_{env}
  models/intermediate/shared/   → intermediate_{env}
  models/gold/dims|facts|events → gold_{env}
  models/marts/{domain}/        → marts_{env}
  models/published/             → published_{env}
```

Staging splits by **API**. Gold splits by **grain** (dims/facts/events), not by route/dataforseo. See [dbt-modeling.md](dbt-modeling.md).

---

## Pipelines: dlt unit vs Gold

A **dlt pipeline** is per REST **endpoint** (and per `{param}` only when schema/grain/auth/incremental **contract** differs). Same path, same schema, different id → one parameterized pipeline, not two Gold tables.

A **source** (`route`, later others) groups those endpoint pipelines. Airflow: **one DAG per source + target + endpoint** (layer tasks: bronze → silver → gold → observability). First job: `route_clickhouse_products`.

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

## Worked example: Route `products` (implemented)

**Live reference:** [`dlt/route/products.py`](../branches/dlt_dbt_clickhouse/dlt/route/products.py). Org extraction norms (mandatory for the next endpoint): [dlt-extraction.md](dlt-extraction.md). Full Route source contract: [route-ingestion.md](route-ingestion.md). Lakehouse copy of the same API (Milestone 2): [dlt-dbt-spark-iceberg.md](dlt-dbt-spark-iceberg.md).

Assumptions: source Route API, endpoint `GET /api/v1/products`, resource `products`. Public catalog — no JWT. Full-refresh paginated extract → MinIO JSONL + ClickHouse Bronze + lake/OTLP. Opaque job names such as `pipe_one` are not used. Catalog follow-ons (`categories`, `brands`) must mirror this script’s norms.

**Three names** ([environments.md](environments.md)):

```text
Job     products.py / route_products   # script now; Airflow task id later
Table   products                       # REST resource / endpoint segment
Bucket  nexus-dlt-dbt-clickhouse-{env}
Prefix  route/products/dt=.../run_id=.../part-*.jsonl.gz
Bronze  bronze_{env}.raw_route__products   # dataset raw_route, separator __
```

Do not name the ClickHouse database or MinIO bucket after the job. dlt dataset = `raw_route` (no env), database = `bronze_{env}`. Script name, Bronze table endpoint segment, and archive `{endpoint}` stay aligned (`products`).

**Archive (`NEXUS_ENV=dev`):** one MinIO service; dlt writes objects (prefixes, not mkdir):

```text
s3://nexus-dlt-dbt-clickhouse-dev/
  route/products/dt=2026-08-18/run_id=local-20260818T175000Z/part-000.jsonl.gz
```

**dbt** — env is `--target` (`target.name`). ClickHouse `schema` in dbt is the **database**. Route staging uses `+schema: silver` → `silver_{env}`; peer tables `stg_route__products*`. Gold next.

- **`_route_sources.yml`:** `database: bronze_{{ target.name }}`, identifier `raw_route__products` (and nested peers).
- **`dbt_project.yml` `+schema`:** unsuffixed layer (`silver`, `gold`, `elementary`, …). `generate_schema_name` appends `_{{ target.name }}`. Do **not** also write `silver_{{ target.name }}` in `+schema`.

`dbt_project.yml` (fragment):

```yaml
models:
  nexus_clickhouse:
    staging:
      route:
        +schema: silver               # → silver_{{ target.name }}
    intermediate:
      +schema: intermediate           # → intermediate_{{ target.name }}
    gold:
      +schema: gold                   # → gold_{{ target.name }}
    marts:
      +schema: marts                  # → marts_{{ target.name }}
    published:
      +schema: published              # → published_{{ target.name }}
```

Staging: `silver_dev.stg_route__products` via `{{ source('route_raw', 'products') }}`. Gold only if a requirement **names** a model (for example `dim_product`). dlt ends at MinIO + Bronze; all post-Bronze work is dbt-only.

From the repo root:

```bash
set -a && source .env && source scripts/load-secrets.sh && set +a
export NEXUS_ENV=dev
unset NEXUS_RUN_ID   # leftover export overrides minting
export OTEL_EXPORTER_OTLP_ENDPOINT="${OTEL_EXPORTER_OTLP_ENDPOINT:-http://127.0.0.1:4317}"
./scripts/clickhouse-rbac-bootstrap.sh   # once per env
uv run python branches/dlt_dbt_clickhouse/dlt/route/products.py
# Optional: --run-id <id> for Airflow / replay / intentional dlt→dbt chain
cd branches/dlt_dbt_clickhouse
uv run dbt run --select stg_route__products+ --profiles-dir . --target "$NEXUS_ENV"
```

Pass the **same** `NEXUS_RUN_ID` (printed by the script, or `--run-id`) as `var('run_id')` when chaining.

`prd` later: same files, `NEXUS_ENV=prd` and `--target prd` → bucket `-prd`, databases `*_prd`.

---

## First pipeline status

| Layer | Status |
| --- | --- |
| dlt Route `products` (archive + Bronze + telemetry) | **Implemented** — `bronze_{env}.raw_route__products` as `nexus_loader` |
| ClickHouse RBAC (loader/transformer/reader/admin) | **Implemented** (dev) — [rbac.md](rbac.md), `./scripts/clickhouse-rbac-bootstrap.sh` |
| Silver `stg_route__products*` peer tables | **Implemented** (dev) — [dbt-modeling.md](dbt-modeling.md), [bronze-silver-cutover.md](bronze-silver-cutover.md) |
| Gold | `dim_product`, `brg_product_image`, `brg_product_subcategory` SCD2 — [gold-products-cutover.md](gold-products-cutover.md) |
| Airflow endpoint DAG | **Implemented** — `route_clickhouse_products` (host `uv` via SSH) |

Physical Bronze: `bronze_{env}.raw_route__products` (`dataset_table_separator=__`). RBAC: dlt=`nexus_loader`, dbt=`nexus_transformer`.

Facts, SCD2, marts, and `pub` only when the requirement needs them. No Spark or LLM in this slice.
