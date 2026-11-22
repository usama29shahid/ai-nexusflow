-- Signup stores the chosen name on the Auth user. The profile row is created
-- by this trigger, before the browser has a session, so the name cannot be
-- written later under RLS when email confirmation is required.

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  chosen_name text;
begin
  chosen_name := nullif(btrim(coalesce(new.raw_user_meta_data->>'display_name', '')), '');
  insert into public.profiles (id, email, display_name)
  values (new.id, new.email, chosen_name)
  on conflict (id) do nothing;
  return new;
end;
$$;

insert into public.schema_migrations (id)
values ('004_profile_display_name_from_signup')
on conflict (id) do nothing;
