#!/usr/bin/env bash
# Apply SQL files under docker/supabase/migrations/ that are not yet in schema_migrations.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIG_DIR="${ROOT}/docker/supabase/migrations"

if ! docker inspect supabase-db >/dev/null 2>&1; then
  echo "supabase-db is not running. Start with ./scripts/start.sh supabase" >&2
  exit 1
fi

docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1 -d postgres <<'SQL'
create schema if not exists extensions;
create table if not exists public.schema_migrations (
  id text primary key,
  applied_at timestamptz not null default now()
);
revoke all on table public.schema_migrations from anon, authenticated;
alter table public.schema_migrations enable row level security;
alter table public.schema_migrations force row level security;
SQL

shopt -s nullglob
for file in "${MIG_DIR}"/*.sql; do
  id="$(basename "${file}" .sql)"
  applied="$(docker exec supabase-db psql -U postgres -d postgres -Atc \
    "select 1 from public.schema_migrations where id = '${id}'")"
  if [[ "${applied}" == "1" ]]; then
    echo "skip ${id}"
    continue
  fi
  echo "apply ${id}"
  docker exec -i supabase-db psql -U postgres -v ON_ERROR_STOP=1 -d postgres <"${file}"
done

echo "Supabase migrations OK"
