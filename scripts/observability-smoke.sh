#!/usr/bin/env bash
# Quick observability infra smoke test (MinIO lake + OTel Collector + optional readers).
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

NEXUS_ENV="${NEXUS_ENV:-dev}"
NEXUS_RUN_ID="${NEXUS_RUN_ID:-local-smoke-$(date -u +%Y%m%dT%H%M%SZ)}"
export NEXUS_ENV NEXUS_RUN_ID

pass=0
fail=0

check() {
  local name="$1"
  shift
  if "$@"; then
    echo "PASS  ${name}"
    pass=$((pass + 1))
  else
    echo "FAIL  ${name}"
    fail=$((fail + 1))
  fi
}

running() {
  docker ps --format '{{.Names}}' | grep -qx "$1"
}

echo "=== Nexus observability smoke (NEXUS_ENV=${NEXUS_ENV}) ==="
echo

check "otel-collector container running" running otel-collector
check "minio container running" running minio
check "OTLP HTTP :4318" curl -sf -X POST "http://127.0.0.1:${OTEL_HTTP_PORT:-4318}/v1/traces" \
  -H 'Content-Type: application/json' -d '{"resourceSpans":[]}' >/dev/null
check "OTel health :13133" curl -sf "http://127.0.0.1:${OTEL_HEALTH_PORT:-13133}/" >/dev/null

if uv run python -c "
from common.observability import publish_run_summary
print(publish_run_summary('${NEXUS_RUN_ID}', branch='dlt_dbt_clickhouse', component='smoke', status='ok'))
" >/tmp/nexus-obs-smoke.txt 2>/tmp/nexus-obs-smoke.err; then
  echo "PASS  lake write (publish_run_summary)"
  pass=$((pass + 1))
  cat /tmp/nexus-obs-smoke.txt
else
  echo "FAIL  lake write (publish_run_summary)"
  cat /tmp/nexus-obs-smoke.err >&2
  fail=$((fail + 1))
fi

if running signoz; then
  check "SigNoz UI health" curl -sf "http://127.0.0.1:${SIGNOZ_UI_PORT:-3301}/api/v1/health" >/dev/null
else
  echo "SKIP  SigNoz (profile not running — ./scripts/start.sh signoz)"
fi

if running openmetadata-server; then
  check "OpenMetadata admin health" curl -sf "http://127.0.0.1:${OPENMETADATA_ADMIN_PORT:-8586}/healthcheck" >/dev/null
else
  echo "SKIP  OpenMetadata (profile not running — ./scripts/start.sh openmetadata)"
fi

echo
echo "Result: ${pass} passed, ${fail} failed"
[[ "${fail}" -eq 0 ]]
