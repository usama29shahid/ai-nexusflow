"""OpenTelemetry helpers — host pipelines export to nexus otel-collector only."""

from __future__ import annotations

from typing import Any

from common.observability.config import nexus_env, otlp_endpoint
from common.observability.lake import publish_pipeline_event

_tracer = None


def get_tracer(name: str = "nexusflow", **resource_attrs: str):
    """Return a tracer that exports spans to the local OTel Collector."""
    global _tracer
    if _tracer is not None:
        return _tracer

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    attrs = {"nexus.env": nexus_env(), "service.name": name}
    attrs.update({k: v for k, v in resource_attrs.items() if v})
    resource = Resource.create(attrs)
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=otlp_endpoint(), insecure=True)
        )
    )
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(name)
    return _tracer


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
