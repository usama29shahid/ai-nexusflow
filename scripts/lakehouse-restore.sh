#!/usr/bin/env bash
# After `docker compose down` + `up`, Polaris loses in-memory catalog metadata.
# Iceberg files stay in MinIO. This script re-bootstraps Polaris and re-registers
# the smoke table so Trino/Spark/dbt can query raw_dlt_smoke.smoke again.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env at repo root." >&2
  exit 1
fi

set -a
# shellcheck source=/dev/null
source .env
set +a

NEXUS_ENV="${NEXUS_ENV:-dev}"
POLARIS_CATALOG="nexus_${NEXUS_ENV}"

wait_healthy() {
  local service="$1"
  local attempts="${2:-60}"
  local delay="${3:-2}"
  for _ in $(seq 1 "${attempts}"); do
    if docker compose ps "${service}" 2>/dev/null | grep -q "(healthy)"; then
      return 0
    fi
    sleep "${delay}"
  done
  echo "Timed out waiting for ${service} to become healthy." >&2
  return 1
}

echo "Recreating polaris-setup (Polaris catalog + namespaces)..."
docker compose --profile lakehouse up -d --force-recreate polaris-setup

echo "Waiting for polaris-setup..."
wait_healthy polaris-setup 60 2

echo "Ensuring spark-thrift is up (dbt-spark)..."
docker compose --profile lakehouse up -d spark-thrift
wait_healthy spark-thrift 60 5

echo "Re-registering Iceberg smoke table from MinIO..."
uv run python tests/integration/register_lakehouse_smoke.py

echo "Waiting for Trino to accept queries (can take ~60s after compose up)..."
ready=0
for _ in $(seq 1 36); do
  if docker exec trino trino --catalog "${POLARIS_CATALOG}" --execute "SELECT 1" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 5
done
if [[ "${ready}" != "1" ]]; then
  echo "Trino did not become ready. Wait a minute, then run:" >&2
  echo "  docker exec trino trino --catalog ${POLARIS_CATALOG} --execute \"SELECT id, name, run_id FROM raw_dlt_smoke.smoke ORDER BY id\"" >&2
  exit 1
fi

echo "Querying raw_dlt_smoke.smoke..."
docker exec trino trino --catalog "${POLARIS_CATALOG}" --execute \
  "SELECT id, name, run_id FROM raw_dlt_smoke.smoke ORDER BY id"
