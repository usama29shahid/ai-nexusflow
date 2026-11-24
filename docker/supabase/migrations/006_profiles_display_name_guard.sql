-- The website checks display name length. Enforce it for direct API writes too.
-- updated_at is set here so a client cannot choose the "Changed" time.
-- 005 granted UPDATE on updated_at. This migration takes that column back.

alter table public.profiles
  drop constraint if exists profiles_display_name_length;

alter table public.profiles
  add constraint profiles_display_name_length
  check (
    display_name is null
    or char_length(btrim(display_name)) between 1 and 80
  );

create or replace function public.set_profiles_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if new.display_name is not null then
    new.display_name := btrim(new.display_name);
  end if;
  new.updated_at := now();
  return new;
end;
$$;

drop trigger if exists profiles_set_updated_at on public.profiles;
create trigger profiles_set_updated_at
  before update on public.profiles
  for each row
  execute function public.set_profiles_updated_at();

revoke all on function public.set_profiles_updated_at() from public;
grant execute on function public.set_profiles_updated_at() to authenticated;

revoke update on table public.profiles from authenticated;
revoke update (display_name, updated_at) on table public.profiles from authenticated;
grant update (display_name) on table public.profiles to authenticated;

notify pgrst, 'reload schema';

insert into public.schema_migrations (id)
values ('006_profiles_display_name_guard')
on conflict (id) do nothing;
