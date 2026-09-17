# Airflow image

Thin wrapper around `apache/airflow:2.10.5-python3.12` that adds the **docker CLI** so LocalExecutor tasks can `docker run` the ELT job image.

dlt/dbt stay in [`docker/elt/`](../elt/). Do not install the project `.venv` or ELT deps in this image.

Rebuild when the Dockerfile changes:

```bash
docker compose --profile airflow up -d --build
```
