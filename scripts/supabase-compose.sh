#!/usr/bin/env bash
# Shared docker compose invocation for self-hosted Supabase under docker/supabase/.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUPABASE_DIR="${ROOT}/docker/supabase"
ENV_FILE="${ROOT}/.nexusflow/supabase.env"

# Drop every KEY from the env file out of this process. Compose prefers the
# shell over --env-file, so a leaked POSTGRES_PASSWORD (or any other Supabase
# key) would override .nexusflow/supabase.env. Do not source the file.
supabase_clear_env_file_overrides() {
  local env_file="$1"
  local line key
  [[ -f "${env_file}" ]] || return 0
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line%$'\r'}"
    line="${line#"${line%%[![:space:]]*}"}"
    [[ -z "${line}" || "${line}" == \#* ]] && continue
    if [[ "${line}" == export\ * ]]; then
      line="${line#export }"
      line="${line#"${line%%[![:space:]]*}"}"
    fi
    if [[ "${line}" =~ ^([A-Za-z_][A-Za-z0-9_]*)= ]]; then
      key="${BASH_REMATCH[1]}"
      unset "${key}"
    fi
  done < "${env_file}"
}

supabase_compose() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Missing ${ENV_FILE}. Run ./scripts/start.sh supabase first." >&2
    exit 1
  fi
  (
    cd "${SUPABASE_DIR}"
    supabase_clear_env_file_overrides "${ENV_FILE}"
    docker compose \
      --env-file "${ENV_FILE}" \
      -f docker-compose.yml \
      -f docker-compose.kong.yml \
      -f docker-compose.nexus.yml \
      "$@"
  )
}

supabase_slim_services=(db auth rest meta studio api-gw vector)
