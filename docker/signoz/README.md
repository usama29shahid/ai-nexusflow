# SigNoz (profile: signoz)

Standalone stack for pipeline trace UI. **Reader only** — system of record remains MinIO `nexus-telemetry-{env}`.

| | |
| --- | --- |
| UI | http://127.0.0.1:3301 (override `SIGNOZ_UI_PORT`) |
| OTLP (internal) | `signoz:4317` (gRPC) / `signoz:4318` (HTTP) — nexus `otel-collector` forwards a copy when this profile is up |
| Host pipelines | Send OTLP to nexus collector: `http://127.0.0.1:4317` |
| Lake replay | `./scripts/observability-ingest.sh signoz` |
| Dashboards | `./scripts/signoz-bootstrap.sh` upserts every JSON under [`dashboards/`](dashboards/) (not on every start) |

## Ready to use (backlog item 2 + ops dashboards)

**Always start with `./scripts/start.sh signoz`.** Do not use bare `COMPOSE_PROFILES=signoz docker compose up` unless `SIGNOZ_TOKENIZER_JWT_SECRET` is already in `.env`. Compose requires that variable (`:?`); `start.sh` generates and writes it when missing.

```bash
./scripts/start.sh signoz          # starts profile, syncs collector, ensures OTLP (:4318)
./scripts/signoz-bootstrap.sh      # optional: needs SIGNOZ_API_KEY (or SIGNOZ_BOOTSTRAP_SQLITE=1)
uv run python branches/dlt_dbt_clickhouse/dlt/route/products.py
# Traces: serviceName = nexusflow.dlt ; attribute nexus.run_id
# Dashboards: see table below
./scripts/observability-ingest.sh signoz   # backfill last 24h
# After a SigNoz volume wipe / empty panels:
./scripts/observability-ingest.sh signoz -- --force --since 2026-09-01T00:00:00Z
# Or set SIGNOZ_AUTO_REPLAY=1 before start.sh signoz (replays 14d when index is empty)
```

### What each script does

1. [`scripts/signoz-ensure.sh`](../../scripts/signoz-ensure.sh) — creates missing `clickhouse` user if needed, starts telemetrystore + OTLP ingester, waits for `:4318`. Warns (or auto-replays) when the trace index is empty.
2. [`scripts/signoz-bootstrap.sh`](../../scripts/signoz-bootstrap.sh) — upserts **all** [`dashboards/*.json`](dashboards/) via API when `SIGNOZ_API_KEY` or email/password are set (POST create, or PUT update if the title already exists; never deletes on failure). Runs [`scripts/check-observability-static.sh`](../../scripts/check-observability-static.sh) first (V1-only JSON, layout↔widget ids, collector ops sync). Edit JSON in git, re-run bootstrap to push panel changes. SQLite metastore edits require `SIGNOZ_BOOTSTRAP_SQLITE=1` (stops UI briefly; last resort).

Compose health requires **both** UI `/api/v1/health` and OTLP `:4318`. UI-only “healthy” is not enough.

## Dashboards in this repo

Your standalone image reports **`v0.117.1`** today. Community templates must be **V1 / legacy** (`title` + `widgets` + `layout`). **Do not import V2 JSON** (`schemaVersion: v6`) — those need SigNoz **0.135+** and crash the Dashboards UI on 0.117 (“Something went wrong”).

| File | Title | Data needed | When to look |
| --- | --- | --- | --- |
| `route-products.json` | Nexus Route products | Pipeline OTLP (`nexusflow.dlt`) | Warehouse `products` run health |
| `opentelemetry-collector.json` | OpenTelemetry Collector | Collector self-metrics (`otelcol_*_total` as stored in SigNoz; `service.name=nexusflow.otel-collector`) | Drops, queues, export failures to lake/SigNoz |
| `uptime-monitoring.json` | Uptime Monitoring (HTTP Check) | `httpcheck.status` / `httpcheck.duration` (`service.name=nexusflow.uptime`) | Always-on reachability (MinIO, collector) |
| `signoz-ingestion-analysis.json` | Ingestion | Live metrics + traces in SigNoz | Ingest volume by signal / service |

Uptime **service_name** is fixed to `nexusflow.uptime` in queries (no fragile UI variable). Panels use `httpcheck.status` / `httpcheck.duration`. There is no `httpcheck.error` series while probes get an HTTP response — the third panel shows **non-2xx** status matches instead (0 when healthy). Optional profile probes (ClickHouse / SigNoz / Airflow) are omitted from the collector httpcheck list by design.

Ops receivers live in both collector configs ([`../otel/collector-config.yaml`](../otel/collector-config.yaml), [`../otel/collector-config.signoz.yaml`](../otel/collector-config.signoz.yaml)). See [docs/observability.md](../../docs/observability.md).

The **OpenTelemetry Collector**, **Uptime**, and **Ingestion** boards are Nexus-tuned (`clickhouse_sql` against names SigNoz actually stores). Do not replace them with upstream SigNoz community V1/V2 JSON on standalone `v0.117` — those use a builder schema / label columns that show blank tables or red panel errors. **Ingestion** logs panel stays empty until app logs are exported via OTLP (metrics/traces only today); blank `deployment.environment` on the old community board was expected — we do not set that resource attribute.

## Future dashboards (add when the situation matches)

Do **not** enable these by default — they add continuous high-cardinality scrapes or host privilege. Revisit when the trigger below is real.

| Dashboard (SigNoz community) | Trigger | What to wire | Notes |
| --- | --- | --- | --- |
| **ClickHouse overview** (`clickhouse/clickhouse-overview.json`) | Warehouse tuning: insert latency, memory pressure, merge backlog, OOMs under larger loads (endpoints / VPS soak) | Enable CH Prometheus (`config.d` `:9363`), scrape from collector, vendor JSON + bootstrap | Compose-network only — never publish `:9363` publicly |
| **Docker container metrics** (`container-metrics/docker/…`) | VPS RAM/CPU contention across many Compose profiles | Mount `docker.sock` (ro) on `otel-collector`, enable `docker_stats`, vendor JSON | Privilege surface; cost scales with container count. Prefer on-demand `docker stats` until then |
| **Cursor IDE** (`cursor/cursor-dashboard.json`) | Team wants IDE token/tool spend in SigNoz | Host `opentelemetry-hooks` → `127.0.0.1:4317`; on VPS use SSH local-forward — never expose OTLP on Caddy | Not platform/ELT ops; set `IDE_OTEL_MCP_LOG_PAYLOAD=false` (shell stdout is sensitive) |
| **CI/CD** (`cicd/cicd.json`) | GitHub Actions emits semantic CI metrics/traces (backlog item **10**) | Actions → OTLP into collector | Little value until Actions are live |

Upstream templates: [SigNoz/dashboards](https://github.com/SigNoz/dashboards) (Apache-2.0). Use **V1** paths while standalone is below 0.135 (current pin reports `v0.117.1`). Switch to V2 only after upgrading SigNoz.

## VPS notes (backlog item 10)

- Keep backends on `NEXUS_PUBLISH_BIND=127.0.0.1`; httpcheck uses Compose DNS (`minio`, `otel-collector`), not public hostnames.
- Do **not** publish collector OTLP (`:4317`/`:4318`) or ClickHouse Prometheus (`:9363`) on the public edge.
- Cursor (if ever enabled): SSH tunnel to VPS loopback collector, not a public ingest URL.

See [docs/observability.md](../../docs/observability.md) and [docs/backlog.md](../../docs/backlog.md).
