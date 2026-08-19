# minio/init

Creates capability buckets on the shared MinIO service (always runs after `minio` is healthy).

Buckets (for `NEXUS_ENV=dev`):

- `nexus-dlt-dbt-clickhouse-dev` — warehouse JSONL archive
- `nexus-dlt-dbt-spark-iceberg-archive-dev` — lakehouse JSONL archive
- `nexus-dlt-dbt-spark-iceberg-dev` — Iceberg warehouse (Polaris catalog `nexus_dev`)
- `nexus-airflow-logs-dev` — Airflow remote task logs (Phase 2)

Script: `create-buckets.sh` (mounted into the `minio-init` Compose service).
