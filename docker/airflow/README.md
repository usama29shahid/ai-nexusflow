# Airflow image

Thin wrapper around `apache/airflow:3.3.2-python3.12` that adds the **docker CLI** so LocalExecutor tasks can `docker run` the ELT job image. Providers: `standard` (BashOperator), `amazon` (MinIO remote logs), `fab` (username/password login).

dlt/dbt stay in [`docker/elt/`](../elt/). Do not install the project `.venv` or ELT deps in this image.

Airflow 3 UI is `airflow api-server` (Compose service `airflow-api-server`). DAG parsing is `airflow dag-processor`.

Rebuild when the Dockerfile changes:

```bash
./scripts/start.sh airflow
```
