"""OpenTelemetry helpers — host pipelines export to nexus otel-collector only."""

from __future__ import annotations

import sys
from typing import Any

from common.observability.config import nexus_env, otlp_endpoint
from common.observability.lake import publish_pipeline_event

_tracer = None
_meter = None
_trace_provider = None
_meter_provider = None
_rows_counter = None


def _ensure_providers(service_name: str = "nexusflow", **resource_attrs: str) -> None:
    """Idempotent TracerProvider + MeterProvider exporting OTLP to the collector."""
    global _tracer, _meter, _trace_provider, _meter_provider, _rows_counter
    if _trace_provider is not None and _meter_provider is not None:
        return

    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    attrs = {"nexus.env": nexus_env(), "service.name": service_name}
    attrs.update({k: v for k, v in resource_attrs.items() if v})
    resource = Resource.create(attrs)
    endpoint = otlp_endpoint()

    if _trace_provider is None:
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
        )
        trace.set_tracer_provider(provider)
        _trace_provider = provider
        _tracer = trace.get_tracer(service_name)

    if _meter_provider is None:
        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=endpoint, insecure=True),
            export_interval_millis=5_000,
        )
        m_provider = MeterProvider(resource=resource, metric_readers=[reader])
        metrics.set_meter_provider(m_provider)
        _meter_provider = m_provider
        _meter = metrics.get_meter(service_name)
        _rows_counter = _meter.create_counter(
            name="nexus.dlt.rows_loaded",
            description="Rows loaded by a dlt pipeline run (0 on failed runs)",
            unit="1",
        )


def get_tracer(name: str = "nexusflow", **resource_attrs: str):
    """Return a tracer that exports spans to the local OTel Collector."""
    global _tracer
    _ensure_providers(name, **resource_attrs)
    if _tracer is None:
        from opentelemetry import trace

        _tracer = trace.get_tracer(name)
    return _tracer


def _force_flush(*, timeout_millis: int = 10_000) -> None:
    if _trace_provider is not None:
        _trace_provider.force_flush(timeout_millis)
    if _meter_provider is not None:
        _meter_provider.force_flush(timeout_millis)


def record_dlt_load(
    *,
    run_id: str,
    branch: str,
    component: str,
    pipeline_name: str,
    status: str,
    event_type: str,
    row_count: int = 0,
    source: str | None = None,
    endpoint: str | None = None,
    **extra: Any,
) -> None:
    """Best-effort OTLP span + rows counter for a dlt load (does not raise)."""
    try:
        from opentelemetry.trace import Status, StatusCode

        tracer = get_tracer("nexusflow.dlt")
        attrs: dict[str, Any] = {
            "nexus.run_id": run_id,
            "nexus.env": nexus_env(),
            "nexus.branch": branch,
            "nexus.component": component,
            "pipeline_name": pipeline_name,
            "status": status,
            "event_type": event_type,
            "row_count": int(row_count or 0),
        }
        if source:
            attrs["nexus.source"] = source
        if endpoint:
            attrs["nexus.endpoint"] = endpoint
        for key, value in extra.items():
            if value is not None and key not in attrs:
                attrs[key] = value

        with tracer.start_as_current_span("dlt.load", attributes=attrs) as span:
            if status == "ok":
                span.set_status(Status(StatusCode.OK))
            else:
                span.set_status(Status(StatusCode.ERROR, status))

        if _rows_counter is not None:
            metric_attrs = {
                "nexus.branch": branch,
                "nexus.component": component,
                "pipeline_name": pipeline_name,
                "status": status,
            }
            if source:
                metric_attrs["nexus.source"] = source
            if endpoint:
                metric_attrs["nexus.endpoint"] = endpoint
            _rows_counter.add(int(row_count or 0) if status == "ok" else 0, metric_attrs)

        _force_flush()
    except Exception as exc:  # noqa: BLE001 — lake write is the required path
        print(
            f"WARNING: OTLP emit failed (collector down or misconfigured): {exc}",
            file=sys.stderr,
        )


def emit_event(
    event_type: str,
    *,
    run_id: str,
    branch: str,
    component: str,
    attributes: dict[str, Any] | None = None,
) -> str:
    """Write a nexus.telemetry/v1 event to the lake (required path for pipelines)."""
    return publish_pipeline_event(
        run_id,
        branch=branch,
        component=component,
        event_type=event_type,
        attributes=attributes,
    )
