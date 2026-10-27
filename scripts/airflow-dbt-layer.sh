#!/usr/bin/env bash
# One dbt layer: run then test. Never dbt build.
# Invoked via ./scripts/start.sh so secrets and NEXUS_* are loaded.
# Usage: ./scripts/start.sh ./scripts/airflow-dbt-layer.sh 'tag:products,tag:staging'
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Names from package-lock.yml whose dbt_packages/<name>/dbt_project.yml is absent.
# Empty output means the install is complete. A missing lock prints "package-lock.yml".
missing_dbt_package_names() {
  local project="$1"
  PROJECT_DIR="${project}" python3 -c '
import os
from pathlib import Path

project = Path(os.environ["PROJECT_DIR"])
lock = project / "package-lock.yml"
if not lock.is_file():
    print("package-lock.yml")
    raise SystemExit(0)
names = []
for line in lock.read_text(encoding="utf-8").splitlines():
    stripped = line.strip()
    if stripped.startswith("- name:"):
        names.append(stripped.split(":", 1)[1].strip())
missing = [
    name
    for name in names
    if not (project / "dbt_packages" / name / "dbt_project.yml").is_file()
]
print(" ".join(missing))
'
}

# Install only when the on-disk packages are incomplete. A healthy tree skips the hub.
# dbt deps deletes dbt_packages/, so the lock file lives outside that directory.
_ensure_dbt_packages() {
  local project="$1"
  local missing
  missing="$(missing_dbt_package_names "${project}")"
  if [[ -z "${missing}" ]]; then
    return 0
  fi
  echo "dbt packages incomplete (${missing}); running dbt deps" >&2
  uv run dbt deps --project-dir "${project}"
  missing="$(missing_dbt_package_names "${project}")"
  if [[ -n "${missing}" ]]; then
    echo "dbt deps did not restore ${missing} under ${project}/dbt_packages/" >&2
    exit 1
  fi
}

ensure_dbt_packages() {
  local project="$1"
  local lock_dir="${ROOT}/.nexusflow"
  mkdir -p "${lock_dir}"
  (
    flock 9
    _ensure_dbt_packages "${project}"
  ) 9>"${lock_dir}/dbt-deps.lock"
}

if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  return 0
fi

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <dbt-select>" >&2
  exit 2
fi

select="$1"
run_id="${NEXUS_RUN_ID:?NEXUS_RUN_ID is required}"
target="${NEXUS_ENV:?NEXUS_ENV is required}"
project="branches/dlt_dbt_clickhouse"

ensure_dbt_packages "${project}"

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
