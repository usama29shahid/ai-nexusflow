#!/usr/bin/env bash
# Initialize / unseal HashiCorp Vault, seed KV secrets, configure AppRole for Agent.
# Idempotent for local dev. Run from repo root after: docker compose --profile vault up -d vault
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

NEXUS_DIR="${ROOT}/.nexusflow"
INIT_FILE="${NEXUS_DIR}/vault-init.json"
APPROLE_DIR="${NEXUS_DIR}/approle"
POLICY_NAME="nexusflow-agent"
APPROLE_NAME="nexusflow-agent"
VAULT_CONTAINER="${VAULT_CONTAINER:-vault}"

mkdir -p "${NEXUS_DIR}" "${APPROLE_DIR}"

# secrets.env: 640 (owner + group read). AppRole / init: admin-only (600 / 700).
fix_nexusflow_permissions() {
  local secrets_file="${1:-${NEXUS_SECRETS_FILE:-${NEXUS_DIR}/secrets.env}}"
  local owner_user owner_group
  owner_user="$(id -un)"
  if [[ -n "${NEXUS_SECRETS_GROUP:-}" ]]; then
    owner_group="${NEXUS_SECRETS_GROUP}"
  else
    owner_group="$(id -gn)"
  fi

  chmod 750 "${NEXUS_DIR}"
  chown "${owner_user}:${owner_group}" "${NEXUS_DIR}" 2>/dev/null || true

  chmod 700 "${APPROLE_DIR}"
  chown "${owner_user}:${owner_group}" "${APPROLE_DIR}" 2>/dev/null || true
  [[ -f "${NEXUS_DIR}/agent-autoauth.hcl" ]] && chmod 600 "${NEXUS_DIR}/agent-autoauth.hcl"
  [[ -f "${INIT_FILE}" ]] && chmod 600 "${INIT_FILE}"

  if [[ ! -f "${secrets_file}" ]]; then
    return 0
  fi

  local chown_ok=1
  if ! chown "${owner_user}:${owner_group}" "${secrets_file}" 2>/dev/null; then
    chown_ok=0
    echo "Could not chown ${secrets_file} (Agent may have written as root)." >&2
  fi

  if ! chmod 640 "${secrets_file}" 2>/dev/null; then
    echo "Could not chmod 640 ${secrets_file}." >&2
  fi

  if [[ ! -r "${secrets_file}" ]]; then
    echo "Bootstrap user $(id -un) cannot read ${secrets_file} — secrets injection will fail." >&2
    echo "  Admin: sudo chown ${owner_user}:${owner_group} ${secrets_file} && chmod 640 ${secrets_file}" >&2
    echo "  Then re-run: ./scripts/vault-bootstrap.sh" >&2
    return 1
  fi

  if [[ "${chown_ok}" -eq 0 ]]; then
    echo "Warning: ${secrets_file} is readable but ownership was not fixed." >&2
    echo "  For admin+dev (640 + shared group), run: sudo chown ${owner_user}:${owner_group} ${secrets_file}" >&2
  fi
}

if [[ ! -f .env ]]; then
  echo "Missing .env — copy from .env.example" >&2
  exit 1
fi

set -a
# shellcheck source=/dev/null
source .env
set +a

export NEXUS_ENV="${NEXUS_ENV:-dev}"

vault_status_json() {
  docker exec "${VAULT_CONTAINER}" wget -qO- \
    "http://127.0.0.1:8200/v1/sys/health?standbyok=true&sealedcode=200&uninitcode=200"
}

vault_exec() {
  docker exec -e VAULT_ADDR=http://127.0.0.1:8200 "${VAULT_CONTAINER}" vault "$@"
}

wait_for_vault() {
  local i
  for i in $(seq 1 60); do
    if docker exec "${VAULT_CONTAINER}" wget -q -O- \
      "http://127.0.0.1:8200/v1/sys/health?standbyok=true&sealedcode=200&uninitcode=200" \
      >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "Vault container '${VAULT_CONTAINER}' not reachable. Start it first:" >&2
  echo "  docker compose --profile vault up -d vault" >&2
  echo "  docker compose logs vault" >&2
  exit 1
}

read_env_default() {
  local key="$1"
  local fallback="${2:-}"
  local line
  line="$(grep -E "^${key}=" .env 2>/dev/null | tail -1 || true)"
  if [[ -n "${line}" ]]; then
    line="${line#*=}"
    line="${line%$'\r'}"
    printf '%s' "${line}"
  else
    printf '%s' "${fallback}"
  fi
}

generate_if_blank() {
  local key="$1"
  local generator="$2"
  local value
  value="$(read_env_default "${key}")"
  if [[ -z "${value}" ]]; then
    value="$(eval "${generator}")"
  fi
  printf '%s' "${value}"
}

kv_secret_exists() {
  vault_exec kv get -format=json "$1" >/dev/null 2>&1
}

echo "Waiting for Vault..."
wait_for_vault

initialized="$(vault_status_json | python3 -c 'import json,sys; print(json.load(sys.stdin).get("initialized", False))')"

if [[ "${initialized}" != "True" ]]; then
  echo "Initializing Vault (1 unseal key — local dev only; use multi-key on production VPS)..."
  vault_exec operator init \
    -key-shares=1 \
    -key-threshold=1 \
    -format=json > "${INIT_FILE}"
  chmod 600 "${INIT_FILE}"
  echo "Saved init output to ${INIT_FILE} (gitignored). Store a backup offline."
fi

unseal_key="$(python3 -c "import json; print(json.load(open('${INIT_FILE}'))['unseal_keys_b64'][0])")"
root_token="$(python3 -c "import json; print(json.load(open('${INIT_FILE}'))['root_token'])")"

sealed="$(vault_status_json | python3 -c 'import json,sys; print(json.load(sys.stdin).get("sealed", True))')"
if [[ "${sealed}" == "True" ]]; then
  echo "Unsealing Vault..."
  vault_exec operator unseal "${unseal_key}" >/dev/null
fi

vault_exec login "${root_token}" >/dev/null

if ! vault_exec secrets list -format=json | python3 -c "import json,sys; sys.exit(0 if 'secret/' in json.load(sys.stdin) else 1)"; then
  echo "Enabling KV v2 at secret/..."
  vault_exec secrets enable -path=secret kv-v2
fi

if ! vault_exec policy read "${POLICY_NAME}" >/dev/null 2>&1; then
  echo "Writing policy ${POLICY_NAME}..."
  docker exec -i -e VAULT_ADDR=http://127.0.0.1:8200 -e VAULT_TOKEN="${root_token}" \
    "${VAULT_CONTAINER}" vault policy write "${POLICY_NAME}" - \
    < "${ROOT}/docker/vault/policies/nexusflow-agent.hcl"
fi

if ! vault_exec auth list -format=json | python3 -c "import json,sys; sys.exit(0 if 'approle/' in json.load(sys.stdin) else 1)"; then
  echo "Enabling AppRole auth..."
  vault_exec auth enable approle
fi

if ! vault_exec read "auth/approle/role/${APPROLE_NAME}" >/dev/null 2>&1; then
  echo "Creating AppRole ${APPROLE_NAME}..."
  vault_exec write "auth/approle/role/${APPROLE_NAME}" \
    token_policies="${POLICY_NAME}" \
    token_ttl=24h \
    token_max_ttl=72h \
    secret_id_ttl=0 \
    secret_id_num_uses=0
fi

if [[ ! -f "${APPROLE_DIR}/role_id" ]]; then
  vault_exec read -field=role_id "auth/approle/role/${APPROLE_NAME}/role-id" > "${APPROLE_DIR}/role_id"
  chmod 600 "${APPROLE_DIR}/role_id"
fi

if [[ ! -f "${APPROLE_DIR}/secret_id" ]]; then
  vault_exec write -field=secret_id -force "auth/approle/role/${APPROLE_NAME}/secret-id" \
    > "${APPROLE_DIR}/secret_id"
  chmod 600 "${APPROLE_DIR}/secret_id"
fi

cat > "${NEXUS_DIR}/agent-autoauth.hcl" <<EOF
# Generated by vault-bootstrap.sh — gitignored. Do not commit.
auto_auth {
  method "approle" {
    config = {
      role_id_file_path   = "/nexusflow/approle/role_id"
      secret_id_file_path = "/nexusflow/approle/secret_id"
      remove_secret_id_file_after_reading = false
    }
  }

  sink "file" {
    config = {
      path = "/tmp/.vault-token"
      mode = 0600
    }
  }
}
EOF
chmod 600 "${NEXUS_DIR}/agent-autoauth.hcl"
chmod 700 "${APPROLE_DIR}"
chmod 600 "${APPROLE_DIR}/role_id" "${APPROLE_DIR}/secret_id"

kv_base="secret/nexusflow/${NEXUS_ENV}"
echo "Checking KV paths for NEXUS_ENV=${NEXUS_ENV}..."
if kv_secret_exists "${kv_base}/clickhouse"; then
  echo "  KV exists: ${kv_base}/clickhouse (skip seed)"
else
  echo "  Seeding: ${kv_base}/clickhouse"
  vault_exec kv put "${kv_base}/clickhouse" \
    password="$(read_env_default CLICKHOUSE_PASSWORD change-me)"
fi
if kv_secret_exists "${kv_base}/minio"; then
  echo "  KV exists: ${kv_base}/minio (skip seed)"
else
  echo "  Seeding: ${kv_base}/minio"
  vault_exec kv put "${kv_base}/minio" \
    root_user="$(read_env_default MINIO_ROOT_USER minioadmin)" \
    root_password="$(read_env_default MINIO_ROOT_PASSWORD minioadmin123)"
fi
if kv_secret_exists "${kv_base}/polaris"; then
  echo "  KV exists: ${kv_base}/polaris (skip seed)"
else
  echo "  Seeding: ${kv_base}/polaris"
  vault_exec kv put "${kv_base}/polaris" \
    client_secret="$(read_env_default POLARIS_CLIENT_SECRET s3cr3t)"
fi
if kv_secret_exists "${kv_base}/airflow"; then
  echo "  KV exists: ${kv_base}/airflow (skip seed)"
else
  echo "  Seeding: ${kv_base}/airflow"
  vault_exec kv put "${kv_base}/airflow" \
    fernet_key="$(generate_if_blank AIRFLOW__CORE__FERNET_KEY "python3 -c 'import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())'")" \
    web_secret="$(generate_if_blank AIRFLOW__WEBSERVER__SECRET_KEY "python3 -c 'import secrets; print(secrets.token_urlsafe(32))'")" \
    admin_password="$(read_env_default AIRFLOW_ADMIN_PASSWORD change-me)"
fi
if kv_secret_exists "${kv_base}/github"; then
  echo "  KV exists: ${kv_base}/github (skip seed)"
else
  echo "  Seeding: ${kv_base}/github"
  vault_exec kv put "${kv_base}/github" \
    token="$(read_env_default GITHUB_TOKEN placeholder-not-set)"
fi

echo "Starting Vault Agent..."
docker compose --profile vault up -d vault-agent

echo "Waiting for Agent-rendered secrets.env..."
secrets_file="${NEXUS_SECRETS_FILE:-${ROOT}/.nexusflow/secrets.env}"
for _ in $(seq 1 30); do
  if [[ -f "${secrets_file}" ]] && grep -q '^CLICKHOUSE_PASSWORD=' "${secrets_file}"; then
    fix_nexusflow_permissions "${secrets_file}"
    echo "Vault bootstrap OK."
    echo "  secrets file: ${secrets_file}"
    echo "  Next: source scripts/load-secrets.sh && docker compose up -d"
    exit 0
  fi
  sleep 2
done

echo "Timed out waiting for ${secrets_file}. Check: docker compose logs vault-agent" >&2
exit 1
