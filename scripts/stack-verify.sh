#!/usr/bin/env bash
# Host health check for local Compose profiles. Prints PASS / FAIL / SKIP.
# Does not start, stop, or repair services.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Missing .env — copy from .env.example" >&2
  exit 1
fi

set -a
# shellcheck source=/dev/null
source .env
set +a

CLICKHOUSE_HTTP_PORT="${CLICKHOUSE_HTTP_PORT:-8123}"
OTEL_HEALTH_PORT="${OTEL_HEALTH_PORT:-13133}"
AIRFLOW_WEBSERVER_PORT="${AIRFLOW_WEBSERVER_PORT:-8081}"
SIGNOZ_UI_PORT="${SIGNOZ_UI_PORT:-3301}"
OPENMETADATA_ADMIN_PORT="${OPENMETADATA_ADMIN_PORT:-8586}"
POLARIS_MGMT_PORT="${POLARIS_MGMT_PORT:-8182}"
SPARK_THRIFT_PORT="${SPARK_THRIFT_PORT:-10000}"
TRINO_PORT="${TRINO_PORT:-8080}"
VAULT_PORT="${VAULT_PORT:-8200}"
CLOUDBEAVER_PORT="${CLOUDBEAVER_PORT:-8978}"
COMPOSE_PROFILES="${COMPOSE_PROFILES:-}"
NEXUS_SECRETS_BACKEND="${NEXUS_SECRETS_BACKEND:-env}"

pass=0
fail=0
skip=0

inspect_field() {
  local format="$1"
  local name="$2"
  local fallback="$3"
  local out
  if ! out="$(docker inspect -f "${format}" "${name}" 2>/dev/null)"; then
    echo "${fallback}"
    return 0
  fi
  printf '%s\n' "${out}"
}

container_status() {
  inspect_field '{{.State.Status}}' "$1" missing
}

container_health() {
  inspect_field '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$1" missing
}

container_exit() {
  inspect_field '{{.State.ExitCode}}' "$1" missing
}

record() {
  local kind="$1"
  local name="$2"
  local detail="${3:-}"
  if [[ -n "${detail}" ]]; then
    echo "${kind}  ${name} (${detail})"
  else
    echo "${kind}  ${name}"
  fi
  case "${kind}" in
    PASS) pass=$((pass + 1)) ;;
    FAIL) fail=$((fail + 1)) ;;
    SKIP) skip=$((skip + 1)) ;;
  esac
}

check() {
  local name="$1"
  shift
  local detail=""
  if detail="$("$@" 2>&1)"; then
    record PASS "${name}"
  else
    record FAIL "${name}" "${detail}"
  fi
}

expect_healthy() {
  local name="$1"
  local status health
  status="$(container_status "${name}")"
  health="$(container_health "${name}")"
  if [[ "${status}" == "running" && "${health}" == "healthy" ]]; then
    return 0
  fi
  echo "status=${status} health=${health}"
  return 1
}

expect_exited_zero() {
  local name="$1"
  local status code
  status="$(container_status "${name}")"
  code="$(container_exit "${name}")"
  if [[ "${status}" == "exited" && "${code}" == "0" ]]; then
    return 0
  fi
  echo "status=${status} exit=${code}"
  return 1
}

expect_running() {
  local name="$1"
  local status
  status="$(container_status "${name}")"
  if [[ "${status}" == "running" ]]; then
    return 0
  fi
  echo "status=${status}"
  return 1
}

expect_curl() {
  local url="$1"
  local err
  if err="$(curl -sf --max-time 10 "${url}" 2>&1)"; then
    return 0
  fi
  echo "curl ${url} failed${err:+: ${err}}"
  return 1
}

expect_curl_body() {
  local url="$1"
  local pattern="$2"
  local body
  if ! body="$(curl -sf --max-time 10 "${url}" 2>&1)"; then
    echo "curl ${url} failed: ${body}"
    return 1
  fi
  if [[ "${body}" == *"${pattern}"* ]]; then
    return 0
  fi
  echo "body did not contain ${pattern}"
  return 1
}

expect_http() {
  local url="$1"
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -L "${url}" || true)"
  if [[ "${code}" =~ ^[23] ]]; then
    return 0
  fi
  echo "http ${url} status=${code:-none}"
  return 1
}

expect_tcp() {
  local port="$1"
  if timeout 3 bash -c "echo >/dev/tcp/127.0.0.1/${port}" 2>/dev/null; then
    return 0
  fi
  echo "tcp 127.0.0.1:${port} closed"
  return 1
}

# Default /v1/sys/health returns 503 while sealed. Do not pass sealedcode=200:
# that forces HTTP 200 and hides a sealed Vault.
expect_vault_unsealed() {
  local url="http://127.0.0.1:${VAULT_PORT}/v1/sys/health"
  local body code compact
  if ! body="$(curl -sS --max-time 10 -w '\n%{http_code}' "${url}" 2>&1)"; then
    echo "curl ${url} failed: ${body}"
    return 1
  fi
  code="${body##*$'\n'}"
  body="${body%$'\n'*}"
  compact="${body//[[:space:]]/}"
  if [[ "${compact}" == *'"sealed":false'* ]]; then
    return 0
  fi
  echo "sealed or not initialized (http=${code})"
  return 1
}

profile_enabled() {
  [[ ",${COMPOSE_PROFILES}," == *",$1,"* ]]
}

container_running() {
  [[ "$(container_status "$1")" == "running" ]]
}

echo "=== Nexus stack verify (NEXUS_ENV=${NEXUS_ENV:-dev} NEXUS_SECRETS_BACKEND=${NEXUS_SECRETS_BACKEND}) ==="
echo

check "minio healthy" expect_healthy minio
check "minio-init exited 0" expect_exited_zero minio-init
check "otel-collector running" expect_running otel-collector
check "OTel health :${OTEL_HEALTH_PORT}" expect_curl "http://127.0.0.1:${OTEL_HEALTH_PORT}/"
check "clickhouse healthy" expect_healthy clickhouse
check "ClickHouse /ping" expect_curl_body "http://127.0.0.1:${CLICKHOUSE_HTTP_PORT}/ping" "Ok."
check "airflow-postgres healthy" expect_healthy airflow-postgres
check "airflow-api-server healthy" expect_healthy airflow-api-server
check "airflow-dag-processor healthy" expect_healthy airflow-dag-processor
check "airflow-scheduler healthy" expect_healthy airflow-scheduler
check "airflow-init exited 0" expect_exited_zero airflow-init
check "Airflow /api/v2/monitor/health" expect_curl "http://127.0.0.1:${AIRFLOW_WEBSERVER_PORT}/api/v2/monitor/health"
check "signoz healthy" expect_healthy signoz
check "SigNoz /api/v1/health" expect_curl "http://127.0.0.1:${SIGNOZ_UI_PORT}/api/v1/health"
check "openmetadata-postgresql healthy" expect_healthy openmetadata-postgresql
check "openmetadata-elasticsearch healthy" expect_healthy openmetadata-elasticsearch
check "openmetadata-migrate exited 0" expect_exited_zero openmetadata-migrate
check "openmetadata-server healthy" expect_healthy openmetadata-server
check "OpenMetadata /healthcheck" expect_curl "http://127.0.0.1:${OPENMETADATA_ADMIN_PORT}/healthcheck"
check "polaris healthy" expect_healthy polaris
check "Polaris /q/health" expect_curl "http://127.0.0.1:${POLARIS_MGMT_PORT}/q/health"
check "polaris-setup healthy" expect_healthy polaris-setup
check "spark-thrift healthy" expect_healthy spark-thrift
check "Spark Thrift TCP :${SPARK_THRIFT_PORT}" expect_tcp "${SPARK_THRIFT_PORT}"
check "trino healthy" expect_healthy trino
check "Trino /v1/info" expect_curl "http://127.0.0.1:${TRINO_PORT}/v1/info"

if [[ "${NEXUS_SECRETS_BACKEND}" == "vault" ]]; then
  check "vault healthy" expect_healthy vault
  check "Vault unsealed" expect_vault_unsealed
  check "vault-agent running" expect_running vault-agent
  check "Vault secrets.env present" test -f .nexusflow/secrets.env
else
  record SKIP "vault" "NEXUS_SECRETS_BACKEND=${NEXUS_SECRETS_BACKEND}"
  record SKIP "vault-agent" "NEXUS_SECRETS_BACKEND=${NEXUS_SECRETS_BACKEND}"
fi

if profile_enabled cloudbeaver || container_running cloudbeaver; then
  check "CloudBeaver HTTP :${CLOUDBEAVER_PORT}" expect_http "http://127.0.0.1:${CLOUDBEAVER_PORT}/"
else
  record SKIP "cloudbeaver" "profile not enabled and container not running"
fi

if profile_enabled proxy || container_running nexus-caddy; then
  check "nexus-caddy running" expect_running nexus-caddy
else
  record SKIP "nexus-caddy" "profile not enabled and container not running"
fi

record SKIP "openmetadata-ingestion" "optional heavy profile; catalog ingest is backlog item 3"

echo
echo "Result: ${pass} passed, ${fail} failed, ${skip} skipped"
[[ "${fail}" -eq 0 ]]
