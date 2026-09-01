# common/observability

Host-side SDK for the observability data lake (`nexus-telemetry-{env}`).

Pipeline code imports this package only — never SigNoz, OpenMetadata, or Elementary directly.

## Direct MinIO writes

- `publish_run_summary()` → `summaries/runs/{run_id}.json`
- `copy_dbt_artifacts()` → `artifacts/dbt/{branch}/{run_id}/`
- `publish_pipeline_event()` → `events/pipeline/...` JSONL

## OTLP (traces, metrics, structured logs)

Point the OpenTelemetry SDK at the local Collector:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4317
```

The Collector exports batches to `nexus-telemetry-{env}/otel/`.

See [docs/observability.md](../../docs/observability.md).
