# dags

Airflow DAG Python files. Mounted into the Airflow containers at `/opt/airflow/dags`.

One DAG per source + target + endpoint. Group folders by source+target. Filename is the endpoint. `dag_id` is `{folder}_{endpoint}` (for example `route_clickhouse_products`).

| DAG | File | Purpose |
| --- | --- | --- |
| `nexus_airflow_smoke` | `nexus_airflow_smoke.py` | Compose profile smoke (in-container) |
| `route_clickhouse_products` | `route_clickhouse/products.py` | Route products warehouse ELT |

`nexus_elt_exec.py` is a helper (not a DAG): wraps `docker run` of `nexus-elt`. Copy that pattern for the next endpoint.

Do not add stub DAGs for endpoints that have no dlt script yet.
