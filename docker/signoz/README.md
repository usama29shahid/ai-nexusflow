# SigNoz (profile: signoz)

Standalone stack for pipeline trace UI. **Reader only** — system of record remains MinIO `nexus-telemetry-{env}`.

| | |
| --- | --- |
| UI | http://127.0.0.1:3301 (override `SIGNOZ_UI_PORT`) |
| OTLP (internal) | `signoz:4317` — nexus `otel-collector` forwards a copy when this profile is up |
| Host pipelines | Send OTLP to nexus collector: `http://127.0.0.1:4317` |
| Lake replay | `./scripts/observability-ingest.sh signoz` — **implement in backlog item 2** (stub today) |

**Backlog item 2** delivers: live OTLP visibility for `products` runs, dashboards/saved views, and lake→SigNoz ingest. See [docs/backlog.md](../../docs/backlog.md).

Start:

```bash
./scripts/start.sh signoz
# or
COMPOSE_PROFILES=signoz docker compose up -d
```

See [docs/observability.md](../../docs/observability.md).
