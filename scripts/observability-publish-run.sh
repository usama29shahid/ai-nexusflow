#!/usr/bin/env bash
# Airflow (or manual) observability closer: lake summary + artifacts.
# Success path: dbt docs, edr report, then publish status=ok.
# Failure path (arg failed): skip docs/edr; publish airflow.dag.failed.
# Invoke via ./scripts/start.sh so secrets and NEXUS_RUN_ID are set.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

status="${1:-ok}"
if [[ "${status}" != "ok" && "${status}" != "failed" ]]; then
  echo "Usage: $0 [ok|failed]" >&2
  exit 2
fi

run_id="${NEXUS_RUN_ID:?NEXUS_RUN_ID is required}"
target="${NEXUS_ENV:?NEXUS_ENV is required}"
project="branches/dlt_dbt_clickhouse"

if [[ "${status}" == "ok" ]]; then
  uv run dbt docs generate \
    --project-dir "${project}" \
    --profiles-dir "${project}" \
    --target "${target}"

  if ! uv run edr --help >/dev/null 2>&1; then
    echo "edr is not installed. Run: uv sync --extra elementary" >&2
    exit 1
  fi

  uv run edr report \
    --profiles-dir "${project}" \
    --project-dir "${project}" \
    --profile-target "${target}" \
    --target-path "${ROOT}/edr_target" \
    --open-browser false \
    --disable-samples true
fi

export NEXUS_OBS_STATUS="${status}"
uv run python -c '
from pathlib import Path
import os
from common.observability.publish import publish_orchestrated_run

uploaded, summary = publish_orchestrated_run(
    Path("branches/dlt_dbt_clickhouse"),
    run_id=os.environ["NEXUS_RUN_ID"],
    dag_id=os.environ.get("NEXUS_DAG_ID"),
    status=os.environ["NEXUS_OBS_STATUS"],
)
if summary:
    print(f"Observability lake: {summary}")
for uri in uploaded:
    print(f"Observability lake: {uri}")
'
