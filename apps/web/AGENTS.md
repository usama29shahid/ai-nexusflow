# Website agent notes

Read [docs/nexus-frontend.md](../../docs/nexus-frontend.md) before changing this app.

- This Next.js app is the website. Do not add a second UI under `ui/`.
- Sign-in is Supabase email and password. The session cookie is httpOnly. Sign-out deletes it.
- After login the home is `/dashboards/ecommerce` with the template sample numbers.
- The header and profile drawer stay. Show `profiles.email`. Do not remove the language, theme, notification, team, invites, or support pieces. Billing and the upgrade card are removed. Help and Support open `/pages/get-help`.
- Leave the Google button and forgot-password page unwired.
- Leave the chat page unwired. Do not add a chat panel in this slice.
- Do not give website users a ClickHouse login. Later chart numbers come from Cube.
- Keep the original Nexus zip outside the git repository.
