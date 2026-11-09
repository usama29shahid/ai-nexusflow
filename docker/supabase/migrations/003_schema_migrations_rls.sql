-- public.schema_migrations is bookkeeping, not an API table.
-- 001 already ran on existing databases without these rules.
-- postgres (superuser) still applies migrations. anon/authenticated get no rows.

revoke all on table public.schema_migrations from anon, authenticated;
alter table public.schema_migrations enable row level security;
alter table public.schema_migrations force row level security;

insert into public.schema_migrations (id)
values ('003_schema_migrations_rls')
on conflict (id) do nothing;
