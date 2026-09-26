# OTel Collector

Always-on with MinIO (no Compose profile). Image: `otel/opentelemetry-collector-contrib:0.128.0`. Receives OTLP on gRPC `:4317` and HTTP `:4318`; exports batches to `nexus-telemetry-{env}/otel/` via the S3-compatible MinIO endpoint.

## Config variants

| File | When | Exporters |
| --- | --- | --- |
| `collector-config.yaml` | Default (SigNoz off) | Lake only (`awss3`) |
| `collector-config.signoz.yaml` | SigNoz profile running | Lake + SigNoz (`otlp/signoz`) |

`start.sh` sets `OTEL_COLLECTOR_CONFIG` and recreates `otel-collector` when SigNoz starts or stops. See [docs/observability.md](../../docs/observability.md).

Keep the two files in sync for ops receivers (self-metrics + httpcheck). Only the SigNoz exporter list differs.

## Ops receivers (always on)

| Receiver | Pipeline | Purpose |
| --- | --- | --- |
| `prometheus/self` | `metrics` | Scrape collector `otelcol_*` on `127.0.0.1:8888` (`service.name=nexusflow.otel-collector`; reader bound to loopback only) |
| `httpcheck` | `metrics/uptime` | Compose-DNS health probes every 60s (`service.name=nexusflow.uptime`) |

**httpcheck targets:** always-on only — `minio` health and `otel-collector:13133`. Optional profiles (ClickHouse, SigNoz, Airflow) are **not** probed by default so stopped stacks do not write failure series into the lake every 60s. On contrib `0.128.0` only default httpcheck metrics emit (`status` / `duration` / `error`).

**Static check:** `./scripts/check-observability-static.sh` (also run by `signoz-bootstrap.sh`) asserts V1 dashboards + identical ops blocks in both collector configs.

**Not enabled here (see [../signoz/README.md](../signoz/README.md) future table):** ClickHouse `:9363` scrape, `docker_stats` / docker.sock.

| Check | Command |
| --- | --- |
| Health | `curl -sf http://127.0.0.1:13133/` |
| OTLP HTTP | `curl -sf -X POST http://127.0.0.1:4318/v1/traces -H 'Content-Type: application/json' -d '{"resourceSpans":[]}'` |
| Full smoke | `./scripts/observability-smoke.sh` |

Host pipelines:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4317
```

Use `common.observability.get_tracer()`, `record_dlt_load()`, or `publish_dlt_load()` (which calls `record_dlt_load`). Lake path uses `s3_partition_format: %Y/%m/%d/%H/%M` under `otel/` (MinIO-safe; avoids default `year=%Y/...` keys).
