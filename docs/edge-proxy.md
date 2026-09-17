# Edge proxy (Caddy + subdomains)

**Status: designed, not implemented.** Do not mix this into the Airflow ELT-job-image PR. Implement as a **separate** slice after `route_clickhouse_products` is closed on the job image. Test on WSL first (`*.localhost`), then the VPS.

Public hostname for the capstone is an intentional goal. That does **not** mean raw Compose ports on the VPS IP.

## Locked decisions

- **Caddy**, not nginx (unless you already know nginx). One Caddyfile. Automatic HTTPS on the VPS.
- **Subdomains**, not paths. Use `airflow.yourdomain.com`, never `yourdomain.com/airflow`. These UIs assume they live at `/`.
- Same file locally and on the VPS. Only `NEXUS_PUBLIC_HOST` changes (`localhost` vs `yourdomain.com`).
- Compose profile **`proxy`** (platform, not a data branch). Prefer Docker DNS to the service (`airflow-webserver:8080`), or `127.0.0.1:<port>` if Caddy is on the host.
- Keep current localhost binds (Airflow `:8081`, Vault, OTel, CloudBeaver, SigNoz, OM). When the proxy lands, bind ClickHouse / MinIO / Trino host ports to `127.0.0.1` as well. Firewall on VPS: **22, 80, 443** only.
- Airflow does **not** need a rewrite. When Caddy is up, set `AIRFLOW__WEBSERVER__BASE_URL` (and ProxyFix / `COOKIE_SECURE` on HTTPS). Subdomain → `https://airflow.yourdomain.com` (no `/airflow` path).
- Host-exec (legacy SSH) is retired for DAGs; ELT runs in `nexus-elt` job containers from the **scheduler** only (`docker.sock` is not mounted on the webserver). Public Airflow still requires a strong unique admin password.

```text
Local:  http://airflow.localhost
VPS:    https://airflow.yourdomain.com
```

Browsers resolve `*.localhost` to `127.0.0.1`. VPS: one **A record per subdomain** (or `*.yourdomain.com`). Individual A records are easier than wildcard DNS-01.

## Publish (with each app’s own login)

| Subdomain | Upstream | Notes |
| --- | --- | --- |
| `airflow.` | Airflow UI | Extra: `BASE_URL` + ProxyFix when proxied |
| `signoz.` | SigNoz `:3301` | |
| `openmetadata.` | OM `:8585` | |
| `minio.` | MinIO **console** only | Extra Caddy basic auth |
| `trino.` | Trino UI | |
| `sql.` | CloudBeaver | Extra Caddy basic auth (full SQL) |
| `docs.` | Static `branches/dlt_dbt_clickhouse/target/` | After `dbt docs generate`. Do not run `dbt docs serve` |
| `elementary.` | Static `edr_target/elementary_report.html` | Last **successful** generate only |
| `vault.` | Vault **UI** on `127.0.0.1:8200` | Extra Caddy basic auth. Unseal/root stay SSH. Optional to omit |

## Never publish

OTel `:4317`/`:4318`, ClickHouse native `:9000`, Spark Thrift, MinIO **S3 API** `:9002`, OpenMetadata Postgres/ES/ingestion, Polaris management, Airflow Postgres, Vault unseal / root token.

## Secrets / VPS

Do not copy WSL `.env` or `.nexusflow/` keys. Generate Vault and Airflow Fernet **on that machine**. Set `NEXUS_REPO_ROOT` to that clone path. `.env.example` stays placeholders. `NEXUS_SECRETS_BACKEND=vault` on the VPS.

## Sequence

1. Close Airflow `feature/airflow-route-products` (DAGs / SSH / lake closer) — no Caddyfile in that commit.
2. New slice: `docker/caddy/` + profile `proxy` + Caddyfile + localhost binds + short ops notes.
3. WSL: `NEXUS_PUBLIC_HOST=localhost`, Caddy `:80`.
4. VPS: DNS + Caddy `:443` + Let’s Encrypt.
