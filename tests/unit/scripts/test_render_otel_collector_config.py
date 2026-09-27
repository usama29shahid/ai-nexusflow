"""Unit tests for scripts/render-otel-collector-config.py (no Docker)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "render-otel-collector-config.py"


def _load():
    spec = importlib.util.spec_from_file_location("render_otel", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["render_otel"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_render_lake_only(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path)
    monkeypatch.setattr(mod, "OUT", tmp_path / "collector-config.yaml")
    out = mod.render(signoz=False, openobserve=False, clickhouse=False)
    text = out.read_text(encoding="utf-8")
    assert "awss3:" in text
    assert "otlp/signoz:" not in text
    assert "otlphttp/openobserve:" not in text
    assert "prometheus/clickhouse:" not in text
    assert "exporters: [awss3]" in text
    assert "receivers: [otlp, prometheus/self, docker_stats]" in text


def test_render_both_readers(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path)
    monkeypatch.setattr(mod, "OUT", tmp_path / "collector-config.yaml")
    out = mod.render(signoz=True, openobserve=True, clickhouse=False)
    text = out.read_text(encoding="utf-8")
    assert "otlp/signoz:" in text
    assert "otlphttp/openobserve:" in text
    assert "exporters: [awss3, otlp/signoz, otlphttp/openobserve]" in text
    assert "prometheus/clickhouse:" not in text


def test_render_clickhouse_scrape(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "OUT_DIR", tmp_path)
    monkeypatch.setattr(mod, "OUT", tmp_path / "collector-config.yaml")
    out = mod.render(signoz=False, openobserve=False, clickhouse=True)
    text = out.read_text(encoding="utf-8")
    assert "prometheus/clickhouse:" in text
    assert "clickhouse:9363" in text
    assert (
        "receivers: [otlp, prometheus/self, prometheus/clickhouse, docker_stats]"
        in text
    )
