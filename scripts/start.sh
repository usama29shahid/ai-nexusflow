#!/usr/bin/env bash
# Single entrypoint: load secrets, start infra by profile rules, run dlt/dbt.
#
# Profile model (see docs/setup.md, docs/vault.md):
#
#   Always (no profile)     MinIO — shared object store, independent of branches
#   Platform (independent)  vault, airflow, cloudbeaver — not tied to a branch
#   Branch stacks           clickhouse → dlt_dbt_clickhouse
#                           lakehouse  → dlt_dbt_spark_iceberg
#
# COMPOSE_PROFILES in .env controls branch (+ optional cloudbeaver/airflow).
# Vault starts separately when NEXUS_SECRETS_BACKEND=vault (not via branch profiles).
#
# Usage (from repo root):
#   ./scripts/start.sh                 # secrets + MinIO + branch profiles + Vault if needed
#   ./scripts/start.sh vault           # Vault only (platform)
#   ./scripts/start.sh airflow         # Airflow only (platform, on-demand)
#   ./scripts/start.sh minio           # MinIO only (always-on service)
#   ./scripts/start.sh smoke           # ClickHouse dlt smoke
#   ./scripts/start.sh dbt ...         # dbt with secrets loaded
#   ./scripts/start.sh shell           # interactive shell with secrets
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Profiles that map to execution branches (config/branches.yaml)
BRANCH_PROFILES="clickhouse lakehouse"
# Profiles for platform tooling (not a data branch)
PLATFORM_PROFILES="vault airflow cloudbeaver"

usage() {
  cat <<'EOF'
Usage: ./scripts/start.sh [command]

Infra (follows Compose profiles; MinIO / Vault / Airflow are branch-independent):

  (no args)     Load secrets → Vault if needed → MinIO + COMPOSE_PROFILES stacks
  all           Start every stack (both branches + cloudbeaver + airflow + vault)
  down          Stop all stacks (including vault + airflow; avoids network-in-use)
  minio         Start MinIO only (always-on shared store)
  vault         Start + bootstrap HashiCorp Vault (platform; secrets)
  airflow       Start Airflow profile only (platform; on-demand)

App (secrets loaded):

  smoke         Run tests/integration/dlt_clickhouse_smoke.py
  dbt <args>    uv run dbt <args>
  shell         Interactive bash with secrets exported
  help          This help

  Any other args run with secrets loaded, e.g.:
    ./scripts/start.sh uv run python branches/dlt_dbt_clickhouse/dlt/github/pull_requests.py

COMPOSE_PROFILES (.env) examples:
  clickhouse                  # warehouse branch only (+ MinIO always)
  lakehouse                   # lakehouse branch only (+ MinIO always)
  clickhouse,lakehouse        # both branches
  clickhouse,lakehouse,cloudbeaver
  clickhouse,airflow          # warehouse + Airflow (Airflow is not a branch)

Vault is started when NEXUS_SECRETS_BACKEND=vault — do not put vault in COMPOSE_PROFILES
just to enable secrets; start.sh handles it as platform infra.
EOF
}

profile_in_list() {
  local needle="$1"
  local haystack="$2"
  [[ ",${haystack}," == *",${needle},"* ]]
}

load_env() {
  chmod +x scripts/load-secrets.sh scripts/vault-bootstrap.sh 2>/dev/null || true

  if [[ ! -f "${ROOT}/.env" ]]; then
    echo "Missing ${ROOT}/.env — copy from .env.example" >&2
    exit 1
  fi

  # Source config first so we know the backend before requiring Agent output.
  set -a
  # shellcheck source=/dev/null
  source "${ROOT}/.env"
  set +a

  if [[ "${NEXUS_SECRETS_BACKEND:-env}" == "vault" ]]; then
    ensure_vault
  fi

  export COMPOSE_PROFILES="${COMPOSE_PROFILES:-clickhouse,lakehouse}"
  export NEXUS_ENV="${NEXUS_ENV:-dev}"
  if [[ -z "${NEXUS_RUN_ID:-}" ]]; then
    export NEXUS_RUN_ID="local-$(date -u +%Y%m%dT%H%M%SZ)"
  fi
}

# MinIO has no profile — always starts with compose (independent of branches).
ensure_minio() {
  echo "Starting MinIO (shared store; no profile)..."
  docker compose up -d minio minio-init
}

# Vault is platform infra, not a branch. Started with --profile vault only.
ensure_vault() {
  if [[ "${NEXUS_SECRETS_BACKEND:-env}" != "vault" ]]; then
    return 0
  fi
  echo "Starting Vault (platform secrets; independent of branches)..."
  docker compose --profile vault up -d vault
  chmod +x scripts/vault-bootstrap.sh
  ./scripts/vault-bootstrap.sh
  # shellcheck source=/dev/null
  source scripts/load-secrets.sh
}

# Airflow is platform orchestration, not a branch.
ensure_airflow() {
  echo "Starting Airflow (platform orchestration; independent of branches)..."
  docker compose --profile airflow up -d
}

# Start stacks declared in COMPOSE_PROFILES (branch + optional platform tooling).
# Vault is never required in COMPOSE_PROFILES; it is handled by ensure_vault.
start_profiles() {
  local profiles="${COMPOSE_PROFILES}"
  # Drop vault from COMPOSE_PROFILES if someone listed it — start via ensure_vault instead.
  local cleaned=""
  local p
  IFS=',' read -ra _parts <<< "${profiles}"
  for p in "${_parts[@]}"; do
    p="$(echo "${p}" | xargs)"
    [[ -z "${p}" || "${p}" == "vault" ]] && continue
    if [[ -n "${cleaned}" ]]; then
      cleaned="${cleaned},${p}"
    else
      cleaned="${p}"
    fi
  done
  export COMPOSE_PROFILES="${cleaned}"

  echo "Branch / optional profiles: COMPOSE_PROFILES=${COMPOSE_PROFILES:-"(none — MinIO only)"}"
  echo "  Branch stacks:   clickhouse | lakehouse"
  echo "  Platform (opt.): airflow | cloudbeaver  |  vault via NEXUS_SECRETS_BACKEND"
  echo "  Always:          MinIO"

  if [[ -n "${COMPOSE_PROFILES}" ]]; then
    docker compose up -d
  else
    ensure_minio
  fi
}

stop_all() {
  echo "Stopping all stacks (branch + platform + vault)..."
  # Every profile must be enabled on down — otherwise Compose leaves profiled services running.
  COMPOSE_PROFILES=clickhouse,lakehouse,cloudbeaver,airflow \
    docker compose \
      --profile vault \
      --profile clickhouse \
      --profile lakehouse \
      --profile cloudbeaver \
      --profile airflow \
      down
  echo "Stopped. Data volumes kept (no -v)."
}

maybe_lakehouse_restore() {
  if [[ ",${COMPOSE_PROFILES}," == *",lakehouse,"* ]]; then
    echo
    echo "Lakehouse profile active — restoring Polaris / Iceberg registrations..."
    chmod +x scripts/lakehouse-restore.sh
    ./scripts/lakehouse-restore.sh
  fi
}

cmd="${1:-}"

case "${cmd}" in
  help|-h|--help)
    usage
    exit 0
    ;;
  minio)
    load_env
    ensure_minio
    echo "MinIO up (API localhost:${MINIO_API_PORT:-9002}, console :${MINIO_CONSOLE_PORT:-9001})."
    ;;
  vault)
    if [[ ! -f .env ]]; then
      echo "Missing .env — copy from .env.example" >&2
      exit 1
    fi
    set -a
    # shellcheck source=/dev/null
    source .env
    set +a
    if [[ "${NEXUS_SECRETS_BACKEND:-env}" != "vault" ]]; then
      echo "Set NEXUS_SECRETS_BACKEND=vault in .env to use Vault." >&2
      exit 1
    fi
    ensure_vault
    echo "Vault ready (platform). Secrets: ${NEXUS_SECRETS_FILE:-.nexusflow/secrets.env}"
    ;;
  airflow)
    load_env
    ensure_minio
    ensure_airflow
    echo "Airflow up: http://127.0.0.1:${AIRFLOW_WEBSERVER_PORT:-8081}"
    ;;
  all)
    load_env
    export COMPOSE_PROFILES="clickhouse,lakehouse,cloudbeaver,airflow"
    start_profiles
    maybe_lakehouse_restore
    echo
    echo "Ready (all stacks)."
    echo "  Profiles: ${COMPOSE_PROFILES} (+ MinIO always)"
    echo "  Secrets:  NEXUS_SECRETS_BACKEND=${NEXUS_SECRETS_BACKEND:-env}"
    echo "  Next:     ./scripts/start.sh smoke"
    echo "            ./scripts/start.sh dbt debug --project-dir branches/dlt_dbt_clickhouse"
    ;;
  down)
    stop_all
    ;;
  "")
    load_env
    start_profiles
    echo
    echo "Ready."
    echo "  Profiles: ${COMPOSE_PROFILES:-none} (+ MinIO always)"
    echo "  Secrets:  NEXUS_SECRETS_BACKEND=${NEXUS_SECRETS_BACKEND:-env}"
    echo "  Next:     ./scripts/start.sh smoke"
    echo "            ./scripts/start.sh dbt debug --project-dir branches/dlt_dbt_clickhouse"
    echo "            ./scripts/start.sh airflow   # optional platform"
    ;;
  smoke)
    load_env
    echo "NEXUS_ENV=${NEXUS_ENV} NEXUS_RUN_ID=${NEXUS_RUN_ID}"
    uv run python tests/integration/dlt_clickhouse_smoke.py
    ;;
  dbt)
    shift
    load_env
    exec uv run dbt "$@"
    ;;
  shell)
    load_env
    echo "Secrets loaded. NEXUS_ENV=${NEXUS_ENV} NEXUS_RUN_ID=${NEXUS_RUN_ID}"
    echo "COMPOSE_PROFILES=${COMPOSE_PROFILES}"
    echo "Type exit when done."
    exec "${SHELL:-bash}" -i
    ;;
  *)
    load_env
    exec "$@"
    ;;
esac
