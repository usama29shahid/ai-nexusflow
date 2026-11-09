-- NexusFlow app schema for self-hosted Supabase (item 11).
-- Idempotent. Applied by ./scripts/supabase-migrate.sh as postgres/nexus_admin.

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
create schema if not exists extensions;
create extension if not exists vector with schema extensions;

-- ---------------------------------------------------------------------------
-- Migration bookkeeping
-- ---------------------------------------------------------------------------
create table if not exists public.schema_migrations (
  id text primary key,
  applied_at timestamptz not null default now()
);

-- Not an API table. 003 repeats this for databases where 001 already ran.
revoke all on table public.schema_migrations from anon, authenticated;
alter table public.schema_migrations enable row level security;
alter table public.schema_migrations force row level security;

-- ---------------------------------------------------------------------------
-- Profiles (one row per auth user)
-- ---------------------------------------------------------------------------
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  email text,
  display_name text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;
alter table public.profiles force row level security;

drop policy if exists profiles_select_own on public.profiles;
create policy profiles_select_own
  on public.profiles
  for select
  to authenticated
  using (auth.uid() = id);

drop policy if exists profiles_update_own on public.profiles;
create policy profiles_update_own
  on public.profiles
  for update
  to authenticated
  using (auth.uid() = id)
  with check (auth.uid() = id);

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email)
  values (new.id, new.email)
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- Shared RAG chunks (org standards). Dimension constant filled when model chosen.
-- Until then use vector(3) for smoke tests; later migration bumps the size.
-- ---------------------------------------------------------------------------
create table if not exists public.document_chunks (
  id bigserial primary key,
  content text not null,
  source_path text not null,
  metadata jsonb not null default '{}'::jsonb,
  embedding extensions.vector(3),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.document_chunks enable row level security;
alter table public.document_chunks force row level security;

drop policy if exists document_chunks_select_authenticated on public.document_chunks;
create policy document_chunks_select_authenticated
  on public.document_chunks
  for select
  to authenticated
  using (true);

-- Process roles (passwords set by ./scripts/supabase-rbac-bootstrap.sh).
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

-- FORCE RLS applies to every role; grant write only to the process loader.
-- Reader/catalog SELECT and nexus_admin BYPASSRLS are migration 002
-- (001 is already applied on existing databases, so those rules live in 002).
drop policy if exists document_chunks_loader_write on public.document_chunks;
create policy document_chunks_loader_write
  on public.document_chunks
  for all
  to nexus_loader
  using (true)
  with check (true);

-- No insert/update/delete policies for anon or authenticated.

create or replace function public.match_document_chunks(
  query_embedding extensions.vector(3),
  match_count int default 5
)
returns table (
  id bigint,
  content text,
  source_path text,
  metadata jsonb,
  distance float
)
language sql
stable
security invoker
set search_path = public, extensions
as $$
  select
    c.id,
    c.content,
    c.source_path,
    c.metadata,
    (c.embedding <=> query_embedding) as distance
  from public.document_chunks c
  where c.embedding is not null
  order by c.embedding <=> query_embedding
  limit greatest(match_count, 1);
$$;

grant usage on schema public to anon, authenticated;
grant select on public.profiles to authenticated;
grant update on public.profiles to authenticated;
grant select on public.document_chunks to authenticated;
grant execute on function public.match_document_chunks(extensions.vector, int) to authenticated;

revoke all on public.document_chunks from anon;
revoke all on public.profiles from anon;

insert into public.schema_migrations (id)
values ('001_app_roles_profiles_pgvector')
on conflict (id) do nothing;
