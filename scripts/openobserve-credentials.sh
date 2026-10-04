#!/usr/bin/env bash
# Ensure ZO_ROOT_USER_* / OPENOBSERVE_OTLP_BASIC_AUTH for the collector.
# Default backend is vault (Agent secrets.env). Legacy env mode still writes .env
# only when NEXUS_SECRETS_BACKEND=env is set explicitly.
#
# Usage: sourced or run from start.sh before compose up openobserve / otel sync.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ensure_openobserve_env_credentials() {
  local backend="${NEXUS_SECRETS_BACKEND:-vault}"
  if [[ "${backend}" == "vault" ]]; then
    return 0
  fi
  if [[ ! -f .env ]]; then
    return 0
  fi
  if ! grep -q '^ZO_ROOT_USER_EMAIL=.\+' .env; then
    if grep -q '^ZO_ROOT_USER_EMAIL=' .env; then
      sed -i 's|^ZO_ROOT_USER_EMAIL=.*|ZO_ROOT_USER_EMAIL=root@nexusflow.local|' .env
    else
      printf '\nZO_ROOT_USER_EMAIL=root@nexusflow.local\n' >> .env
    fi
    echo "Generated ZO_ROOT_USER_EMAIL in .env"
  fi
  if ! grep -q '^ZO_ROOT_USER_PASSWORD=.\+' .env; then
    local pw
    pw="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
    if grep -q '^ZO_ROOT_USER_PASSWORD=' .env; then
      sed -i "s|^ZO_ROOT_USER_PASSWORD=.*|ZO_ROOT_USER_PASSWORD=${pw}|" .env
    else
      printf 'ZO_ROOT_USER_PASSWORD=%s\n' "${pw}" >> .env
    fi
    echo "Generated ZO_ROOT_USER_PASSWORD in .env"
  fi
  set -a
  # shellcheck source=/dev/null
  source .env
  set +a
}

export_openobserve_otlp_basic_auth() {
  if [[ -z "${ZO_ROOT_USER_EMAIL:-}" || -z "${ZO_ROOT_USER_PASSWORD:-}" ]]; then
    echo "ERROR: ZO_ROOT_USER_EMAIL and ZO_ROOT_USER_PASSWORD required for OpenObserve OTLP" >&2
    return 1
  fi
  export OPENOBSERVE_OTLP_BASIC_AUTH
  OPENOBSERVE_OTLP_BASIC_AUTH="$(
    python3 -c 'import base64, os; e=os.environ["ZO_ROOT_USER_EMAIL"]; p=os.environ["ZO_ROOT_USER_PASSWORD"]; print(base64.b64encode(f"{e}:{p}".encode()).decode())'
  )"
}

# When executed directly (not sourced):
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
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
  ensure_openobserve_env_credentials
  export_openobserve_otlp_basic_auth
  echo "OPENOBSERVE_OTLP_BASIC_AUTH ready (email=${ZO_ROOT_USER_EMAIL})"
fi
