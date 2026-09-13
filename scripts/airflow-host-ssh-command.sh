#!/usr/bin/env bash
# Forced sshd command for the Airflow host-exec key.
# The entire SSH_ORIGINAL_COMMAND must match: three NEXUS_* exports, one OTEL
# URL, cd to this repo, then an allowlisted ./scripts/start.sh remote.
# Test: SSH_ORIGINAL_COMMAND='…' "$0" --check
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cmd="${SSH_ORIGINAL_COMMAND:-}"

reject() {
  echo "nexus-airflow-ssh: $1" >&2
  exit 1
}

ere_escape() {
  printf '%s' "$1" | sed -e 's/[][\\.^$*+?(){}|]/\\&/g'
}

if [[ -z "${cmd}" ]]; then
  reject "empty SSH_ORIGINAL_COMMAND"
fi
if [[ "${cmd}" == *$'\n'* || "${cmd}" == *$'\r'* ]]; then
  reject "newlines are not allowed"
fi

root_ere="$(ere_escape "${ROOT}")"
otel_alt='http://127\.0\.0\.1:4317|http://localhost:4317|\$\{OTEL_EXPORTER_OTLP_ENDPOINT:-http://127\.0\.0\.1:4317\}'
shape="^export NEXUS_RUN_ID='[A-Za-z0-9][A-Za-z0-9._:+-]*' NEXUS_DAG_ID='[A-Za-z0-9_]+' NEXUS_TASK_ID='[A-Za-z0-9_]+' OTEL_EXPORTER_OTLP_ENDPOINT=(${otel_alt}); cd '${root_ere}' && ./scripts/start.sh (.+)$"

if [[ ! "${cmd}" =~ ${shape} ]]; then
  reject "command shape rejected"
fi

remote="${BASH_REMATCH[2]}"
ok=0
if [[ "${remote}" == "./scripts/assert-branch-enabled.sh dlt_dbt_clickhouse" ]]; then
  ok=1
elif [[ "${remote}" == "./scripts/observability-publish-run.sh" || "${remote}" == "./scripts/observability-publish-run.sh failed" ]]; then
  ok=1
elif [[ "${remote}" =~ ^./scripts/airflow-dbt-layer.sh\ \'[A-Za-z0-9_:,]+\'$ ]]; then
  ok=1
elif [[ "${remote}" =~ ^uv\ run\ python\ branches/dlt_dbt_clickhouse/dlt/[a-z0-9_]+/[a-z0-9_]+\.py\ --run-id\  ]]; then
  run_id="${remote##* --run-id }"
  run_id="${run_id#\'}"
  run_id="${run_id%\'}"
  run_id="${run_id#\"}"
  run_id="${run_id%\"}"
  if [[ "${run_id}" =~ ^[A-Za-z0-9][A-Za-z0-9._:+-]*$ ]]; then
    ok=1
  fi
fi

if [[ "${ok}" -ne 1 ]]; then
  reject "remote not allowlisted: ${remote}"
fi

if [[ "${1:-}" == "--check" ]]; then
  echo "ok"
  exit 0
fi

exec /bin/bash -c "${cmd}"
