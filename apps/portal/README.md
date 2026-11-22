# Website

Public home and signed-in home. Caddy is the only door: `http://app.localhost.com` (local) or `https://app.<domain>` when the edge mode is `vps`. Port 8501 is not published.

```bash
./scripts/proxy-hosts.sh install
./scripts/start.sh portal
```

`start.sh portal` starts Supabase if needed, writes `.nexusflow/portal.env` with the anon key only, builds this image, and starts Caddy. The container calls Auth at `http://kong:8000`. The service-role key stays out of this service.

After sign-in, the left panel lists the lab tools, dbt docs (`http://docs.localhost.com:8080`), and Elementary (`http://elementary.localhost.com:8080`). Each link opens in a new tab. The login page does not show that list. On the laptop, point `app.localhost.com`, `docs.localhost.com`, and `elementary.localhost.com` at `127.0.0.1`, and keep the SSH tunnel that forwards local port 8080 to Caddy on the instance (port 80). Open `http://app.localhost.com:8080`. The dbt and Elementary pages themselves appear only after those reports have been generated.

A refresh keeps the signed-in home. Sign out ends it. The browser cookie is a random id for this site, not the sign-in tokens, and it is not put in the address bar. The tokens stay in the website process.

Sign-up and sign-in use email and password. Passwords must be at least 8 characters and include lowercase, uppercase, a digit, and a symbol. Chat is locked on the public home and accepts messages after sign-in. Answers are connected in a later step. Warehouse counts are the same: the area unlocks now, the numbers come with the metrics work.

Rebuild after a code change with `./scripts/start.sh portal`.
