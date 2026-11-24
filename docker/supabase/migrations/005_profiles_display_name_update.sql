-- Website users may change their display name. Email stays owned by Auth.
-- 001 granted table-wide UPDATE. Existing databases already applied that grant.

revoke update on table public.profiles from authenticated;
grant update (display_name, updated_at) on table public.profiles to authenticated;

notify pgrst, 'reload schema';

insert into public.schema_migrations (id)
values ('005_profiles_display_name_update')
on conflict (id) do nothing;
