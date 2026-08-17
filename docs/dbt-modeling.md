# dbt modeling — medallion + dimensional (dlt_dbt_clickhouse)

dbt is the **transformation** layer on ClickHouse. It reads Bronze via `source()`. It does not call REST APIs and does not write the MinIO archive.

Project: `branches/dlt_dbt_clickhouse` (`nexus_dbt`). Profile **target** = env (`dev` until Terraform, later `prd`). One project; do not fork the repo per env. `+database` (ClickHouse database) = `{layer}_{target}` — `stg_dev`, `int_dev`, `gold_dev`, `marts_dev`. Sources read `raw_{env}`. See [environments.md](environments.md).

Pass `var('run_id')` on every run (same value as dlt). Until Airflow, that is the generated local `run_id`.

---

## Medallion and Kimball together

Medallion is **quality/ownership** of tables. Dimensional modeling is **grain** (entities, processes, activity). Use both. Do not treat medallion as a mandatory ladder of copies.

Typical path when the requirement needs it:

```text
raw_{env} (Bronze, dlt)
  → stg_{env}.stg_*
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
stg_pokeapi_pokemon ──► int_pokemon_keys ──► dim_pokemon
stg_github_repo     ──► int_repo_keys    ──► dim_repo
dim_pokemon ──► fct_pokemon_stat
dim_pokemon ──► mart_pokedex
int_pokemon_keys ──► int_pokedex_enrich ──► mart_pokedex
evt_github_push ──► mart_engineering
```

A domain mart may depend on a conformed dim, a fact, an event, or another `int_*`. An event does not have to become a periodic fact first.

**Do not skip ownership:** API JSON does not land in a mart. Domain fields do not get bolted onto a **shared** dim unless the requirement **names a separate dim**.

---

## Layers

### Bronze (`raw_{env}`, not dbt models)

dlt output in `raw_dev` (until Terraform). Append-only **history of loads**. Shared `run_id` on every row. dbt `source()` these tables.

### Silver staging — `stg_*`

One staging model per Bronze resource where practical.

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

## Folder sketch (when models exist)

Replace `models/example/` stubs at implementation time:

```text
models/
  staging/          stg_*
  intermediate/     shared int_*
  gold/
    dims/
    facts/
    events/
  domain/
    <domain>/int_/
    <domain>/marts/
  published/        optional
```
