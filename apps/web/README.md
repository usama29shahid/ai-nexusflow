# Website

Nexus Next.js is the public site. Caddy is the only door: `http://app.localhost.com` on the instance, or `http://app.localhost.com:8080` from a laptop whose SSH tunnel forwards local port 8080 to Caddy port 80.

```bash
./scripts/proxy-hosts.sh install
./scripts/start.sh web
```

`start.sh web` writes `.nexusflow/web.env` with the Supabase anon key only, builds this image, and starts Caddy. The container calls Auth at `http://kong:8000`. The service-role key stays out of this service.

Email and password sign-in and register use Supabase. A signed-in person has the `authenticated` role and lands on the ecommerce dashboard. The Google button and the forgot-password page are still the template screens. Chat is not wired.

Rebuild after a code change with `./scripts/start.sh web`.
