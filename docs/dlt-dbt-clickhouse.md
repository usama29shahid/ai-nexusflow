# dlt_dbt_clickhouse — warehouse ELT

Public name: **dlt_dbt_clickhouse** (dlt → dbt → ClickHouse). This is the warehouse ELT **capability**, not a git branch.

The five-backend platform story lives in [architecture.md](architecture.md). Extraction: [dlt-extraction.md](dlt-extraction.md). Modeling: [dbt-modeling.md](dbt-modeling.md). Logs: [observability.md](observability.md). Env: [environments.md](environments.md).

dbt project: `branches/dlt_dbt_clickhouse`. Config key: `dlt_dbt_clickhouse` in [`config/branches.yaml`](../config/branches.yaml).

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

Until Airflow exists (Phase 2), the same path runs on the host with `uv run`. Generate **one `run_id` per local run** (`NEXUS_RUN_ID`) and pass it to **both** dlt and dbt. Later, Airflow supplies the DAG `run_id`. Env is **`NEXUS_ENV` (default `dev`) until Terraform**.

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
| `nexus-airflow-logs-dev` | Phase 2 Airflow remote task logs. Not data. |

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

Examples of `{source}`: `pokeapi`, `dataforseo`, `github`. `{endpoint}` is the REST resource. `{param_variant}` is used only when the **payload contract** differs, not for every id in a URL.

Archive objects are **immutable**. Format: **JSONL** (compressed). Do not put Iceberg on this archive.

**Replay:** read the prefix, load Bronze as a **new `run_id` (append)**, then `dbt run`. Do not mutate archive objects. Do not delete prior Bronze rows.

---

## ClickHouse databases

ClickHouse has **no schemas** (only `database.table`). **Hybrid:** per-source databases for landing (raw/stg); **shared** databases for int, gold, marts, pub.

Do **not** create `gold_github_dev`. Shared Conformed Gold cannot live inside a source database.

Until Terraform, `env=dev`.

```text
raw_{source}_{env}     raw_github_dev.repos
stg_{source}_{env}     stg_github_dev.stg_github_repos
int_{env}              int_dev.int_repo_keys
gold_{env}             gold_dev.dim_repo
marts_{env}            marts_dev.mart_engineering
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

Gold table names are **conformed** (`dim_repo`, not `github_dim_repo`) unless the requirement explicitly names a separate dim.

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

Staging splits by **API**. Gold splits by **grain** (dims/facts/events), not by github/pokeapi. See [dbt-modeling.md](dbt-modeling.md).

---

## Pipelines: dlt unit vs Gold

A **dlt pipeline** is per REST **endpoint** (and per `{param}` only when schema/grain/auth/incremental **contract** differs). Same path, same schema, different id → one parameterized pipeline, not two Gold tables.

A **source** (pokeapi, github, …) groups those endpoint pipelines. Airflow later: **one DAG per source**, tasks per endpoint, then **one dbt run with selectors**.

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

**Until Airflow (Phase 2):** generate one id per local invocation — `local-{utc_timestamp}` or a UUID. Set `NEXUS_RUN_ID` (or equivalent) and pass the **same** value into dlt (Bronze column) and dbt (`var('run_id')`). Do **not** reuse a single eternal string like `"default"` on every load — Bronze is append-only history.

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

## Worked example: GitHub `pipe_one`

Illustration of the rules above. Pipelines are **not implemented yet**. Lakehouse copy of the same API: [dlt-dbt-spark-iceberg.md](dlt-dbt-spark-iceberg.md).

Assumptions: source GitHub, endpoint `pull_request/{param1}`, job name `pipe_one`. `{param1}` is a URL id with the **same** payload contract → one parameterized pipeline, not a `{param_variant}` prefix and not a new Gold table.

**Three names** ([environments.md](environments.md)):

```text
Job     pipe_one
Table   pull_request
Bucket  nexus-dlt-dbt-clickhouse-{env}     # all warehouse JSONL for this env
Prefix  github/pull_request/dt=.../run_id=.../part-*.jsonl.gz
Bronze  raw_github_{env}.pull_request
```

Do not name the ClickHouse database or MinIO bucket `pipe_one`. dlt dataset = `raw_github_{env}`, not the job name.

**Archive (`NEXUS_ENV=dev`):** one MinIO service; dlt writes objects (prefixes, not mkdir):

```text
s3://nexus-dlt-dbt-clickhouse-dev/
  github/pull_request/dt=2026-08-18/run_id=local-20260818T175000Z/part-000.jsonl.gz
```

**dbt** — env is `--target` (`target.name`). ClickHouse `schema` in dbt is the **database**. Interpolate env into database names. If `+schema` cannot use `target.name` in `dbt_project.yml`, a `generate_schema_name` macro does the same.

`models/staging/github/sources.yml` (proposed):

```yaml
version: 2
sources:
  - name: github_raw
    database: raw_github_{{ target.name }}
    schema: raw_github_{{ target.name }}
    tables:
      - name: pull_request
```

`dbt_project.yml` (proposed fragment):

```yaml
models:
  nexus_dbt:
    staging:
      github:
        +schema: stg_github_{{ target.name }}
    intermediate:
      +schema: int_{{ target.name }}
    gold:
      +schema: gold_{{ target.name }}
    marts:
      +schema: marts_{{ target.name }}
    published:
      +schema: pub_{{ target.name }}
```

Staging: `stg_github_dev.stg_github_pull_request` via `{{ source('github_raw', 'pull_request') }}`. Gold only if a requirement **names** a model.

From the repo root (when code exists):

```bash
export NEXUS_ENV=dev
export NEXUS_RUN_ID=local-$(date -u +%Y%m%dT%H%M%SZ)
uv run python branches/dlt_dbt_clickhouse/dlt/github/pipe_one.py
uv run dbt run --project-dir branches/dlt_dbt_clickhouse --target "$NEXUS_ENV" \
  --vars "{\"run_id\": \"$NEXUS_RUN_ID\"}"
```

`prd` later: same files, `NEXUS_ENV=prd` and `--target prd` → bucket `-prd`, databases `*_prd`.

---

## First pipeline (implementation later)

Working path: the example above (or one similar REST source) → dlt → MinIO `nexus-dlt-dbt-clickhouse-dev` + ClickHouse `raw_{source}_dev` → dbt `--target dev`. Facts, SCD2, marts, and `pub` only when the requirement needs them. No Spark, Databricks, Airflow, or LLM in that slice.
