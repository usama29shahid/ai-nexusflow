-- JavaScript String.trim removes more than PostgreSQL btrim. A direct update could
-- store a name made only of tabs, newlines, or other Unicode spaces. Trim that
-- same set here, on update and on signup, and use it in the length check.
--
-- WhiteSpace plus LineTerminator from ECMA-262. U+0085 and U+180E are not
-- included; current JavaScript does not trim them.
-- authenticated can execute the trim function because the check runs as the
-- role that updates the row. anon and service_role cannot.
--
-- One transaction. Disabling the trigger commits only together with the
-- rewrite, the stricter check, and turning the trigger back on.

begin;

create or replace function public.trim_display_name(value text)
returns text
language sql
immutable
parallel safe
set search_path = pg_catalog
as $$
  select btrim(
    value,
    U&'\0009\000A\000B\000C\000D\0020\00A0\1680\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029\202F\205F\3000\FEFF'
  );
$$;

revoke all on function public.trim_display_name(text) from public, anon, service_role;
grant execute on function public.trim_display_name(text) to authenticated;

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
    new.display_name := public.trim_display_name(new.display_name);
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

-- Rewrite stored names before the stricter check. Leave updated_at alone.
alter table public.profiles disable trigger profiles_set_updated_at;

update public.profiles
set display_name = nullif(public.trim_display_name(display_name), '')
where display_name is not null
  and display_name is distinct from nullif(public.trim_display_name(display_name), '');

alter table public.profiles enable trigger profiles_set_updated_at;

alter table public.profiles
  drop constraint if exists profiles_display_name_length;

alter table public.profiles
  add constraint profiles_display_name_length
  check (
    display_name is null
    or char_length(public.trim_display_name(display_name)) between 1 and 80
  );

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  chosen_name text;
begin
  chosen_name := nullif(
    public.trim_display_name(coalesce(new.raw_user_meta_data->>'display_name', '')),
    ''
  );
  insert into public.profiles (id, email, display_name)
  values (new.id, new.email, chosen_name)
  on conflict (id) do nothing;
  return new;
end;
$$;

notify pgrst, 'reload schema';

insert into public.schema_migrations (id)
values ('008_profiles_display_name_unicode_trim')
on conflict (id) do nothing;

commit;
