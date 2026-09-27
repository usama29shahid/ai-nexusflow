#!/usr/bin/env bash
# Upsert all JSON dashboards under docker/openobserve/dashboards/ (backlog 2.1).
# Pipeline code never calls OpenObserve. Uses ZO_ROOT_USER_* Basic auth.
#
# Usage:
#   ./scripts/openobserve-bootstrap.sh
#
# OPENOBSERVE_URL overrides the base URL (e.g. http://openobserve:5080 on Compose DNS).
# When host :5080 is unreachable (common under Docker Desktop + WSL), falls back to
# curl via a one-shot container on the Compose network.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck source=/dev/null
  source .env
  set +a
fi
if [[ -f scripts/load-secrets.sh ]]; then
  set -a
  # shellcheck source=/dev/null
  source scripts/load-secrets.sh 2>/dev/null || true
  set +a
fi

# shellcheck source=scripts/openobserve-credentials.sh
source "${ROOT}/scripts/openobserve-credentials.sh"
ensure_openobserve_env_credentials

UI_PORT="${OPENOBSERVE_UI_PORT:-5080}"
ORG="${OPENOBSERVE_ORG:-default}"
DASHBOARD_DIR="${ROOT}/docker/openobserve/dashboards"
COMPOSE_NETWORK="${OPENOBSERVE_COMPOSE_NETWORK:-ai-nexusflow_default}"

if [[ -z "${ZO_ROOT_USER_EMAIL:-}" || -z "${ZO_ROOT_USER_PASSWORD:-}" ]]; then
  echo "ERROR: ZO_ROOT_USER_EMAIL / ZO_ROOT_USER_PASSWORD required" >&2
  exit 1
fi

AUTH=(-u "${ZO_ROOT_USER_EMAIL}:${ZO_ROOT_USER_PASSWORD}")
USE_DOCKER_CURL=0
UI_BASE="${OPENOBSERVE_URL:-http://127.0.0.1:${UI_PORT}}"
UI_BASE="${UI_BASE%/}"

oo_curl() {
  # Host connects need short connect timeout (WSL can hang). Allow longer
  # total time — dashboard list JSON is ~60KB and dockerized curl is slower.
  local timeout_args=(-m 60 --connect-timeout 3)
  if [[ "${USE_DOCKER_CURL}" -eq 0 ]]; then
    curl "${timeout_args[@]}" "$@"
    return
  fi
  local args=()
  local a
  for a in "$@"; do
    a="${a//http:\/\/127.0.0.1:${UI_PORT}/http://openobserve:5080}"
    a="${a//http:\/\/localhost:${UI_PORT}/http://openobserve:5080}"
    args+=("$a")
  done
  docker run --rm --network "${COMPOSE_NETWORK}" curlimages/curl:8.5.0 "${timeout_args[@]}" "${args[@]}"
}

# POST/PUT JSON body; mounts host file when using Compose-network curl.
oo_curl_json_file() {
  local method="$1"
  local url="$2"
  local file="$3"
  if [[ "${USE_DOCKER_CURL}" -eq 0 ]]; then
    curl -sf -m 60 --connect-timeout 3 "${AUTH[@]}" -X "${method}" "${url}" \
      -H "Content-Type: application/json" \
      --data-binary @"${file}"
    return
  fi
  docker run --rm --network "${COMPOSE_NETWORK}" \
    -v "${file}:/dash.json:ro" \
    curlimages/curl:8.5.0 \
    -sf -m 60 --connect-timeout 3 "${AUTH[@]}" -X "${method}" "${url}" \
    -H "Content-Type: application/json" \
    --data-binary @/dash.json
}

wait_healthy() {
  local i
  for i in $(seq 1 30); do
    if oo_curl -sf "${UI_BASE}/healthz" >/dev/null; then
      return 0
    fi
    sleep 1
  done
  return 1
}

if wait_healthy; then
  :
elif [[ -z "${OPENOBSERVE_URL:-}" ]] && docker network inspect "${COMPOSE_NETWORK}" >/dev/null 2>&1; then
  echo "Host ${UI_BASE}/healthz unreachable — using Compose network ${COMPOSE_NETWORK}"
  USE_DOCKER_CURL=1
  UI_BASE="http://openobserve:5080"
  if ! wait_healthy; then
    echo "ERROR: OpenObserve not healthy at ${UI_BASE}/healthz — start with ./scripts/start.sh openobserve" >&2
    exit 1
  fi
else
  echo "ERROR: OpenObserve not healthy at ${UI_BASE}/healthz — start with ./scripts/start.sh openobserve" >&2
  exit 1
fi

mapfile -t DASHBOARD_FILES < <(find "${DASHBOARD_DIR}" -maxdepth 1 -type f -name '*.json' | sort)
if ((${#DASHBOARD_FILES[@]} == 0)); then
  echo "ERROR: no dashboard JSON under ${DASHBOARD_DIR}" >&2
  exit 1
fi

dashboard_title() {
  python3 -c 'import json,sys; print(json.load(open(sys.argv[1],encoding="utf-8")).get("title") or "")' "$1"
}

list_existing() {
  local body
  if ! body="$(oo_curl -sf "${AUTH[@]}" "${UI_BASE}/api/${ORG}/dashboards")"; then
    echo "ERROR: failed to list dashboards at ${UI_BASE}/api/${ORG}/dashboards" >&2
    exit 1
  fi
  printf '%s\n' "${body}"
}

find_dashboard_ids() {
  # JSON on stdin, title as argv — do not use a heredoc (it steals stdin).
  local title="$1"
  python3 -c '
import json, sys
title = sys.argv[1]
data = json.load(sys.stdin)
items = data.get("dashboards") or data.get("data") or data
if isinstance(items, dict):
    items = items.get("dashboards") or []
if not isinstance(items, list):
    raise SystemExit(0)
for d in items:
    if not isinstance(d, dict):
        continue
    t = d.get("title") or d.get("name") or ""
    if t == title:
        did = d.get("dashboardId") or d.get("dashboard_id") or ""
        if did:
            print(did)
' "${title}"
}

echo "OpenObserve bootstrap → ${UI_BASE} org=${ORG} (docker_curl=${USE_DOCKER_CURL})"

for path in "${DASHBOARD_FILES[@]}"; do
  title="$(dashboard_title "${path}")"
  if [[ -z "${title}" ]]; then
    echo "SKIP (no title): ${path}"
    continue
  fi
  # Always re-list so we delete every duplicate with this title before create.
  existing="$(list_existing)"
  mapfile -t existing_ids < <(find_dashboard_ids "${title}" <<<"${existing}" || true)
  if ((${#existing_ids[@]} > 0)); then
    echo "REPLACE ${title} (${#existing_ids[@]} existing)"
    for existing_id in "${existing_ids[@]}"; do
      [[ -z "${existing_id}" ]] && continue
      oo_curl -sf "${AUTH[@]}" -X DELETE \
        "${UI_BASE}/api/${ORG}/dashboards/${existing_id}" >/dev/null 2>&1 || true
    done
  else
    echo "CREATE ${title}"
  fi
  oo_curl_json_file POST \
    "${UI_BASE}/api/${ORG}/dashboards" \
    "${path}" >/dev/null
done

# Safety net: keep one id per title (handles races / prior duplicates).
if [[ "${USE_DOCKER_CURL}" -eq 1 ]]; then
  docker run --rm --network "${COMPOSE_NETWORK}" \
    -v "${ROOT}:/work" -w /work \
    -e ZO_ROOT_USER_EMAIL -e ZO_ROOT_USER_PASSWORD \
    -e OPENOBSERVE_URL=http://openobserve:5080 \
    -e OPENOBSERVE_ORG="${ORG}" \
    python:3.12-slim python scripts/openobserve-dedupe-dashboards.py
else
  OPENOBSERVE_URL="${UI_BASE}" OPENOBSERVE_ORG="${ORG}" \
    python3 "${ROOT}/scripts/openobserve-dedupe-dashboards.py"
fi

echo "--- dashboard inventory ---"
list_existing | python3 -c '
import json, sys
from collections import Counter
data = json.load(sys.stdin)
items = data if isinstance(data, list) else data.get("dashboards") or []
if isinstance(items, dict):
    items = items.get("dashboards") or []
titles = [d.get("title") for d in items if isinstance(d, dict)]
counts = Counter(titles)
print(f"Dashboards listed: {len(titles)}")
for t, n in sorted(counts.items()):
    flag = " (DUPLICATE)" if n > 1 else ""
    print(f"  - {t} x{n}{flag}")
duplicates = sum(1 for n in counts.values() if n > 1)
if duplicates:
    raise SystemExit("ERROR: duplicate dashboard titles remain after bootstrap")
'

echo "Done. Open http://127.0.0.1:${UI_PORT} → Dashboards (or ${UI_BASE} on Compose DNS)"
