#!/usr/bin/env bash
# Fast Vault path for daily use: start Vault, unseal if sealed, ensure Agent, verify secrets.env.
# Falls back to vault-bootstrap.sh when Vault is not initialized or secrets are missing.
# Secrets still come only from Agent-rendered .nexusflow/secrets.env — never from .env passwords.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

NEXUS_DIR="${ROOT}/.nexusflow"
INIT_FILE="${NEXUS_DIR}/vault-init.json"
APPROLE_DIR="${NEXUS_DIR}/approle"
VAULT_CONTAINER="${VAULT_CONTAINER:-vault}"

if [[ ! -f .env ]]; then
  echo "Missing .env — copy from .env.example" >&2
  exit 1
fi

set -a
# shellcheck source=/dev/null
source .env
set +a

if [[ "${NEXUS_SECRETS_BACKEND:-env}" != "vault" ]]; then
  exit 0
fi

secrets_file="${NEXUS_SECRETS_FILE:-${NEXUS_DIR}/secrets.env}"

vault_status_json() {
  docker exec "${VAULT_CONTAINER}" wget -qO- \
    "http://127.0.0.1:8200/v1/sys/health?standbyok=true&sealedcode=200&uninitcode=200"
}

vault_exec() {
  docker exec -e VAULT_ADDR=http://127.0.0.1:8200 "${VAULT_CONTAINER}" vault "$@"
}

wait_for_vault() {
  local attempts="${1:-30}"
  local i
  for i in $(seq 1 "${attempts}"); do
    if docker exec "${VAULT_CONTAINER}" wget -q -O- \
      "http://127.0.0.1:8200/v1/sys/health?standbyok=true&sealedcode=200&uninitcode=200" \
      >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "Vault container '${VAULT_CONTAINER}' not reachable." >&2
  echo "  docker compose --profile vault up -d vault" >&2
  echo "  docker compose logs vault" >&2
  exit 1
}

secrets_file_ready() {
  [[ -f "${secrets_file}" && -r "${secrets_file}" ]] \
    && grep -q '^CLICKHOUSE_PASSWORD=' "${secrets_file}" \
    && grep -q '^MINIO_ROOT_USER=' "${secrets_file}"
}

vault_agent_running() {
  docker compose --profile vault ps vault-agent --status running -q 2>/dev/null | grep -q .
}

vault_unseal_if_needed() {
  if [[ ! -f "${INIT_FILE}" ]]; then
    return 1
  fi

  local sealed unseal_key
  sealed="$(vault_status_json | python3 -c 'import json,sys; print(json.load(sys.stdin).get("sealed", True))')"
  if [[ "${sealed}" != "True" ]]; then
    return 0
  fi

  echo "Unsealing Vault..."
  unseal_key="$(python3 -c "import json; print(json.load(open('${INIT_FILE}'))['unseal_keys_b64'][0])")"
  vault_exec operator unseal "${unseal_key}" >/dev/null
}

wait_for_secrets_file() {
  local attempts="${1:-15}"
  local i
  for i in $(seq 1 "${attempts}"); do
    if secrets_file_ready; then
      return 0
    fi
    sleep 1
  done
  return 1
}

needs_full_bootstrap() {
  local initialized
  initialized="$(vault_status_json | python3 -c 'import json,sys; print(json.load(sys.stdin).get("initialized", False))')"
  [[ "${initialized}" != "True" ]] && return 0
  [[ ! -f "${INIT_FILE}" ]] && return 0
  [[ ! -f "${APPROLE_DIR}/role_id" || ! -f "${APPROLE_DIR}/secret_id" ]] && return 0
  [[ ! -f "${NEXUS_DIR}/agent-autoauth.hcl" ]] && return 0
  return 1
}

run_full_bootstrap() {
  echo "Vault needs bootstrap (first run or missing Agent credentials)..."
  chmod +x scripts/vault-bootstrap.sh
  exec ./scripts/vault-bootstrap.sh
}

echo "Ensuring Vault secrets (fast path)..."
docker compose --profile vault up -d vault
wait_for_vault 30

if needs_full_bootstrap; then
  run_full_bootstrap
fi

if ! vault_unseal_if_needed; then
  run_full_bootstrap
fi

if secrets_file_ready; then
  if ! vault_agent_running; then
    echo "Starting Vault Agent..."
    docker compose --profile vault up -d vault-agent
    wait_for_secrets_file 10 || true
  fi
  exit 0
fi

echo "Starting Vault Agent..."
docker compose --profile vault up -d vault-agent

if wait_for_secrets_file 30; then
  exit 0
fi

run_full_bootstrap
