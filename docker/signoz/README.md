# SigNoz (profile: signoz)

Standalone stack for pipeline trace UI. **Reader only** — system of record remains MinIO `nexus-telemetry-{env}`.

| | |
| --- | --- |
| UI | http://127.0.0.1:3301 (override `SIGNOZ_UI_PORT`) |
| OTLP (internal) | `signoz:4317` (gRPC) / `signoz:4318` (HTTP) — nexus `otel-collector` forwards a copy when this profile is up |
| Host pipelines | Send OTLP to nexus collector: `http://127.0.0.1:4317` |
| Lake replay | `./scripts/observability-ingest.sh signoz` |
| Dashboard | **Nexus Route products** — `./scripts/signoz-bootstrap.sh` (not on every start) |

## Ready to use (backlog item 2)

**Always start with `./scripts/start.sh signoz`.** Do not use bare `COMPOSE_PROFILES=signoz docker compose up` unless `SIGNOZ_TOKENIZER_JWT_SECRET` is already in `.env`. Compose requires that variable (`:?`); `start.sh` generates and writes it when missing.

```bash
./scripts/start.sh signoz          # starts profile, syncs collector, ensures OTLP (:4318)
./scripts/signoz-bootstrap.sh      # optional: needs SIGNOZ_API_KEY (or SIGNOZ_BOOTSTRAP_SQLITE=1)
uv run python branches/dlt_dbt_clickhouse/dlt/route/products.py
# Traces: serviceName = nexusflow.dlt ; attribute nexus.run_id
# Dashboard: Dashboards → Nexus Route products
./scripts/observability-ingest.sh signoz   # backfill last 24h
# After a SigNoz volume wipe / empty panels:
./scripts/observability-ingest.sh signoz -- --force --since 2026-09-01T00:00:00Z
# Or set SIGNOZ_AUTO_REPLAY=1 before start.sh signoz (replays 14d when index is empty)
```

### What each script does

1. [`scripts/signoz-ensure.sh`](../../scripts/signoz-ensure.sh) — creates missing `clickhouse` user if needed, starts telemetrystore + OTLP ingester, waits for `:4318`. Warns (or auto-replays) when the trace index is empty.
2. [`scripts/signoz-bootstrap.sh`](../../scripts/signoz-bootstrap.sh) — upserts [`dashboards/route-products.json`](dashboards/route-products.json) via API when `SIGNOZ_API_KEY` or email/password are set (POST create, or PUT update if the title already exists; never deletes on failure). Edit that JSON in git, then re-run bootstrap to push panel changes. SQLite metastore edits require `SIGNOZ_BOOTSTRAP_SQLITE=1` (stops UI briefly; last resort).

Compose health requires **both** UI `/api/v1/health` and OTLP `:4318`. UI-only “healthy” is not enough.

See [docs/observability.md](../../docs/observability.md) and [docs/backlog.md](../../docs/backlog.md).
