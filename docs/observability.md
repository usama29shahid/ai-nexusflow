# Observability and logging

Do **not** build a custom logging platform. Three concerns stay separate.

| Concern | Owner | Where it lives |
| --- | --- | --- |
| Did the DAG/task run? duration, retries, stdout | **Airflow** (Phase 2) | Airflow metadata DB + **remote task logs** in MinIO `nexus-airflow-logs-{env}` (default `-dev`) |
| Did extract/load succeed? packages, schema, row counts | **dlt** | Console until Airflow; `_dlt_*` tables in ClickHouse; stdout captured as Airflow task logs later |
| Did transforms and tests succeed? | **dbt** | `target/run_results.json` and artifacts; stdout as Airflow task logs later |
| Which rows came from which run? | **data** | `run_id` on Bronze, carried in dbt where needed |

Until Phase 2: host `uv run` + dlt/dbt native logs.

After Airflow: **Airflow is the operational log**. Enable **remote logging** to MinIO. dlt and dbt do not need a sidecar log shipper.

Optional later: copy dbt artifacts to object storage for retention. Not required for Milestone 1.

Do **not**: a logging microservice, a ClickHouse “log table” as the system of record for task success, or duplicating Airflow in application code.

---

## Airflow DAG grain (Phase 2)

**One DAG per source** (pokeapi, github, …):

1. Task(s) per endpoint dlt pipeline (archive + Bronze).
2. One `dbt run` / `dbt test` with **selectors** for downstream models.

Not one DAG per REST URL (DAG explosion). Domain marts: dbt selector only, or a dbt-only DAG, still no extra extract.

The future LLM workflow agent should emit this shape.

---

## Run id

Until Airflow: generate `local-{utc_timestamp}` (or UUID); pass the **same** value to dlt and dbt `var('run_id')`. After Airflow: DAG `run_id`. See [dlt-dbt-clickhouse.md](dlt-dbt-clickhouse.md).

---

## MinIO buckets (logs vs data)

| Bucket | Contents |
| --- | --- |
| `nexus-dlt-dbt-clickhouse-dev` | Raw API JSONL — **data archive**, not logs |
| `nexus-dlt-dbt-spark-iceberg-archive-dev` | Lakehouse JSONL archive — **data**, not logs |
| `nexus-dlt-dbt-spark-iceberg-dev` | Iceberg warehouse — **data**, not logs |
| `nexus-airflow-logs-dev` | Airflow task logs — **ops**, not table data |

`prd` suffixes after Terraform. See [environments.md](environments.md).
