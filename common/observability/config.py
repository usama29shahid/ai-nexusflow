"""Environment-backed observability settings."""

from __future__ import annotations

import os


def nexus_env() -> str:
    return os.environ.get("NEXUS_ENV", "dev")


def telemetry_bucket() -> str:
    return f"nexus-telemetry-{nexus_env()}"


def minio_endpoint() -> str:
    port = os.environ.get("MINIO_API_PORT", "9002")
    return os.environ.get("MINIO_ENDPOINT_URL", f"http://localhost:{port}")


def otlp_endpoint() -> str:
    return os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4317")


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
