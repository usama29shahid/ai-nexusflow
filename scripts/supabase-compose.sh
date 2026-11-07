#!/usr/bin/env bash
# Shared docker compose invocation for self-hosted Supabase under docker/supabase/.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUPABASE_DIR="${ROOT}/docker/supabase"
ENV_FILE="${ROOT}/.nexusflow/supabase.env"

supabase_compose() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Missing ${ENV_FILE}. Run ./scripts/start.sh supabase first." >&2
    exit 1
  fi
  (
    cd "${SUPABASE_DIR}"
    docker compose \
      --env-file "${ENV_FILE}" \
      -f docker-compose.yml \
      -f docker-compose.kong.yml \
      -f docker-compose.nexus.yml \
      "$@"
  )
}

supabase_slim_services=(db auth rest meta studio api-gw vector)
