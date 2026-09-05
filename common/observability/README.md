# common/observability

Host-side SDK for the observability data lake (`nexus-telemetry-{env}`).

Pipeline code imports this package only — never SigNoz, OpenMetadata, or Elementary directly.

## Direct MinIO writes

- `publish_run_summary()` → `summaries/runs/{run_id}.json`
- `copy_dbt_artifacts()` → `artifacts/dbt/{branch}/{run_id}/`
- `publish_pipeline_event()` → `events/pipeline/...` JSONL

## OTLP (traces, metrics)

`publish_dlt_load()` also emits a best-effort `dlt.load` span and `nexus.dlt.rows_loaded` counter via the Collector (does not fail the pipeline if the collector is down).

```bash
# default — host → always-on otel-collector
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4317
```

Collector exports batches to `nexus-telemetry-{env}/otel/`. Ensure `otel-collector` is running (`docker compose` with MinIO).

See [docs/observability.md](../../docs/observability.md).
