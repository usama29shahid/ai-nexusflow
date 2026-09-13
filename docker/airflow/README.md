# Airflow image

Thin wrapper around `apache/airflow:2.10.5-python3.12` that adds `openssh-client`.

dlt/dbt/`uv` stay on the **host**. DAG tasks SSH to the Docker host and run `./scripts/start.sh`. Do not install the project `.venv` in this image.

Rebuild when the Dockerfile changes:

```bash
docker compose --profile airflow up -d --build
```
