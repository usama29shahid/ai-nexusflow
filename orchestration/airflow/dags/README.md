# dags

Airflow DAG Python files. Mounted into the Airflow containers at `/opt/airflow/dags`.

One DAG per source + target + endpoint. Group folders by source+target. Filename is the endpoint. `dag_id` is `{folder}_{endpoint}` (for example `route_clickhouse_products`).

| DAG | File | Purpose |
| --- | --- | --- |
| `nexus_airflow_smoke` | `nexus_airflow_smoke.py` | Compose profile smoke (in-container) |
| `route_clickhouse_products` | `route_clickhouse/products.py` | Route products warehouse ELT |
| `route_clickhouse_categories` | `route_clickhouse/categories.py` | Route categories warehouse ELT |
| `route_clickhouse_brands` | `route_clickhouse/brands.py` | Route brands warehouse ELT |
| `route_clickhouse_subcategories` | `route_clickhouse/subcategories.py` | Route subcategories warehouse ELT. Triggers `route_clickhouse_categories` and waits before Bronze so the silver `category_id` relationship test has a current parent table |
| `observability_openmetadata_ingest` | `observability_openmetadata_ingest.py` | Daily OM reader ingest plus glossary and metric upsert (`governance` tag) |
| `ops_backup_archive` | `ops_backup_archive.py` | Daily MinIO archive → R2 mirror |

`nexus_elt_exec.py` is a helper (not a DAG): wraps `docker run` of `nexus-elt`. Copy that pattern for the next endpoint.

Do not add stub DAGs for endpoints that have no dlt script yet.
