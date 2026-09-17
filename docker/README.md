# docker

Init scripts and image extras for Compose services. The Compose **file** stays at the repo root (`docker-compose.yml`). Optional stacks use **profiles** (`clickhouse`, `lakehouse`, `cloudbeaver`, `airflow`). MinIO is unprofiled.

ClickHouse and MinIO already run from the root file. Airflow image extras live in [`airflow/`](airflow/). Ephemeral ELT job image (dlt/dbt for Airflow tasks) lives in [`elt/`](elt/). Add SQL/bucket init here when needed.
