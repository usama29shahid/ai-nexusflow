-- 006 revoked EXECUTE from PUBLIC. Supabase default privileges still grant it to
-- anon and service_role when the function is created. Those roles do not update
-- profiles. authenticated keeps EXECUTE so its own UPDATE can fire the trigger.
-- An update must not clear a display name. Rows that never had one may stay null
-- until a name is set. The length check from 006 still applies.

create or replace function public.set_profiles_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  if new.display_name is null then
    if old.display_name is not null then
      raise exception 'display_name is required'
        using errcode = '23514';
    end if;
  else
    new.display_name := btrim(new.display_name);
    if new.display_name = '' then
      raise exception 'display_name is required'
        using errcode = '23514';
    end if;
  end if;
  new.updated_at := now();
  return new;
end;
$$;

revoke all on function public.set_profiles_updated_at() from public, anon, service_role;
grant execute on function public.set_profiles_updated_at() to authenticated;

notify pgrst, 'reload schema';

insert into public.schema_migrations (id)
values ('007_profiles_name_required_on_update')
on conflict (id) do nothing;
