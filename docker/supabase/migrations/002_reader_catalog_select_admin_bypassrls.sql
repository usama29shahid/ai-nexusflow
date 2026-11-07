-- Reader and catalog can see rows under FORCE RLS.
-- nexus_admin bypasses RLS (break-glass). Idempotent.
-- 001 is already recorded on existing databases, so this is a new migration.

do $$
begin
  if not exists (select from pg_roles where rolname = 'nexus_loader') then
    create role nexus_loader nologin;
  end if;
  if not exists (select from pg_roles where rolname = 'nexus_reader') then
    create role nexus_reader nologin;
  end if;
  if not exists (select from pg_roles where rolname = 'nexus_catalog') then
    create role nexus_catalog nologin;
  end if;
  if not exists (select from pg_roles where rolname = 'nexus_admin') then
    create role nexus_admin nologin;
  end if;
end $$;

drop policy if exists document_chunks_select_reader on public.document_chunks;
create policy document_chunks_select_reader
  on public.document_chunks
  for select
  to nexus_reader, nexus_catalog
  using (true);

drop policy if exists profiles_select_reader on public.profiles;
create policy profiles_select_reader
  on public.profiles
  for select
  to nexus_reader, nexus_catalog
  using (true);

alter role nexus_admin bypassrls;

insert into public.schema_migrations (id)
values ('002_reader_catalog_select_admin_bypassrls')
on conflict (id) do nothing;
