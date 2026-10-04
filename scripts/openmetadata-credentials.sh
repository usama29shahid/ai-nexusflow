#!/usr/bin/env bash
# Ensure OPENMETADATA_ADMIN_* for catalog login.
# Default backend is vault (Agent secrets.env). Legacy env mode still writes .env
# only when NEXUS_SECRETS_BACKEND=env is set explicitly.
#
# OpenMetadata first boot always creates admin@open-metadata.org / admin.
# Keep OPENMETADATA_ADMIN_* aligned with that (or rotate UI + Vault together).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ensure_openmetadata_env_credentials() {
  local backend="${NEXUS_SECRETS_BACKEND:-vault}"
  if [[ "${backend}" == "vault" ]]; then
    return 0
  fi
  if [[ ! -f .env ]]; then
    return 0
  fi
  if ! grep -q '^OPENMETADATA_ADMIN_EMAIL=.\+' .env; then
    if grep -q '^OPENMETADATA_ADMIN_EMAIL=' .env; then
      sed -i 's|^OPENMETADATA_ADMIN_EMAIL=.*|OPENMETADATA_ADMIN_EMAIL=admin@open-metadata.org|' .env
    else
      printf '\nOPENMETADATA_ADMIN_EMAIL=admin@open-metadata.org\n' >> .env
    fi
    echo "Set OPENMETADATA_ADMIN_EMAIL in .env"
  fi
  if ! grep -q '^OPENMETADATA_ADMIN_PASSWORD=.\+' .env; then
    if grep -q '^OPENMETADATA_ADMIN_PASSWORD=' .env; then
      sed -i 's|^OPENMETADATA_ADMIN_PASSWORD=.*|OPENMETADATA_ADMIN_PASSWORD=admin|' .env
    else
      printf 'OPENMETADATA_ADMIN_PASSWORD=admin\n' >> .env
    fi
    echo "Set OPENMETADATA_ADMIN_PASSWORD in .env (OM first-boot default)"
  fi
  if ! grep -q '^CLICKHOUSE_CATALOG_USER=.\+' .env; then
    if grep -q '^CLICKHOUSE_CATALOG_USER=' .env; then
      sed -i 's|^CLICKHOUSE_CATALOG_USER=.*|CLICKHOUSE_CATALOG_USER=nexus_catalog|' .env
    else
      printf 'CLICKHOUSE_CATALOG_USER=nexus_catalog\n' >> .env
    fi
    echo "Set CLICKHOUSE_CATALOG_USER=nexus_catalog in .env"
  fi
  if ! grep -q '^CLICKHOUSE_CATALOG_PASSWORD=.\+' .env; then
    local pw="${CLICKHOUSE_PASSWORD:-}"
    if [[ -z "${pw}" ]]; then
      pw="$(grep -E '^CLICKHOUSE_PASSWORD=' .env 2>/dev/null | tail -1 | cut -d= -f2- || true)"
    fi
    if [[ -z "${pw}" ]]; then
      pw="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
    fi
    if grep -q '^CLICKHOUSE_CATALOG_PASSWORD=' .env; then
      sed -i "s|^CLICKHOUSE_CATALOG_PASSWORD=.*|CLICKHOUSE_CATALOG_PASSWORD=${pw}|" .env
    else
      printf 'CLICKHOUSE_CATALOG_PASSWORD=%s\n' "${pw}" >> .env
    fi
    echo "Set CLICKHOUSE_CATALOG_PASSWORD in .env (aligned with ClickHouse admin/bootstrap)"
    echo "Re-run ./scripts/clickhouse-rbac-bootstrap.sh if nexus_catalog auth fails."
  fi
  set -a
  # shellcheck source=/dev/null
  source .env
  set +a
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
  ensure_openmetadata_env_credentials
  echo "OpenMetadata credentials ready (email=${OPENMETADATA_ADMIN_EMAIL:-admin@open-metadata.org})"
fi
