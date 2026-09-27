# OpenObserve (profile: openobserve) — backlog item **2.1**

Single-binary OSS image (`openobserve/openobserve:v1.0.4`). **Reader only** — system of record remains MinIO `nexus-telemetry-{env}`. SigNoz (item 2) stays available for comparison.

| | |
| --- | --- |
| UI | http://127.0.0.1:5080 (override `OPENOBSERVE_UI_PORT`) |
| Proxy | `http://openobserve.${NEXUS_PUBLIC_HOST}` when profile `proxy` is up |
| OTLP HTTP (Compose) | `http://openobserve:5080/api/default/v1/{traces,metrics,logs}` + Basic auth |
| Host pipelines | Send OTLP to nexus collector: `http://127.0.0.1:4317` |
| Lake replay | `./scripts/observability-ingest.sh openobserve` (default `--signals traces,logs,events`; add `metrics` explicitly). Transient failures retry; permanent payload errors get `indexes/openobserve/*.rejected` (use `--force` to re-try; success clears `.rejected`). |
| Dashboards | `./scripts/openobserve-bootstrap.sh` |
| Retention (compact) | `OPENOBSERVE_RETENTION_DAYS` (default **90**) → `ZO_COMPACT_DATA_RETENTION_DAYS` |
| Ingest age window | `OPENOBSERVE_INGEST_ALLOWED_HOURS` (default **2160** = 90d) → `ZO_INGEST_ALLOWED_UPTO` — OO’s built-in default is only **5 hours**; without this, lake replay of older traces/logs is rejected |

## Ready to use

**Always start with `./scripts/start.sh openobserve`.** That generates `ZO_ROOT_USER_*` in `.env` when `NEXUS_SECRETS_BACKEND=env`, or seeds/reads Vault KV `openobserve` when `vault`. Compose uses soft defaults for those vars (not `:?`) so other `docker compose` commands still parse; `start.sh` refuses to start the container if they are empty.

```bash
./scripts/start.sh openobserve
./scripts/openobserve-bootstrap.sh
uv run python branches/dlt_dbt_clickhouse/dlt/route/products.py
# Traces: service_name = nexusflow.dlt ; attribute nexus.run_id
./scripts/observability-ingest.sh openobserve   # backfill last 24h
```

### Credentials

| Backend | Source |
| --- | --- |
| `env` | `.env` `ZO_ROOT_USER_EMAIL` / `ZO_ROOT_USER_PASSWORD` (auto-generated on first start) |
| `vault` | KV `secret/nexusflow/{env}/openobserve` → Agent `secrets.env` |

Collector OTLP forward uses the same password via `OPENOBSERVE_OTLP_BASIC_AUTH` (set by `start.sh`).

### Dashboards in this repo

| File | Title |
| --- | --- |
| `route-products.json` | Nexus Route products |
| `opentelemetry-collector.json` | OpenTelemetry Collector |
| `uptime-monitoring.json` | Uptime Monitoring |
| `ingestion.json` | Ingestion |
| `docker-container-metrics.json` | Docker Container Metrics (community) |
| `airflow.json` | Airflow (community) |
| `clickhouse-overview.json` | ClickHouse overview |

Community JSON is Apache-2.0 from [openobserve/dashboards](https://github.com/openobserve/dashboards). Retune PromQL stream names after the first live scrape if panels are empty.

### Collector signals for Docker / ClickHouse / Airflow

- `docker_stats` on always-on collector (`docker.sock` read-only)
- ClickHouse Prometheus `:9363` (Compose network only; not host-published)
- Airflow 3.3 `AIRFLOW__METRICS__OTEL_*` → collector `:4318`

See [docs/observability.md](../../docs/observability.md) and [docs/backlog.md](../../docs/backlog.md) item **2.1**.
