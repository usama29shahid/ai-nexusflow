"""Laptop addresses for the signed-in tool list. UI links only."""

from __future__ import annotations

TOOL_LINKS: tuple[tuple[str, str], ...] = (
    ("Vault", "http://127.0.0.1:8200"),
    ("ClickHouse HTTP", "http://127.0.0.1:8123"),
    ("CloudBeaver", "http://127.0.0.1:8978"),
    ("MinIO console", "http://127.0.0.1:9001"),
    ("Airflow", "http://127.0.0.1:8081"),
    ("OpenObserve", "http://127.0.0.1:5080"),
    ("OpenMetadata", "http://127.0.0.1:8585"),
    ("Cube", "http://127.0.0.1:4000"),
    ("Supabase Studio", "http://127.0.0.1:3001"),
    ("dbt docs", "http://docs.localhost.com:8080"),
    ("Elementary", "http://elementary.localhost.com:8080"),
)
