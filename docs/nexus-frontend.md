# Nexus website

Nexus Next.js in `apps/web` is the website. Supabase Auth is the app backend for sign-in and `profiles`. ClickHouse, Cube, Airflow, and the other lab tools stay their own services.

## This slice

- Branch `feat/nexus-web`. The app is served by Caddy at `app.${NEXUS_PUBLIC_HOST}`. From a laptop that is `http://app.localhost.com:8080` when local port 8080 tunnels to Caddy port 80. The Next container does not publish a host port.
- Email and password login and register call Supabase with the anon key. The container uses `http://kong:8000`. Passwords follow the Auth rule: 8 or more characters, with lowercase, uppercase, a digit, and a symbol.
- A signed-in person has the Supabase role `authenticated`. That role can open the dashboard. `nexus_loader`, `nexus_reader`, `nexus_catalog`, `nexus_admin`, and `service_role` are not website roles.
- After login the home is `/dashboards/ecommerce`. The stat cards, chart, and table still use the template sample numbers.
- The admin top bar stays: search, language, theme, notifications, and the profile drawer. The drawer shows `profiles.display_name` or the mailbox name, and always shows `profiles.email`. Sign Out is a server action that ends the Supabase session, deletes the httpOnly cookies, and returns to `/auth/login`.
- View Profile and Settings open `/pages/settings`. Help in the sidebar and Support in the profile drawer open `/pages/get-help`. Team and Invites stay visible and are not connected. Billing and the upgrade card are not in the drawer.
- The sidebar lists Ecommerce and Settings. The Nexus component gallery and the other demo dashboards are not in this app. Chat stays in the tree for a later slice.

## Later

- Google, GitHub, forgot-password, and email OTP wait until SES and the OAuth apps exist.
- Replace the ecommerce sample numbers by calling Cube `POST /v1/load`. Cube already reads Gold as `nexus_reader`. The browser does not open ClickHouse or the Route API.
- Chat (`src/app/(admin)/apps/chat/page.tsx`) stays in the tree and is not a product surface yet. Streaming, history, and citations are a later customization.

The original download stays at `/home/ubuntu/nexus-private/nexus-nextjs.zip` and is not committed.
