#!/usr/bin/env bash
# Single entrypoint: load secrets, start infra by profile rules, run dlt/dbt.
#
# Profile model (see docs/setup.md, docs/vault.md):
#
#   Always (no profile)     MinIO + otel-collector — shared store + telemetry gateway
#                           Independent of branches (same always-on model)
#   Platform (independent)  vault, airflow, cloudbeaver, signoz, openmetadata
#   Branch stacks           clickhouse → dlt_dbt_clickhouse
#                           lakehouse  → dlt_dbt_spark_iceberg
#
# COMPOSE_PROFILES in .env controls branch (+ optional platform tooling).
# Vault starts separately when NEXUS_SECRETS_BACKEND=vault (not via branch profiles).
#
# Usage (from repo root):
#   ./scripts/start.sh                 # secrets + MinIO/OTel + branch profiles + Vault if needed
#   ./scripts/start.sh vault           # Vault only (platform)
#   ./scripts/start.sh airflow         # Airflow only (platform, on-demand)
#   ./scripts/start.sh proxy           # Caddy edge proxy (*.NEXUS_PUBLIC_HOST)
#   ./scripts/start.sh signoz          # SigNoz reader (platform, on-demand)
#   ./scripts/start.sh openmetadata    # OpenMetadata reader (platform, on-demand)
#   ./scripts/start.sh observability   # MinIO + OTel + SigNoz + OpenMetadata readers
#   ./scripts/start.sh stop-signoz       # stop SigNoz reader; OTel → lake only
#   ./scripts/start.sh stop-openmetadata # stop OpenMetadata reader
#   ./scripts/start.sh stop-observability # stop both readers
#   ./scripts/start.sh smoke           # ClickHouse dlt smoke
#   ./scripts/start.sh dbt ...         # dbt with secrets loaded
#   ./scripts/start.sh shell           # interactive shell with secrets
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"
# Host uv may live outside a login shell PATH (CI / non-interactive).
export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"

# Profiles that map to execution branches (config/branches.yaml)
BRANCH_PROFILES="clickhouse lakehouse"
# Profiles for platform tooling (not a data branch)
PLATFORM_PROFILES="vault airflow cloudbeaver signoz openmetadata proxy"

usage() {
  cat <<'EOF'
Usage: ./scripts/start.sh [command]

Infra (follows Compose profiles; MinIO + OTel / Vault / Airflow are branch-independent):

  (no args)     Load secrets → Vault if needed → MinIO + OTel + COMPOSE_PROFILES stacks
  all           Start every stack (both branches + cloudbeaver + airflow + vault)
  down          Stop all stacks (including vault + airflow; avoids network-in-use)
  minio         Start MinIO + OTel Collector only (always-on shared infra)
  vault         Start + bootstrap HashiCorp Vault (platform; secrets)
  airflow       Start Airflow profile only (platform; on-demand)
  proxy         Start Caddy edge proxy (http://*.NEXUS_PUBLIC_HOST)
  signoz        Start SigNoz reader profile (trace UI)
  openmetadata  Start OpenMetadata reader profile (data catalog)
  observability Start shared infra + SigNoz + OpenMetadata readers
  observability-smoke  Run scripts/observability-smoke.sh
  stop-signoz        Stop SigNoz reader; revert OTel to lake-only export
  stop-openmetadata  Stop OpenMetadata reader
  stop-observability Stop SigNoz + OpenMetadata readers

App (secrets loaded):

  smoke         Run tests/integration/dlt_clickhouse_smoke.py
  dbt <args>    uv run dbt <args>
  shell         Interactive bash with secrets exported
  help          This help

  Any other args run with secrets loaded, e.g.:
    ./scripts/start.sh uv run python branches/dlt_dbt_clickhouse/dlt/route/products.py

COMPOSE_PROFILES (.env) examples:
  clickhouse                  # warehouse branch only (+ MinIO + OTel always)
  lakehouse                   # lakehouse branch only (+ MinIO + OTel always)
  clickhouse,lakehouse        # both branches
  clickhouse,lakehouse,cloudbeaver
  clickhouse,airflow          # warehouse + Airflow (Airflow is not a branch)

Vault is started when NEXUS_SECRETS_BACKEND=vault — do not put vault in COMPOSE_PROFILES
just to enable secrets; start.sh handles it as platform infra.

With vault backend, passwords come only from Agent-rendered secrets.env (via load_secrets).
stop-openmetadata loads .env config only; stop-signoz loads secrets too (recreates otel-collector).
EOF
}

profile_in_list() {
  local needle="$1"
  local haystack="$2"
  [[ ",${haystack}," == *",${needle},"* ]]
}

dbt_project_dir_from_args() {
  local args=("$@")
  local i arg
  for i in "${!args[@]}"; do
    arg="${args[$i]}"
    if [[ "${arg}" == "--project-dir" && $((i + 1)) -lt ${#args[@]} ]]; then
      echo "${args[$((i + 1))]}"
      return 0
    fi
    if [[ "${arg}" == --project-dir=* ]]; then
      echo "${arg#--project-dir=}"
      return 0
    fi
  done
  return 1
}

load_env() {
  chmod +x scripts/load-secrets.sh scripts/vault-bootstrap.sh scripts/vault-ensure.sh 2>/dev/null || true

  if [[ ! -f "${ROOT}/.env" ]]; then
    echo "Missing ${ROOT}/.env — copy from .env.example" >&2
    exit 1
  fi

  # Config only — passwords/tokens live in Vault KV when NEXUS_SECRETS_BACKEND=vault.
  set -a
  # shellcheck source=/dev/null
  source "${ROOT}/.env"
  set +a

  export COMPOSE_PROFILES="${COMPOSE_PROFILES:-clickhouse,lakehouse}"
  export NEXUS_ENV="${NEXUS_ENV:-dev}"
  if [[ -z "${NEXUS_RUN_ID:-}" ]]; then
    export NEXUS_RUN_ID="local-$(date -u +%Y%m%dT%H%M%SZ)"
  fi

  # Backend host publishes (ClickHouse/MinIO/Polaris/Spark/Trino).
  # Fail before compose up (Caddy entrypoint also rejects; this avoids publishing first).
  # shellcheck source=scripts/nexus_publish_bind.sh
  source "${ROOT}/scripts/nexus_publish_bind.sh"
  nexus_resolve_publish_bind || exit 1
}

# Source Agent-rendered secrets.env when backend is vault. Call only when a command needs credentials.
load_secrets() {
  if [[ "${NEXUS_SECRETS_BACKEND:-env}" != "vault" ]]; then
    return 0
  fi
  ./scripts/vault-ensure.sh
  set -a
  # shellcheck source=/dev/null
  source scripts/load-secrets.sh
  set +a
}

load_env_and_secrets() {
  load_env
  load_secrets
}

# Shared infra has no Compose profile — always on, independent of branches.
# MinIO = object store; otel-collector = telemetry gateway → nexus-telemetry-{env}.
signoz_is_running() {
  docker compose --profile signoz ps signoz --status running -q 2>/dev/null | grep -q .
}

sync_otel_collector_config() {
  local config="collector-config.yaml"
  if signoz_is_running; then
    config="collector-config.signoz.yaml"
  fi
  export OTEL_COLLECTOR_CONFIG="${config}"
  echo "Syncing otel-collector (${config})..."
  docker compose up -d --force-recreate otel-collector
}

ensure_shared_infra() {
  echo "Starting shared infra (MinIO AIStor Free + otel-collector; no profile)..."
  # shellcheck source=scripts/minio_license.sh
  source "${ROOT}/scripts/minio_license.sh"
  require_minio_license || exit 1
  docker compose up -d minio minio-init
  sync_otel_collector_config
}

# Alias used by platform entrypoints (airflow, signoz, …).
ensure_minio() {
  ensure_shared_infra
}

# Vault is platform infra, not a branch. Full bootstrap for explicit `vault` command.
ensure_vault() {
  if [[ "${NEXUS_SECRETS_BACKEND:-env}" != "vault" ]]; then
    return 0
  fi
  echo "Starting Vault (platform secrets; independent of branches)..."
  docker compose --profile vault up -d vault
  chmod +x scripts/vault-bootstrap.sh
  ./scripts/vault-bootstrap.sh
  set -a
  # shellcheck source=/dev/null
  source scripts/load-secrets.sh
  set +a
}

# Airflow is platform orchestration, not a branch.
require_airflow_elt_ready() {
  local repo="${NEXUS_REPO_ROOT:-}"
  if [[ -z "${repo}" ]]; then
    echo "Set NEXUS_REPO_ROOT in .env to the absolute clone path (host path for docker run -v)." >&2
    echo "Example: NEXUS_REPO_ROOT=${ROOT}" >&2
    exit 1
  fi
  if [[ ! -d "${repo}" ]]; then
    echo "NEXUS_REPO_ROOT does not exist: ${repo}" >&2
    exit 1
  fi
  chmod +x scripts/airflow-write-elt-env.sh
  ./scripts/airflow-write-elt-env.sh
  local sock="${DOCKER_SOCK:-/var/run/docker.sock}"
  if [[ ! -S "${sock}" ]]; then
    echo "Docker socket not found at ${sock}. Set DOCKER_SOCK if your daemon uses another path." >&2
    exit 1
  fi
  if [[ -z "${DOCKER_GID:-}" ]]; then
    export DOCKER_GID
    DOCKER_GID="$(stat -c '%g' "${sock}" 2>/dev/null || echo 0)"
  fi
  # Match the Compose project network (directory name by default: ai-nexusflow_default).
  if [[ -z "${NEXUS_COMPOSE_NETWORK:-}" ]]; then
    local project
    project="$(docker compose config --format json 2>/dev/null \
      | python3 -c 'import json,sys; print(json.load(sys.stdin).get("name") or "")' 2>/dev/null || true)"
    if [[ -z "${project}" ]]; then
      project="$(basename "${ROOT}")"
    fi
    export NEXUS_COMPOSE_NETWORK="${project}_default"
  fi
  export NEXUS_ELT_IMAGE="${NEXUS_ELT_IMAGE:-nexus-elt:latest}"
}

build_nexus_elt_image() {
  local image="${NEXUS_ELT_IMAGE:-nexus-elt:latest}"
  echo "Building ELT job image (${image})..."
  docker build -f docker/elt/Dockerfile -t "${image}" .
}

ensure_airflow() {
  echo "Starting Airflow 3.3 (platform orchestration; ELT via nexus-elt job image)..."
  if [[ "${NEXUS_SECRETS_BACKEND:-env}" != "vault" ]] && [[ -f .env ]]; then
    if ! grep -q '^AIRFLOW__API_AUTH__JWT_SECRET=.\+' .env; then
      local jwt
      jwt="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
      if grep -q '^AIRFLOW__API_AUTH__JWT_SECRET=' .env; then
        sed -i "s|^AIRFLOW__API_AUTH__JWT_SECRET=.*|AIRFLOW__API_AUTH__JWT_SECRET=${jwt}|" .env
      else
        printf '\nAIRFLOW__API_AUTH__JWT_SECRET=%s\n' "${jwt}" >> .env
      fi
      echo "Generated AIRFLOW__API_AUTH__JWT_SECRET in .env"
      set -a
      # shellcheck source=/dev/null
      source .env
      set +a
    fi
  fi
  require_airflow_elt_ready
  build_nexus_elt_image
  # Airflow 3 renamed webserver → api-server. A leftover 2.x container holds :8081.
  if docker inspect airflow-webserver >/dev/null 2>&1; then
    echo "Removing leftover Airflow 2 container airflow-webserver (frees :8081)..."
    docker rm -f airflow-webserver
  fi
  docker compose --profile airflow up -d --build
}

ensure_proxy() {
  echo "Starting Caddy edge proxy (profile proxy)..."
  echo "  Host: ${NEXUS_CADDY_SITE_SCHEME:-http://}*.${NEXUS_PUBLIC_HOST:-localhost.com}"
  echo "  Hosts: ./scripts/proxy-hosts.sh install   # required for *.localhost.com"
  docker compose --profile proxy up -d
}

ensure_signoz() {
  echo "Starting SigNoz reader (profile signoz)..."
  docker compose --profile signoz up -d signoz
  sync_otel_collector_config
}

ensure_openmetadata() {
  echo "Starting OpenMetadata reader (profile openmetadata)..."
  docker compose --profile openmetadata up -d
}

stop_signoz() {
  echo "Stopping SigNoz reader..."
  docker compose --profile signoz stop signoz 2>/dev/null || true
  docker compose --profile signoz rm -f signoz 2>/dev/null || true
  sync_otel_collector_config
}

stop_openmetadata() {
  echo "Stopping OpenMetadata reader..."
  docker compose --profile openmetadata down
}

stop_observability_readers() {
  stop_signoz
  stop_openmetadata
}

ensure_observability_readers() {
  ensure_minio
  ensure_signoz
  ensure_openmetadata
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

  echo "Branch / optional profiles: COMPOSE_PROFILES=${COMPOSE_PROFILES:-"(none — shared infra only)"}"
  echo "  Branch stacks:   clickhouse | lakehouse"
  echo "  Platform (opt.): airflow | cloudbeaver | signoz | openmetadata | vault via NEXUS_SECRETS_BACKEND"
  echo "  Always:          MinIO, otel-collector"

  # Always bring shared infra up first (explicit; not only via compose no-profile side effect).
  ensure_shared_infra

  if [[ ",${COMPOSE_PROFILES}," == *",airflow,"* ]]; then
    require_airflow_elt_ready
    build_nexus_elt_image
  fi

  if [[ -n "${COMPOSE_PROFILES}" ]]; then
    # Rebuild when Airflow is in the profile set so docker/airflow/Dockerfile
    # changes (docker CLI) are not skipped by a stale nexus-airflow image.
    if [[ ",${COMPOSE_PROFILES}," == *",airflow,"* ]]; then
      docker compose up -d --build
    else
      docker compose up -d
    fi
  fi

  # proxy is optional platform; start when listed in COMPOSE_PROFILES
  if [[ ",${COMPOSE_PROFILES}," == *",proxy,"* ]]; then
    ensure_proxy
  fi
}

stop_all() {
  echo "Stopping all stacks (branch + platform + vault)..."
  # Every profile must be enabled on down — otherwise Compose leaves profiled services running.
  COMPOSE_PROFILES=clickhouse,lakehouse,cloudbeaver,airflow,signoz,openmetadata,openmetadata-ingestion,proxy \
    docker compose \
      --profile vault \
      --profile clickhouse \
      --profile lakehouse \
      --profile cloudbeaver \
      --profile airflow \
      --profile signoz \
      --profile openmetadata \
      --profile openmetadata-ingestion \
      --profile proxy \
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
    load_env_and_secrets
    ensure_shared_infra
    echo "Shared infra up."
    echo "  MinIO API:       localhost:${MINIO_API_PORT:-9002}"
    echo "  MinIO console:   http://127.0.0.1:${MINIO_CONSOLE_PORT:-9001}"
    echo "  OTel Collector:  gRPC :${OTEL_GRPC_PORT:-4317}, HTTP :${OTEL_HTTP_PORT:-4318}, health :${OTEL_HEALTH_PORT:-13133}"
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
    load_env_and_secrets
    ensure_minio
    ensure_airflow
    echo "Airflow up: http://127.0.0.1:${AIRFLOW_WEBSERVER_PORT:-8081}"
    if [[ -n "${NEXUS_PUBLIC_HOST:-}" ]]; then
      echo "  Via proxy (if up): ${AIRFLOW__API__BASE_URL:-${AIRFLOW__WEBSERVER__BASE_URL:-http://airflow.${NEXUS_PUBLIC_HOST}}}"
    fi
    ;;
  proxy)
    load_env
    ensure_minio
    ensure_proxy
    echo "Caddy up on :${NEXUS_PROXY_HTTP_PORT:-80}"
    echo "  Examples: http://airflow.${NEXUS_PUBLIC_HOST:-localhost.com}"
    echo "            http://minio.${NEXUS_PUBLIC_HOST:-localhost.com}"
    echo "  Hosts:    ./scripts/proxy-hosts.sh install"
    ;;
  signoz)
    load_env_and_secrets
    ensure_minio
    ensure_signoz
    echo "SigNoz up: http://127.0.0.1:${SIGNOZ_UI_PORT:-3301}"
    ;;
  openmetadata)
    load_env_and_secrets
    ensure_minio
    ensure_openmetadata
    echo "OpenMetadata up: http://127.0.0.1:${OPENMETADATA_SERVER_PORT:-8585}"
    echo "  Login: admin@open-metadata.org / admin"
    ;;
  observability)
    load_env_and_secrets
    ensure_observability_readers
    echo "Observability readers up."
    echo "  SigNoz:        http://127.0.0.1:${SIGNOZ_UI_PORT:-3301}"
    echo "  OpenMetadata:  http://127.0.0.1:${OPENMETADATA_SERVER_PORT:-8585}"
    echo "  OTel gateway:  http://127.0.0.1:${OTEL_HTTP_PORT:-4318} (HTTP), :${OTEL_GRPC_PORT:-4317} (gRPC)"
    ;;
  observability-smoke)
    load_env_and_secrets
    chmod +x scripts/observability-smoke.sh
    exec ./scripts/observability-smoke.sh
    ;;
  stop-signoz)
    load_env_and_secrets
    stop_signoz
    echo "SigNoz stopped. OTel collector exports to lake only."
    ;;
  stop-openmetadata)
    load_env
    stop_openmetadata
    echo "OpenMetadata stopped."
    ;;
  stop-observability)
    load_env_and_secrets
    stop_observability_readers
    echo "Observability readers stopped. OTel collector exports to lake only."
    ;;
  all)
    load_env_and_secrets
    export COMPOSE_PROFILES="clickhouse,lakehouse,cloudbeaver,airflow"
    start_profiles
    maybe_lakehouse_restore
    echo
    echo "Ready (all stacks)."
    echo "  Profiles: ${COMPOSE_PROFILES} (+ MinIO + OTel always)"
    echo "  Secrets:  NEXUS_SECRETS_BACKEND=${NEXUS_SECRETS_BACKEND:-env}"
    echo "  Next:     ./scripts/start.sh smoke"
    echo "            ./scripts/start.sh dbt debug --project-dir branches/dlt_dbt_clickhouse"
    ;;
  down)
    stop_all
    ;;
  "")
    load_env_and_secrets
    start_profiles
    echo
    echo "Ready."
    echo "  Profiles: ${COMPOSE_PROFILES:-none} (+ MinIO + OTel always)"
    echo "  Secrets:  NEXUS_SECRETS_BACKEND=${NEXUS_SECRETS_BACKEND:-env}"
    echo "  Next:     ./scripts/start.sh smoke"
    echo "            ./scripts/start.sh dbt debug --project-dir branches/dlt_dbt_clickhouse"
    echo "            ./scripts/start.sh airflow   # optional platform"
    ;;
  smoke)
    load_env_and_secrets
    echo "NEXUS_ENV=${NEXUS_ENV} NEXUS_RUN_ID=${NEXUS_RUN_ID}"
    uv run python tests/integration/dlt_clickhouse_smoke.py
    ;;
  dbt)
    shift
    load_env_and_secrets
    dbt_project_dir="$(dbt_project_dir_from_args "$@" || true)"
    if [[ -n "${dbt_project_dir}" ]]; then
      export NEXUS_DBT_PROJECT_DIR="${dbt_project_dir}"
    fi
    set +e
    uv run dbt "$@"
    dbt_exit=$?
    set -e
    NEXUS_DBT_EXIT_CODE="${dbt_exit}" uv run python -m common.observability.publish || true
    exit "${dbt_exit}"
    ;;
  shell)
    load_env_and_secrets
    echo "Secrets loaded. NEXUS_ENV=${NEXUS_ENV} NEXUS_RUN_ID=${NEXUS_RUN_ID}"
    echo "COMPOSE_PROFILES=${COMPOSE_PROFILES}"
    echo "Type exit when done."
    exec "${SHELL:-bash}" -i
    ;;
  *)
    load_env_and_secrets
    exec "$@"
    ;;
esac
