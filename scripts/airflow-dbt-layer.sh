#!/usr/bin/env bash
# One dbt layer: run then test. Never dbt build.
# Invoked via ./scripts/start.sh so secrets and NEXUS_* are loaded.
# Usage: ./scripts/start.sh ./scripts/airflow-dbt-layer.sh 'tag:products,tag:staging'
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <dbt-select>" >&2
  exit 2
fi

select="$1"
run_id="${NEXUS_RUN_ID:?NEXUS_RUN_ID is required}"
target="${NEXUS_ENV:?NEXUS_ENV is required}"
project="branches/dlt_dbt_clickhouse"

uv run dbt run \
  --project-dir "${project}" \
  --profiles-dir "${project}" \
  --target "${target}" \
  --select "${select}" \
  --vars "{\"run_id\": \"${run_id}\"}"

# Do not pass run_id into dbt test. Silver FULL_LOAD uses var('run_id') to
# scope Bronze; unit-test fixtures use run_id r1 and would compile to 0 rows.
uv run dbt test \
  --project-dir "${project}" \
  --profiles-dir "${project}" \
  --target "${target}" \
  --select "${select}"
