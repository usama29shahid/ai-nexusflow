"""OpenTelemetry helpers — host pipelines export to nexus otel-collector only."""

from __future__ import annotations

import sys
import time
from typing import Any

from common.observability.config import nexus_env, otlp_endpoint
from common.observability.lake import publish_pipeline_event

_tracer = None
_meter = None
_trace_provider = None
_meter_provider = None
_logger_provider = None
_rows_counter = None


def _ensure_providers(service_name: str = "nexusflow", **resource_attrs: str) -> None:
    """Idempotent Tracer/Meter/Logger providers exporting OTLP to the collector."""
    global _tracer, _meter, _trace_provider, _meter_provider, _logger_provider, _rows_counter
    if (
        _trace_provider is not None
        and _meter_provider is not None
        and _logger_provider is not None
    ):
        return

    from opentelemetry import _logs, metrics, trace
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
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

    if _logger_provider is None:
        log_provider = LoggerProvider(resource=resource)
        log_provider.add_log_record_processor(
            BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, insecure=True))
        )
        _logs.set_logger_provider(log_provider)
        _logger_provider = log_provider


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
    if _logger_provider is not None:
        _logger_provider.force_flush(timeout_millis)


def emit_otlp_log(
    body: str,
    *,
    severity: str = "INFO",
    attributes: dict[str, Any] | None = None,
    service_name: str = "nexusflow",
) -> None:
    """Best-effort OTLP log record via the collector (does not raise)."""
    try:
        from opentelemetry import _logs
        from opentelemetry._logs import LogRecord, SeverityNumber

        _ensure_providers(service_name)
        severity_map = {
            "DEBUG": SeverityNumber.DEBUG,
            "INFO": SeverityNumber.INFO,
            "WARN": SeverityNumber.WARN,
            "WARNING": SeverityNumber.WARN,
            "ERROR": SeverityNumber.ERROR,
        }
        now_ns = time.time_ns()
        logger = _logs.get_logger(service_name)
        logger.emit(
            LogRecord(
                timestamp=now_ns,
                observed_timestamp=now_ns,
                severity_number=severity_map.get(severity.upper(), SeverityNumber.INFO),
                severity_text=severity.upper(),
                body=body,
                attributes={k: v for k, v in (attributes or {}).items() if v is not None},
            )
        )
        _force_flush()
    except Exception as exc:  # noqa: BLE001
        print(
            f"WARNING: OTLP log emit failed (collector down or misconfigured): {exc}",
            file=sys.stderr,
        )


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
    """Best-effort OTLP span + log + rows counter for a dlt load (does not raise)."""
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

        emit_otlp_log(
            f"{event_type} pipeline={pipeline_name} status={status} rows={int(row_count or 0)}",
            severity="INFO" if status == "ok" else "ERROR",
            attributes=attrs,
            service_name="nexusflow.dlt",
        )

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
