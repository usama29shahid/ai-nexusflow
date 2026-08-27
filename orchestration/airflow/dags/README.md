# dags

Airflow DAG Python files. Mounted into the Airflow containers at `/opt/airflow/dags`.

| DAG | Purpose |
| --- | --- |
| `nexus_airflow_smoke` | Manual smoke test for the Compose `airflow` profile |

Source / branch ELT DAGs (one DAG per source, endpoint tasks, dbt selectors) come later. Do not invent speculative pipeline DAGs here.
