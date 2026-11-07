#!/usr/bin/env bash
# Fill empty Vault supabase* fields from .nexusflow/supabase.env (+ rbac env).
# Safe no-op when Vault is down or vault-init.json is missing.
# Recreates vault-agent when any field was written so secrets.env picks up keys.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

NEXUS_DIR="${ROOT}/.nexusflow"
INIT_FILE="${NEXUS_DIR}/vault-init.json"
VAULT_CONTAINER="${VAULT_CONTAINER:-vault}"

if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${ROOT}/.env"
  set +a
fi
NEXUS_ENV="${NEXUS_ENV:-dev}"
kv_base="secret/nexusflow/${NEXUS_ENV}"

if ! docker inspect "${VAULT_CONTAINER}" >/dev/null 2>&1; then
  echo "Vault container not running; skip supabase Vault sync."
  exit 0
fi
if [[ ! -f "${INIT_FILE}" ]]; then
  echo "Missing ${INIT_FILE}; skip supabase Vault sync."
  exit 0
fi
if [[ ! -f "${NEXUS_DIR}/supabase.env" ]]; then
  echo "Missing ${NEXUS_DIR}/supabase.env; skip supabase Vault sync."
  exit 0
fi

root_token="$(python3 - "${INIT_FILE}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text())
token = data.get("root_token") or ""
if not token:
    sys.exit(1)
print(token)
PY
)" || {
  echo "Could not read root_token from ${INIT_FILE}; skip supabase Vault sync." >&2
  exit 0
}

vault_exec() {
  docker exec \
    -e VAULT_ADDR=http://127.0.0.1:8200 \
    -e VAULT_TOKEN="${root_token}" \
    "${VAULT_CONTAINER}" vault "$@"
}

# shellcheck source=scripts/supabase-vault-seed.sh
source "${ROOT}/scripts/supabase-vault-seed.sh"

echo "Syncing Supabase secrets into Vault from .nexusflow/supabase.env..."
SUPABASE_VAULT_CHANGED=0
seed_supabase_api
seed_supabase_role "${kv_base}/supabase_loader" nexus_loader SUPABASE_LOADER_USER SUPABASE_LOADER_PASSWORD
seed_supabase_role "${kv_base}/supabase_reader" nexus_reader SUPABASE_READER_USER SUPABASE_READER_PASSWORD
seed_supabase_role "${kv_base}/supabase_catalog" nexus_catalog SUPABASE_CATALOG_USER SUPABASE_CATALOG_PASSWORD
seed_supabase_role "${kv_base}/supabase_admin" nexus_admin SUPABASE_ADMIN_USER SUPABASE_ADMIN_PASSWORD

if [[ "${SUPABASE_VAULT_CHANGED}" != "1" ]]; then
  echo "Supabase Vault secrets already populated."
  exit 0
fi

echo "Recreating vault-agent so secrets.env picks up filled Supabase keys..."
docker compose --profile vault up -d --no-deps --force-recreate vault-agent

secrets_file="${NEXUS_SECRETS_FILE:-${NEXUS_DIR}/secrets.env}"
for _ in $(seq 1 30); do
  if [[ -f "${secrets_file}" ]] && grep -q '^SUPABASE_ANON_KEY=.\+' "${secrets_file}" 2>/dev/null; then
    echo "Supabase Vault sync OK (${secrets_file})."
    exit 0
  fi
  sleep 1
done
echo "Vault Agent recreated; waiting for SUPABASE_ANON_KEY in ${secrets_file} timed out (check docker compose logs vault-agent)." >&2
exit 1
