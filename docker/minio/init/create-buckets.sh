#!/bin/sh
# Creates MinIO buckets for both capabilities (env=dev until Terraform).
set -eu

MINIO_USER="${MINIO_ROOT_USER:-minioadmin}"
MINIO_PASS="${MINIO_ROOT_PASSWORD:-minioadmin123}"
NEXUS_ENV="${NEXUS_ENV:-dev}"

until mc alias set nexus "http://minio:9000" "$MINIO_USER" "$MINIO_PASS"; do
  echo "waiting for MinIO..."
  sleep 2
done

# Warehouse capability archive
mc mb --ignore-existing "nexus/nexus-dlt-dbt-clickhouse-${NEXUS_ENV}"

# Lakehouse capability archive + Iceberg warehouse
mc mb --ignore-existing "nexus/nexus-dlt-dbt-spark-iceberg-archive-${NEXUS_ENV}"
mc mb --ignore-existing "nexus/nexus-dlt-dbt-spark-iceberg-${NEXUS_ENV}"

# Phase 1 Airflow remote task logs (not data)
mc mb --ignore-existing "nexus/nexus-airflow-logs-${NEXUS_ENV}"

# Observability data lake (OTel batches, events, dbt artifacts, run summaries)
mc mb --ignore-existing "nexus/nexus-telemetry-${NEXUS_ENV}"

echo "MinIO buckets:"
mc ls nexus/
