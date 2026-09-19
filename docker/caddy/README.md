# Caddy edge proxy

Compose profile **`proxy`**. Shared routes in `sites.caddy`; TLS mode from **`NEXUS_EDGE_MODE`** (no hand-edit for HTTPS).

| | Local | VPS (Phase 2) |
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

Local: each tool’s own login.  
Before VPS: gate `docs` / `elementary` / future home — [edge-proxy auth](../../docs/edge-proxy.md#auth-locked-intent).

## VPS (Phase 2 — automated)

Terraform/Actions set on the server (no SSH edit of Caddyfile):

```bash
NEXUS_EDGE_MODE=vps
NEXUS_PUBLIC_HOST=example.com
NEXUS_CADDY_SITE_SCHEME=          # empty — http:// is rejected
NEXUS_CADDY_ACME_EMAIL=ops@example.com
# Backends default to 127.0.0.1 in Compose; never set 0.0.0.0 on VPS
# NEXUS_PUBLISH_BIND=127.0.0.1
```

Full checklist: [deployment contract](../../docs/edge-proxy.md#deployment-contract-terraform--github-actions--phase-2).

**Debug (agents):** if Caddy exits with `caddy: fatal:` about scheme, ACME email, or `NEXUS_PUBLISH_BIND`, or backends look public after a failed proxy start — see [Debug: Caddy exit / NEXUS_PUBLISH_BIND](../../docs/edge-proxy.md#debug-caddy-exit--nexus_publish_bind-for-agents).
