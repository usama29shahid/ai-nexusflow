#!/usr/bin/env bash
# Create nexus_loader / nexus_reader / nexus_catalog / nexus_admin on Supabase Postgres.
# Passwords from Vault Agent env, or generated once into .nexusflow/supabase-rbac.env.
# Run after ./scripts/supabase-migrate.sh so public tables exist.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

RBAC_ENV="${ROOT}/.nexusflow/supabase-rbac.env"

if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck source=/dev/null
  source "${ROOT}/.env"
  set +a
fi
# Do not swallow Vault/Agent failures — that would mint a new supabase-rbac.env
# while Vault already holds different passwords.
if [[ -f "${ROOT}/scripts/load-secrets.sh" ]]; then
  set -a
  # shellcheck source=scripts/load-secrets.sh
  source "${ROOT}/scripts/load-secrets.sh"
  set +a
fi

gen_pw() { python3 -c 'import secrets; print("k" + secrets.token_urlsafe(24))'; }

if [[ -z "${SUPABASE_LOADER_PASSWORD:-}" || -z "${SUPABASE_READER_PASSWORD:-}" || -z "${SUPABASE_CATALOG_PASSWORD:-}" || -z "${SUPABASE_ADMIN_PASSWORD:-}" ]]; then
  if [[ -f "${RBAC_ENV}" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "${RBAC_ENV}"
    set +a
  else
    mkdir -p "${ROOT}/.nexusflow"
    {
      echo "SUPABASE_LOADER_USER=nexus_loader"
      echo "SUPABASE_LOADER_PASSWORD=$(gen_pw)"
      echo "SUPABASE_READER_USER=nexus_reader"
      echo "SUPABASE_READER_PASSWORD=$(gen_pw)"
      echo "SUPABASE_CATALOG_USER=nexus_catalog"
      echo "SUPABASE_CATALOG_PASSWORD=$(gen_pw)"
      echo "SUPABASE_ADMIN_USER=nexus_admin"
      echo "SUPABASE_ADMIN_PASSWORD=$(gen_pw)"
    } >"${RBAC_ENV}"
    chmod 600 "${RBAC_ENV}"
    echo "Wrote ${RBAC_ENV} (seed into Vault when ready)."
    set -a
    # shellcheck source=/dev/null
    source "${RBAC_ENV}"
    set +a
  fi
fi

SUPABASE_LOADER_USER="${SUPABASE_LOADER_USER:-nexus_loader}"
SUPABASE_READER_USER="${SUPABASE_READER_USER:-nexus_reader}"
SUPABASE_CATALOG_USER="${SUPABASE_CATALOG_USER:-nexus_catalog}"
SUPABASE_ADMIN_USER="${SUPABASE_ADMIN_USER:-nexus_admin}"

if ! docker inspect supabase-db >/dev/null 2>&1; then
  echo "supabase-db is not running. Start with ./scripts/start.sh supabase" >&2
  exit 1
fi

echo "Applying Supabase Postgres RBAC..."
python3 - \
  "${SUPABASE_LOADER_USER}" "${SUPABASE_LOADER_PASSWORD}" \
  "${SUPABASE_READER_USER}" "${SUPABASE_READER_PASSWORD}" \
  "${SUPABASE_CATALOG_USER}" "${SUPABASE_CATALOG_PASSWORD}" \
  "${SUPABASE_ADMIN_USER}" "${SUPABASE_ADMIN_PASSWORD}" <<'PY' \
  | docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1 -d postgres
import sys

import re

def esc(value: str) -> str:
    return value.replace("'", "''")

def qident(name: str) -> str:
    # Postgres identifiers: quote and reject empty / NUL.
    if not name or "\x00" in name:
        raise SystemExit(f"invalid role name: {name!r}")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise SystemExit(f"invalid role name (use [A-Za-z_][A-Za-z0-9_]*): {name!r}")
    return '"' + name.replace('"', '""') + '"'

loader_u, loader_p, reader_u, reader_p, catalog_u, catalog_p, admin_u, admin_p = sys.argv[1:]
roles = [
    (loader_u, loader_p),
    (reader_u, reader_p),
    (catalog_u, catalog_p),
    (admin_u, admin_p),
]
qi = {u: qident(u) for u, _ in roles}

print("begin;")
for user, pw in roles:
    print(f"""
do $$
begin
  if not exists (select from pg_roles where rolname = '{esc(user)}') then
    create role {qi[user]} login password '{esc(pw)}';
  else
    alter role {qi[user]} with login password '{esc(pw)}';
  end if;
end $$;
""")

print(f"""
grant usage on schema public to {qi[loader_u]}, {qi[reader_u]}, {qi[catalog_u]};
grant select, insert, update on table public.document_chunks to {qi[loader_u]};
grant usage, select on sequence public.document_chunks_id_seq to {qi[loader_u]};
grant select on table public.document_chunks to {qi[reader_u]}, {qi[catalog_u]};
grant select on table public.profiles to {qi[reader_u]}, {qi[catalog_u]};
grant all privileges on schema public to {qi[admin_u]};
grant all privileges on all tables in schema public to {qi[admin_u]};
grant all privileges on all sequences in schema public to {qi[admin_u]};
alter default privileges in schema public grant all on tables to {qi[admin_u]};
alter role {qi[admin_u]} bypassrls;
""")
print("commit;")
PY

echo "Supabase RBAC OK (${SUPABASE_LOADER_USER}, ${SUPABASE_READER_USER}, ${SUPABASE_CATALOG_USER}, ${SUPABASE_ADMIN_USER})."
echo "Seed Vault: secret/nexusflow/\${NEXUS_ENV}/supabase_* — see docs/vault.md"
