# docker

Init scripts and image extras for Compose services. The Compose **file** stays at the repo root (`docker-compose.yml`). Optional stacks use **profiles** (`clickhouse`, later `lakehouse`, `airflow`). MinIO is unprofiled.

ClickHouse and MinIO already run from the root file. Add SQL/bucket init here when needed.
