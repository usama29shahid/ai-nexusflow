# OTel Collector

Always-on with MinIO (no Compose profile). Image: `otel/opentelemetry-collector-contrib:0.128.0`. Receives OTLP on gRPC `:4317` and HTTP `:4318`; exports batches to `nexus-telemetry-{env}/otel/` via the S3-compatible MinIO endpoint.

## Config

| File | Role |
| --- | --- |
| `collector-config.yaml` | Hand-maintained **default** mount (receivers + lake `awss3`). Safe for bare `docker compose up`. |
| `.generated/collector-config.yaml` | Written by `scripts/render-otel-collector-config.py` — lake + optional SigNoz / OpenObserve exporters + ClickHouse scrape when that profile is up |

Compose default: `OTEL_COLLECTOR_CONFIG=collector-config.yaml`. `./scripts/start.sh` always renders then recreates `otel-collector` with `OTEL_COLLECTOR_CONFIG=.generated/collector-config.yaml`. Stopping one reader re-renders without dropping the other.

## Ops receivers

| Receiver | When | Pipeline | Purpose |
| --- | --- | --- | --- |
| `prometheus/self` | always (base) | `metrics` | Collector `otelcol_*` on `127.0.0.1:8888` |
| `docker_stats` | always (base) | `metrics` | Container CPU/mem/net/IO (`docker.sock` read-only) |
| `prometheus/clickhouse` | **render when `clickhouse` running** | `metrics` | Warehouse `clickhouse:9363` (Compose DNS; not host-published) |
| `httpcheck` | always (base) | `metrics/uptime` | Always-on MinIO + collector probes (`service.name=nexusflow.uptime`) |

**httpcheck / ClickHouse scrape:** optional profiles are not probed when stopped (no lake flood of scrape failures).

**Static check:** `./scripts/check-observability-static.sh`

| Check | Command |
| --- | --- |
| Health | `curl -sf http://127.0.0.1:13133/` |
| Full smoke | `./scripts/observability-smoke.sh` |

Host pipelines:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4317
```

See [docs/observability.md](../../docs/observability.md).
