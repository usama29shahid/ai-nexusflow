#!/usr/bin/env bash
# Bootstrap ClickHouse layer DBs + nexus_* users/GRANTs.
# Usage (from repo root):
#   set -a && source .env && source scripts/load-secrets.sh; set +a
#   ./scripts/clickhouse-rbac-bootstrap.sh
#
# On VPS (NEXUS_SECRETS_BACKEND=vault): passwords come from Vault Agent via
# load-secrets.sh — not from editing .env. After rotating KV in Vault UI,
# reload Agent, source load-secrets.sh, then re-run this script (ALTER USER).
#
# SQL is piped into clickhouse-client (no temp file with passwords on disk).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

NEXUS_ENV="${NEXUS_ENV:-dev}"
ADMIN_USER="${CLICKHOUSE_USER:-default}"
ADMIN_PASSWORD="${CLICKHOUSE_PASSWORD:?CLICKHOUSE_PASSWORD required}"

LOADER_PASSWORD="${CLICKHOUSE_LOADER_PASSWORD:-${CLICKHOUSE_PASSWORD}}"
TRANSFORMER_PASSWORD="${CLICKHOUSE_TRANSFORMER_PASSWORD:-${CLICKHOUSE_PASSWORD}}"
READER_PASSWORD="${CLICKHOUSE_READER_PASSWORD:-${CLICKHOUSE_PASSWORD}}"
NEXUS_ADMIN_PASSWORD="${CLICKHOUSE_ADMIN_PASSWORD:-${CLICKHOUSE_PASSWORD}}"

tpl="${ROOT}/scripts/sql/clickhouse_rbac_bootstrap.sql.tpl"

echo "Applying ClickHouse RBAC for NEXUS_ENV=${NEXUS_ENV} as ${ADMIN_USER}..."
python3 - "${tpl}" "${NEXUS_ENV}" \
  "${LOADER_PASSWORD}" "${TRANSFORMER_PASSWORD}" "${READER_PASSWORD}" "${NEXUS_ADMIN_PASSWORD}" <<'PY' \
  | docker compose exec -T clickhouse clickhouse-client \
      --user "${ADMIN_USER}" --password "${ADMIN_PASSWORD}" \
      --multiquery
import re
import sys

src, env, loader_pw, transformer_pw, reader_pw, admin_pw = sys.argv[1:]

if not re.fullmatch(r"[a-z0-9_]+", env):
    raise SystemExit(f"Invalid NEXUS_ENV for SQL identifiers: {env!r}")


def sql_string(value: str) -> str:
    """Escape a value for a ClickHouse single-quoted string literal."""
    return value.replace("\\", "\\\\").replace("'", "''")


text = open(src).read()
repl = {
    "{{NEXUS_ENV}}": env,
    "{{LOADER_PASSWORD}}": sql_string(loader_pw),
    "{{TRANSFORMER_PASSWORD}}": sql_string(transformer_pw),
    "{{READER_PASSWORD}}": sql_string(reader_pw),
    "{{ADMIN_PASSWORD}}": sql_string(admin_pw),
}
for k, v in repl.items():
    text = text.replace(k, v)
sys.stdout.write(text)
PY

echo "RBAC bootstrap OK (nexus_loader, nexus_transformer, nexus_reader, nexus_admin)."
