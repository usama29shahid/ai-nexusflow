# dbt modeling — medallion + dimensional

dbt is the **transformation** layer. It reads Bronze via `source()`. It does not call REST APIs and does not write the MinIO archive.

The **DAG, prefixes, SCD, and folder grain** below apply to both warehouse and lakehouse capabilities. Physical names differ because ClickHouse is two-level and Iceberg is three-level.

Enhanced keys / soft-delete / SCD metadata patterns: [enhanced-modeling-strategy.md](enhanced-modeling-strategy.md) (**proposal only** — not active until accepted). Warehouse Bronze/silver implementation record: [bronze-silver-cutover.md](bronze-silver-cutover.md).

| | `dlt_dbt_clickhouse` | `dlt_dbt_spark_iceberg` |
| --- | --- | --- |
| Project | `branches/dlt_dbt_clickhouse` (`nexus_clickhouse`) | `branches/dlt_dbt_spark_iceberg` (`nexus_lakehouse`) |
| Adapter | dbt-clickhouse | dbt-spark |
| Bronze | `bronze_{env}.raw_{source}__{endpoint}` | `nexus_{env}.raw_{source}.table` |
| Staging | `silver_{env}.stg_{source}__{endpoint}` | schema `stg_{source}` in catalog `nexus_{env}` |
| Gold | `gold_{env}.dim_*` / `fct_*` / `evt_*` | schema `gold` in catalog `nexus_{env}` |
| Elementary | `elementary_{env}` | (lakehouse TBD) |

Lakehouse catalog/schema rules: [dlt-dbt-spark-iceberg.md](dlt-dbt-spark-iceberg.md). ClickHouse database rules: [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md). Env: [environments.md](environments.md). RBAC: [rbac.md](rbac.md).

Profile **target** = env (`NEXUS_ENV`, default `dev` until Terraform, later `prd`). One project per capability; do not fork the repo per env. Run with `--target "$NEXUS_ENV"` so dlt and dbt agree.

**Profile default database (ClickHouse):** in `profiles.example.yml`, each output hardcodes `schema: silver_dev` / `silver_prd` (the connection default / fallback). Do **not** derive profile `schema` from `NEXUS_ENV` — that can disagree with `--target`. Models with `+schema: silver` (and later `gold`, …) still resolve via `generate_schema_name` to `{layer}_{{ target.name }}`. Re-copy or edit local gitignored `profiles.yml` when the example changes.

**Where `{{ target.name }}` goes:**

- **ClickHouse:** into **layer database** names (`bronze_dev`, `silver_dev`, `gold_dev`, `elementary_dev`, …). In sources YAML, set `database: bronze_{{ target.name }}` and table `identifier: raw_route__products` (no env on the table). In `dbt_project.yml`, set `+schema` to the **unsuffixed** layer (`silver`, `gold`, `elementary`, …); `generate_schema_name` appends `_{{ target.name }}` → `silver_dev`. Do not put `_{{ target.name }}` in both places.
- **Iceberg / dbt-spark:** into the Polaris **catalog** only (`nexus_{{ target.name }}`). `+schema` stays `raw_{source}`, `stg_{source}`, `gold`, … — never `gold_{{ target.name }}`.

`source()` examples: [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md), [dlt-dbt-spark-iceberg.md](dlt-dbt-spark-iceberg.md).

Pass `var('run_id')` on every run (same value as dlt / `NEXUS_RUN_ID`). Until Airflow, that is the generated local `run_id`.

---

## Medallion and Kimball together

Medallion is **quality/ownership** of tables. Dimensional modeling is **grain** (entities, processes, activity). Use both. Do not treat medallion as a mandatory ladder of copies.

Typical path when the requirement needs it (warehouse ClickHouse):

```text
bronze_{env}.raw_{source}__{endpoint}   (Bronze, dlt)
  → silver_{env}.stg_{source}__{endpoint}
  → intermediate_{env}.int_*
  → gold_{env}  dim_* / fct_* / evt_*
  → intermediate_{env} domain int_*
  → marts_{env}.mart_*
  → published_{env}.pub_*            optional
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
stg_route__products   ──► int_product_keys ──► dim_product
stg_route__categories ──► int_category_keys ──► dim_category
stg_route__brands     ──► int_brand_keys ──► dim_brand
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

### Bronze (`bronze_{env}`, not dbt models)

dlt output e.g. `bronze_dev.raw_route__products`. Append-only **history of loads**. Shared `run_id` on every row. dbt `source()` these tables. Nested dlt children (`…__images`, `…__subcategory`) stay in Bronze with `_dlt_parent_id` → parent `_dlt_id`.

### Silver staging — speech “silver”, prefix `stg_*`

One staging model per Bronze resource where practical. Live in `models/staging/{source}/` → database **`silver_{env}`**. Table/alias: `stg_{source}__{endpoint}` (and peer nested resources).

**Bronze hierarchy vs silver peers:** Bronze names reflect dlt nesting. Silver has **no parent/child role** — every staged resource is a **peer table** (`materialized='table'`). Run together with shared tags (e.g. `tag:products`). Nested peers join Bronze parents via `_dlt_parent_id` and keep children of **winning** parent `_dlt_id`s after parent dedupe.

| Bronze | Silver |
| --- | --- |
| `raw_route__products` | `stg_route__products` |
| `raw_route__products__images` | `stg_route__products__images` |
| `raw_route__products__subcategory` | `stg_route__products__subcategory` |

dbt folder stays `models/staging/route/`.

#### FULL_LOAD silver (Route products today)

Each Bronze `run_id` is a full snapshot. Silver rebuilds **current** grain from a Bronze window, then dedupes by **`pk_hash`**. No custom scope macro; logic is inline in each model. Incremental / delta silver is **deferred**.

Bronze `WHERE` (same pattern on products Bronze for peer models):

1. `dbt run --full-refresh` → `flags.FULL_REFRESH` → all Bronze history (`run_id` / lookback ignored)  
2. Else if `var('run_id')` set → that load only  
3. Else → `_extracted_at >= now - lookback_days` (project default **15**)

Then `row_number() over (partition by pk_hash order by _extracted_at desc, _dlt_id desc) = 1`.

**Trusted vars (no Jinja allowlist in models):** validate at the edge — dlt CLI/`NEXUS_RUN_ID`, Airflow, or the operator — not inside silver SQL.

| Var | Contract |
| --- | --- |
| `run_id` | Same rules as dlt (`products.py`): non-empty, ≤128 chars, `^[A-Za-z0-9][A-Za-z0-9._:+-]*$`. Pass the Bronze load id you intend to pin. |
| `lookback_days` | Non-negative integer (default `15` in `dbt_project.yml`). |

Malformed vars can break the compiled SQL; that is acceptable for trusted local/CI/Airflow callers. Do not treat dbt `--vars` as an untrusted API.

| Rule | Silver FULL_LOAD | Gold and above |
| --- | --- | --- |
| Grain | Current keys after lookback + `pk_hash` dedupe | SCD / history / as-of as required |
| Materialization | **`table` only** (+ `copy_grants` where configured) | Incremental / SCD2 etc. as required |
| Soft-delete | Absent from newest snapshot in window → dropped | Yes when required |
| Engine RBAC | dlt=loader, dbt=transformer | Same users; reader for consumers |
| Keys | business key(s), `pk_hash`, `row_hash`, `ingestion_hash` via `dbt_utils.generate_surrogate_key` | Gold may extend |
| Dates | `source_created_at` / `source_updated_at`; `_extracted_at`; `_inserted_at` | Effective dates (`valid_from` / `valid_to`) only in Gold |
| Keep columns | `_dlt_id`, `_dlt_load_id`, nexus audit cols (do not carry duplicate source `_id` when it equals the business key) | — |

Hashes: MD5 via `dbt_utils.generate_surrogate_key`.  
`pk_hash` = hash of business key(s); `row_hash` = source attrs only; `ingestion_hash` = business key(s) + `run_id`.

Also:

- Rename, type, flatten JSON.
- Pass through `run_id` and business keys.
- No department metrics.
- No Bronze / dlt changes for this pattern.

### dbt YAML convention (two files per source folder)

| File | Contents |
| --- | --- |
| `_{source}_sources.yml` | sources only (Bronze tables, meta, column docs) |
| `_{source}_models.yml` | models, column docs, tests, unit_tests |

Always run `dbt docs generate` after run/test (OpenMetadata-compatible artifacts).

### Packages (day one, warehouse)

- `dbt-labs/dbt_utils` (required)
- `elementary-data/elementary` → `+schema: elementary` → `elementary_{env}`
- `calogica/dbt_expectations` (use when native tests insufficient)

### Shared intermediate — `int_*`

Reusable keys, standardization, grain fixes. Still not “sales’s version of customer.” ClickHouse database: `intermediate_{env}`.

### Conformed Gold

Shared across endpoints **by default**. Database: `gold_{env}`.

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

dbt **only**. No dlt pipeline. Wide or process-specific tables for a domain. Run with **dbt selectors**, not a new extract DAG. Database: `marts_{env}`.

### Published — `pub_*` (optional)

Stable names for BI/apps. Skip until a consumer needs a contract. Gold is already queryable. Database: `published_{env}`.

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

Same folders in both dbt projects. ClickHouse maps folders to **layer databases**; Iceberg maps them to **schemas** inside catalog `nexus_{env}`.

```text
models/
  staging/{source}/          CH: silver_{env}           Iceberg: nexus_{env}.stg_{source}
  intermediate/shared/       CH: intermediate_{env}     Iceberg: nexus_{env}.int
  gold/dims|facts|events     CH: gold_{env}             Iceberg: nexus_{env}.gold
  marts/{domain}/            CH: marts_{env}            Iceberg: nexus_{env}.marts
  published/                 CH: published_{env}        Iceberg: nexus_{env}.pub
```

Staging subfolders are REST **sources**. Gold subfolders are **grain** (not route/dataforseo).
