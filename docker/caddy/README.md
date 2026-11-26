# Caddy edge proxy

Compose profile **`proxy`**. Shared routes in `sites.caddy`; TLS mode from **`NEXUS_EDGE_MODE`** (no hand-edit for HTTPS).

| | Local | VPS (backlog **10**) |
| --- | --- | --- |
| Flag | `NEXUS_EDGE_MODE=local` | `NEXUS_EDGE_MODE=vps` (Terraform/Actions) |
| Caddyfile | `Caddyfile.local` (`auto_https off`) | `Caddyfile.vps` (Let’s Encrypt) |
| Names | `./scripts/proxy-hosts.sh` | DNS A records |
| Scheme | `http://` (entrypoint default) | empty + `NEXUS_CADDY_ACME_EMAIL` |

Entrypoint: [`docker-entrypoint.sh`](docker-entrypoint.sh) copies the mode file at start.

## Local (WSL)

```bash
./scripts/proxy-hosts.sh install
# .env: NEXUS_EDGE_MODE=local
# Uncomment Airflow/MinIO proxy URLs only while Caddy is up — see .env.example
./scripts/start.sh proxy
```

Open e.g. `http://airflow.localhost.com`. Windows browser → also update Windows hosts (`./scripts/proxy-hosts.sh print`).

## Auth

The image is `caddy:2.9-alpine` plus `htpasswd`, so the popup password is hashed from stdin at start.

`docs.`, `elementary.`, and `cube.` share one browser popup. Cube's playground replaces the `Authorization` header on its own API calls, so a successful popup sets a host-only `docs_gate` cookie that those calls send. A failed sign-in does not set that cookie. The cookie name/value is matched exactly (`header_regexp`, not a substring). It matches only the current 24-hour window (`Max-Age` is the time left in that window). Caddy rewrites and reloads that Max-Age about hourly (and at the window boundary), skips reload when nothing changed, and retries a failed refresh after 30s. Local reloads keep `NEXUS_CADDY_SITE_SCHEME=http://` so the listener stays on `:80`. A copied cookie is rejected after the window ends. The user and password are Vault `secret/nexusflow/{env}/docs_basic_auth`. Other hostnames keep their own logins. `cube.` proxies `cube:4000` on the Compose network. The host publishes neither playground port 4000 nor SQL port 15432. HTTP regression checks: `uv run python tests/integration/caddy_docs_auth_smoke.py`. See [edge-proxy auth](../../docs/edge-proxy.md#auth-locked-intent).

## VPS (backlog item 10 — automated)

Terraform/Actions set on the server (no SSH edit of Caddyfile):

```bash
NEXUS_EDGE_MODE=vps
NEXUS_PUBLIC_HOST=example.com
NEXUS_CADDY_SITE_SCHEME=          # empty — http:// is rejected
NEXUS_CADDY_ACME_EMAIL=ops@example.com
# Backends default to 127.0.0.1 in Compose; never set 0.0.0.0 on VPS
# NEXUS_PUBLISH_BIND=127.0.0.1
```

Full checklist: [deployment contract](../../docs/edge-proxy.md#deployment-contract-terraform--github-actions--backlog-item-10).

**Debug (agents):** if Caddy exits with `caddy: fatal:` about scheme, ACME email, or `NEXUS_PUBLISH_BIND`, or backends look public after a failed proxy start — see [Debug: Caddy exit / NEXUS_PUBLISH_BIND](../../docs/edge-proxy.md#debug-caddy-exit--nexus_publish_bind-for-agents).
