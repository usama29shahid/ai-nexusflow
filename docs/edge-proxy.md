# Edge proxy (Caddy + subdomains)

**Status:** local path implemented (Compose profile `proxy` — [`docker/caddy/`](../docker/caddy/)). **VPS / Terraform path is a separate contract** (backlog item **10**) — do not treat local hosts + HTTP as production.

Public hostname for the capstone is intentional. That does **not** mean raw Compose ports on a VPS IP.

## Locked decisions (both modes)

- **Caddy**, not nginx (unless you already know nginx). Subdomains, not paths (`airflow.…`, never `/airflow`).
- Compose profile **`proxy`** (platform, not a data branch). Upstreams use Docker DNS (`airflow-api-server:8080`, `minio:9001`, …).
- Airflow 3 needs `AIRFLOW__API__BASE_URL` (or `AIRFLOW__WEBSERVER__BASE_URL` fallback) + `ENABLE_PROXY_FIX` when behind Caddy; strong unique admin password when public.
- ELT runs in `nexus-elt` from the **scheduler** only (`docker.sock` not on the api-server).
- **Never publish:** OTel, ClickHouse native `:9000`, Spark Thrift, MinIO S3 API, OM Postgres/ES/ingestion, Polaris mgmt `:8182`, Airflow Postgres, Vault unseal/root.

## Local vs VPS (keep separate)

| Concern | **Local** (`NEXUS_EDGE_MODE=local`) | **VPS** (`NEXUS_EDGE_MODE=vps`) |
| --- | --- | --- |
| Who configures it | Developer on WSL | Terraform + deploy workflow (backlog **10**); not copy-paste of WSL `.env` |
| Name service | `./scripts/proxy-hosts.sh` (+ Windows hosts if browser is on Windows) | **DNS A records** (or wildcard). **No** `/etc/hosts` as production DNS |
| `NEXUS_PUBLIC_HOST` | `localhost.com` | Real domain, e.g. `example.com` |
| TLS | HTTP only (`Caddyfile.local`, `auto_https off`; scheme defaults to `http://`) | HTTPS + Let’s Encrypt (`Caddyfile.vps` selected by `NEXUS_EDGE_MODE=vps`; empty site scheme + `NEXUS_CADDY_ACME_EMAIL`) |
| Ports exposed | `./scripts/start.sh` defaults backends to `0.0.0.0`; raw Compose defaults to `127.0.0.1` | Firewall **22, 80, 443**; backends **`NEXUS_PUBLISH_BIND=127.0.0.1`** (Compose default + start.sh); Caddy public; **start.sh + entrypoint reject** `0.0.0.0` on vps |
| Secrets | `NEXUS_SECRETS_BACKEND=env` OK | **`vault`**; generate Fernet/passwords **on the VPS** ([vault.md](vault.md)) |
| Auth | App logins; static `docs.` / `elementary.` OK on loopback | **Auth gate required** before public DNS (home + Supabase/Google and/or Caddy in front of unauthenticated routes) |
| ClickHouse / Polaris on edge | Local showcase OK | Gate or **omit** from public Caddy |
| `proxy-hosts.sh` | Required for `*.localhost.com` | **Do not** use as the name service |

```text
Local:  http://airflow.localhost.com
VPS:    https://airflow.yourdomain.com
```

Do not “promote” a laptop by opening port 80 on a VPS IP with the local hosts file and HTTP settings. That is a different mode.

## Local quick start

```bash
./scripts/proxy-hosts.sh install
# .env: NEXUS_EDGE_MODE=local
#       NEXUS_PUBLIC_HOST=localhost.com
#       NEXUS_CADDY_SITE_SCHEME=   # empty → entrypoint uses http://
# Add proxy to COMPOSE_PROFILES (or ./scripts/start.sh proxy), then uncomment:
#       AIRFLOW__API__BASE_URL=http://airflow.localhost.com
#       AIRFLOW__WEBSERVER__BASE_URL=http://airflow.localhost.com
#       AIRFLOW__WEBSERVER__ENABLE_PROXY_FIX=True
#       MINIO_BROWSER_REDIRECT_URL=http://minio.localhost.com
# Leave those three commented when Caddy is not running.
./scripts/start.sh proxy
```

`install` / `remove` replace or clear **all** `nexus-edge-proxy` blocks so changing `NEXUS_PUBLIC_HOST` does not leave stale names.

## Auth (locked intent)

**Local:** App login is enough for Airflow / Vault / MinIO / CloudBeaver / etc. Strong passwords; never demo defaults on a shared host.

**Before any public / VPS edge:** gate unauthenticated surfaces (`docs.`, `elementary.`, future home with Supabase + Google auth). Caddy is TLS + routing, not a substitute for app passwords.

## Publish table

| Subdomain | Upstream | Local | VPS |
| --- | --- | --- | --- |
| `airflow.` | Airflow UI | App login | App login + strong password; ProxyFix |
| `minio.` | Console only | App login | App login; S3 API never on edge |
| `cloudbeaver.` | CloudBeaver | App login | App login |
| `vault.` | Vault UI | Optional | Optional; unseal stays SSH |
| `clickhouse.` | HTTP Play | Showcase | Omit or gate |
| `polaris.` | REST `:8181` | Showcase | Omit or gate |
| `trino.` / `spark.` | UIs | As needed. Trino sets `http-server.process-forwarded=true` so Caddy’s `X-Forwarded-For` is accepted | As needed; Thrift never on edge |
| `signoz.` / `openmetadata.` | Readers | App login | App login |
| `docs.` / `elementary.` | Static | Loopback OK | **Auth gate required** |

## Deployment contract (Terraform / GitHub Actions — backlog item 10)

Backlog item **10** is **additive** ([environments.md](environments.md), [backlog.md](backlog.md), [ci-cd.md](ci-cd.md)). **GitHub Actions** is the primary CI/CD path; **Terraform** owns env/DNS/server edge settings on the VPS. Modules and deploy workflows **must** treat edge as first-class and **must not** assume local mode. Local Terraform (backlog **5**) does not require this VPS checklist.

When implementing `infrastructure/terraform/` and VPS deploy Actions, satisfy all of the following (checklist for implementers):

1. **Set `NEXUS_EDGE_MODE=vps`** on the server (Terraform-rendered env or cloud-init). Never leave `local` on a public host.
2. **Set `NEXUS_PUBLIC_HOST`** to the real apex/domain Terraform/DNS owns.
3. **Provision DNS** (A/AAAA per subdomain or wildcard) → VPS public IP. Do not ship `proxy-hosts.sh` as production DNS.
4. **Enable HTTPS via mode, not a hand-edit:** set `NEXUS_EDGE_MODE=vps` (entrypoint loads `Caddyfile.vps`), leave `NEXUS_CADDY_SITE_SCHEME` empty (entrypoint **exits** if it is `http://`), set `NEXUS_CADDY_ACME_EMAIL` (required), open **80/443** for ACME; firewall denies other app ports from the internet.
5. **Bind backends to `127.0.0.1`:** Compose defaults `NEXUS_PUBLISH_BIND` to `127.0.0.1` (safe for raw `docker compose` on a VPS). `./scripts/start.sh` keeps that on vps and opens `0.0.0.0` only for local. Both **`start.sh` (before compose up)** and the Caddy entrypoint **exit** if `vps` + `NEXUS_PUBLISH_BIND=0.0.0.0`. Caddy keeps public 80/443.
6. **Include profile `proxy`** in the VPS Compose profile set used by deploy/`start.sh`.
7. **Render Airflow/MinIO public URLs** for HTTPS, e.g. `AIRFLOW__API__BASE_URL=https://airflow.${NEXUS_PUBLIC_HOST}` (Compose also accepts `AIRFLOW__WEBSERVER__BASE_URL`), `ENABLE_PROXY_FIX=True`, `MINIO_BROWSER_REDIRECT_URL=https://minio.${NEXUS_PUBLIC_HOST}`.
8. **Secrets:** `NEXUS_SECRETS_BACKEND=vault`; generate Fernet, JWT, and admin passwords on that machine — do not copy WSL `.env` ([vault.md](vault.md)).
9. **Auth gate** for `docs.` / `elementary.` / home must exist before pointing public DNS at the box.
10. **Same execution path:** Actions deploy = `git pull` + `./scripts/start.sh` (or documented equivalent). Actions is not a second ELT runner.

Canonical pointers: [ci-cd.md](ci-cd.md), [infrastructure/terraform/README.md](../infrastructure/terraform/README.md).

## Debug: Caddy exit / `NEXUS_PUBLISH_BIND` (for agents)

Use this when `start.sh` or Caddy exits on start, or a VPS edge looks “half up.” Entrypoint: [`docker/caddy/docker-entrypoint.sh`](../docker/caddy/docker-entrypoint.sh). Publish-bind guard: [`scripts/nexus_publish_bind.sh`](../scripts/nexus_publish_bind.sh) (sourced from [`scripts/start.sh`](../scripts/start.sh) `load_env`).

**Fail-closed (intentional `exit 1` on VPS only):**

| Symptom | Cause | Fix |
| --- | --- | --- |
| `start.sh: fatal: … NEXUS_PUBLISH_BIND=0.0.0.0` (before compose) | Explicit public bind in env | Set `NEXUS_PUBLISH_BIND=127.0.0.1` (or omit) |
| `caddy: fatal: … NEXUS_CADDY_SITE_SCHEME=http://` | Laptop HTTP scheme left on VPS | Clear `NEXUS_CADDY_SITE_SCHEME` (empty) |
| `caddy: fatal: NEXUS_CADDY_ACME_EMAIL is required…` | Missing ACME contact | Set `NEXUS_CADDY_ACME_EMAIL` |
| `caddy: fatal: … NEXUS_PUBLISH_BIND=0.0.0.0` (or `::` / `[::]`) | Public bind when Caddy starts (e.g. raw Compose, not `start.sh`) | Same as row 1; recreate backends if already published |

**Local:** these checks do **not** run. `./scripts/start.sh` opening backends on `0.0.0.0` under `NEXUS_EDGE_MODE=local` is expected.

**Residual race (unlikely under automation):** `./scripts/start.sh` refuses a public bind **before** `compose up`, so the usual deploy path never publishes first. Residual only if someone runs **raw** `docker compose` with `vps` + `0.0.0.0` (backends up) and then starts Caddy — Caddy exits, but host ports already published until backends are recreated with `127.0.0.1`.

**Agent checklist when debugging VPS edge:**

1. Confirm `NEXUS_EDGE_MODE=vps` (never leave `local` on a public host).
2. Confirm `NEXUS_PUBLISH_BIND` is `127.0.0.1` or unset — never `0.0.0.0` on VPS.
3. Prefer `./scripts/start.sh` over raw Compose on VPS so the early bind check runs.
4. If Caddy logged the public-bind fatal **and** backends were up first (raw Compose): recreate backends after fixing env.
5. Automated Terraform/Actions deploy that only sets the [deployment contract](#deployment-contract-terraform--github-actions--backlog-item-10) defaults makes the bad-bind path **very unlikely**; treat an explicit `0.0.0.0` on VPS as a misconfiguration.

## Secrets on VPS

Do not copy WSL `.env` or `.nexusflow/` keys. Generate Vault and Airflow Fernet **on that machine**. Set `NEXUS_REPO_ROOT` to that clone path. `.env.example` stays placeholders.

## Sequence

1. ~~Airflow ELT-job-image on main~~.
2. ~~Local Caddy + `proxy` profile + hosts script~~ (this slice).
3. Keep local **production-shaped** (same scripts, names, images, edge routes) — [ci-cd.md](ci-cd.md).
4. Auth gate (home + Supabase/Google and/or Caddy for static routes) — **before** public DNS.
5. Backlog item **10**: GitHub Actions + Terraform (`NEXUS_EDGE_MODE=vps`, DNS, HTTPS, Vault, `127.0.0.1` binds) — day-one deploy automated via the contract above.
