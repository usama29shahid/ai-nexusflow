# dbt modeling — medallion + dimensional

dbt is the **transformation** layer. It reads Bronze via `source()`. It does not call REST APIs and does not write the MinIO archive.

The **DAG, prefixes, SCD, and folder grain** below apply to both warehouse and lakehouse capabilities. Physical names differ because ClickHouse is two-level and Iceberg is three-level.

Enhanced keys / soft-delete / SCD metadata patterns: [enhanced-modeling-strategy.md](enhanced-modeling-strategy.md) (**proposal only** — not active until accepted).

| | `dlt_dbt_clickhouse` | `dlt_dbt_spark_iceberg` |
| --- | --- | --- |
| Project | `branches/dlt_dbt_clickhouse` (`nexus_clickhouse`) | `branches/dlt_dbt_spark_iceberg` (`nexus_lakehouse`) |
| Adapter | dbt-clickhouse | dbt-spark |
| Bronze | `raw_{source}_{env}.table` | `nexus_{env}.raw_{source}.table` |
| Staging | database `stg_{source}_{env}` | schema `stg_{source}` in catalog `nexus_{env}` |
| Gold | database `gold_{env}` | schema `gold` in catalog `nexus_{env}` |

Lakehouse catalog/schema rules: [dlt-dbt-spark-iceberg.md](dlt-dbt-spark-iceberg.md). ClickHouse database rules: [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md). Env: [environments.md](environments.md).

Profile **target** = env (`NEXUS_ENV`, default `dev` until Terraform, later `prd`). One project per capability; do not fork the repo per env. Run with `--target "$NEXUS_ENV"`.

**Where `{{ target.name }}` goes:**

- **ClickHouse:** into **database** names (`raw_route_dev`, `stg_route_dev`, `gold_dev`, …). In `sources.yml`, write the suffix with Jinja (`raw_route_{{ target.name }}`). In `dbt_project.yml`, set `+schema` to the **unsuffixed** name (`stg_route`, `gold`, …); `generate_schema_name` appends `_{{ target.name }}`. Do not put `_{{ target.name }}` in both places.
- **Iceberg / dbt-spark:** into the Polaris **catalog** only (`nexus_{{ target.name }}`). `+schema` stays `raw_{source}`, `stg_{source}`, `gold`, … — never `gold_{{ target.name }}`.

`source()` examples: [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md), [dlt-dbt-spark-iceberg.md](dlt-dbt-spark-iceberg.md).

Pass `var('run_id')` on every run (same value as dlt / `NEXUS_RUN_ID`). Until Airflow, that is the generated local `run_id`.

---

## Medallion and Kimball together

Medallion is **quality/ownership** of tables. Dimensional modeling is **grain** (entities, processes, activity). Use both. Do not treat medallion as a mandatory ladder of copies.

Typical path when the requirement needs it:

```text
raw_{source}_{env} (Bronze, dlt)
  → stg_{source}_{env}.stg_*
  → int_{env}.int_*
  → gold_{env}  dim_* / fct_* / evt_*
  → int_{env} domain int_*
  → marts_{env}.mart_*
  → pub_{env}.pub_*            optional
```

This is a **DAG**. A model `ref()`s what it needs. Steps depend on the requirement. Skip a layer when there is nothing to do there.

### Ladder (do not require)

```text
every table must go
Bronze → stg → int → gold dim → gold fact → domain int → mart → published
```

That forces empty models and forbids a mart from reading a dimension directly.

### DAG (required)

```text
stg_route_products   ──► int_product_keys ──► dim_product
stg_route_categories ──► int_category_keys ──► dim_category
stg_route_brands     ──► int_brand_keys ──► dim_brand
dim_product ──► fct_product_snapshot
dim_product ──► mart_product_performance
int_product_keys ──► int_catalog_enrich ──► mart_product_performance
# Later secondary source (example) can also feed shared Gold without touching Route staging:
# stg_dataforseo_* ──► … ──► same gold_{env} / marts_{env}
```

A domain mart may depend on a conformed dim, a fact, an event, or another `int_*`. An event does not have to become a periodic fact first.

**Do not skip ownership:** API JSON does not land in a mart. Domain fields do not get bolted onto a **shared** dim unless the requirement **names a separate dim**.

Enhanced SCD / soft-delete / hash-key patterns: [enhanced-modeling-strategy.md](enhanced-modeling-strategy.md) (proposal only).

---

## Layers

### Bronze (`raw_{source}_{env}`, not dbt models)

dlt output e.g. `raw_route_dev` (until Terraform). Append-only **history of loads**. Shared `run_id` on every row. dbt `source()` these tables.

### Silver staging — `stg_*`

One staging model per Bronze resource where practical. Live in `models/staging/{source}/` → database `stg_{source}_{env}`.

- Rename, type, flatten JSON.
- Light dedupe / null handling.
- Pass through `run_id` and business keys.
- No department metrics.

### Shared intermediate — `int_*`

Reusable keys, standardization, grain fixes. Still not “sales’s version of customer.”

### Conformed Gold

Shared across endpoints **by default**.

| Type | Role |
| --- | --- |
| **`dim_*`** | Entities. SCD1 if history is irrelevant. SCD2 if you must answer “as of that day.” |
| **`fct_*`** | Measured processes at a declared grain, keyed to dims. |
| **`evt_*`** | Append-only activity. ClickHouse’s natural fit. Do not force every event into a periodic fact. |

**Separate dim only when the requirement names it:**

```text
url/v1/{param1} + "create dim_any_name1" → dim_any_name1
url/v1/{param2} + "create dim_any_name2" → dim_any_name2
otherwise both feed one dim_name
```

Do not create `dim_*` per URL. Do not widen a shared dim for one team’s attribute — use a domain `int_*`, satellite, or mart.

Prefer **natural or hashed keys** over serial surrogates.

**SCD2 on ClickHouse:** insert-only (`valid_from`, `valid_to`, `is_current`). Do not rely on classic dbt snapshots. Add SCD2 only when the requirement needs history.

Facts and SCD2 are **not** required on every source. Entities + events are enough when that is the grain.

### Domain intermediate — `int_*` (domain)

Business rules that **read** Gold or other ints. Department-specific.

### Domain marts — `mart_*`

dbt **only**. No dlt pipeline. Wide or process-specific tables for a domain. Run with **dbt selectors**, not a new extract DAG.

### Published — `pub_*` (optional)

Stable names for BI/apps. Skip until a consumer needs a contract. Gold is already queryable.

---

## Incremental and “current” vs as-of

Bronze keeps **all** loads. Staging/Gold incremental models typically:

- Take the latest `run_id` (or max `_extracted_at`) per business key for “current,” or
- Build as-of logic explicitly for SCD2 / historical replay.

Replay of an old archive = **new** `run_id` appended to Bronze, then dbt. Prior loads remain.

---

## Tests (quality)

For now: **dbt tests** (not null, unique, relationships, accepted values) plus dlt load info. No separate DQ platform. Test grain and keys on Gold; test typing on `stg_*`.

---

## Selectors (Airflow later)

One dbt invocation per **source** DAG, with selectors for models downstream of that source’s `stg_*` (including shared Gold those models update, and marts if requested). Domain-only runs: selector on `marts` without running dlt.

---

## Folder layout

Same folders in both dbt projects. ClickHouse maps folders to **databases**; Iceberg maps them to **schemas** inside catalog `nexus_{env}`.

```text
models/
  staging/{source}/          CH: stg_{source}_{env}     Iceberg: nexus_{env}.stg_{source}
  intermediate/shared/       CH: int_{env}              Iceberg: nexus_{env}.int
  gold/dims|facts|events     CH: gold_{env}             Iceberg: nexus_{env}.gold
  marts/{domain}/            CH: marts_{env}            Iceberg: nexus_{env}.marts
  published/                 CH: pub_{env} optional     Iceberg: nexus_{env}.pub
```

Staging subfolders are REST **sources**. Gold subfolders are **grain** (not route/dataforseo). Leave `models/example/` on the warehouse project until the first real source.
