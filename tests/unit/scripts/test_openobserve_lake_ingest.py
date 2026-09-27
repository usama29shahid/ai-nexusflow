"""Unit tests for scripts/openobserve_lake_ingest.py (no Docker / MinIO)."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "openobserve_lake_ingest.py"


def _load():
    spec = importlib.util.spec_from_file_location("oo_lake", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["oo_lake"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_parse_lake_key_traces():
    mod = _load()
    obj = mod.parse_lake_key("otel/2026/09/24/19/46/traces_abc.json")
    assert obj is not None
    assert obj.signal == "traces"
    assert obj.partition_time == datetime(2026, 9, 24, 19, 46, tzinfo=timezone.utc)


def test_parse_lake_key_rejects_noise():
    mod = _load()
    assert mod.parse_lake_key("events/pipeline/x.json") is None
    assert mod.parse_lake_key("otel/bad/key.json") is None


def test_marker_key():
    mod = _load()
    assert mod.marker_key("otel/2026/09/24/19/46/traces_a.json").startswith(
        "indexes/openobserve/"
    )
    assert mod.reject_marker_key("otel/a.json").endswith(".rejected")


def test_is_transient_otlp_failure():
    mod = _load()
    assert mod.is_transient_otlp_failure(
        RuntimeError("rejected due to exceeding the allowed retention period")
    )
    assert mod.is_transient_otlp_failure(
        RuntimeError("OpenObserve OTLP POST failed HTTP 503: MemoryTableOverflowError")
    )
    assert mod.is_transient_otlp_failure(RuntimeError("HTTP 401 unauthorized"))
    assert mod.is_transient_otlp_failure(RuntimeError("connect timeout while reading"))
    assert not mod.is_transient_otlp_failure(
        RuntimeError('failed HTTP 400: missing field `values`')
    )
    assert not mod.is_transient_otlp_failure(RuntimeError("invalid JSON schema"))
    # Broad words alone must not count as transient (avoid false retries).
    assert not mod.is_transient_otlp_failure(RuntimeError("service unavailable forever"))
    assert not mod.is_transient_otlp_failure(RuntimeError("timeout policy denied"))


def test_sanitize_empty_array_value():
    mod = _load()
    raw = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "attributes": [
                                    {"key": "empty", "value": {"arrayValue": {}}},
                                    {
                                        "key": "ok",
                                        "value": {
                                            "arrayValue": {
                                                "values": [{"stringValue": "a"}]
                                            }
                                        },
                                    },
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }
    fixed = mod.sanitize_otlp_json(raw)
    attrs = fixed["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["attributes"]
    assert attrs[0]["value"]["arrayValue"] == {"values": []}
    assert attrs[1]["value"]["arrayValue"]["values"][0]["stringValue"] == "a"


def test_prepare_otlp_body_rewrites_json():
    mod = _load()
    body = b'{"value":{"arrayValue":{}}}'
    out = json.loads(mod.prepare_otlp_body(body))
    assert out == {"value": {"arrayValue": {"values": []}}}


def test_event_in_window():
    mod = _load()
    since = datetime(2026, 9, 20, tzinfo=timezone.utc)
    until = datetime(2026, 9, 27, tzinfo=timezone.utc)
    key = "events/pipeline/dt=2026-09-25/branch=x/run_id=y/a.jsonl"
    assert mod.event_in_window(key, since=since, until=until) is True
    assert (
        mod.event_in_window(
            "events/pipeline/dt=2026-09-10/branch=x/a.jsonl",
            since=since,
            until=until,
        )
        is False
    )
    assert mod.event_in_window("events/pipeline/no-dt/a.jsonl", since=since, until=until) is False


def test_default_signals_omit_metrics():
    mod = _load()
    parser = mod.build_parser()
    args = parser.parse_args([])
    signals = {s.strip() for s in args.signals.split(",") if s.strip()}
    assert signals == {"traces", "logs", "events"}
    assert "metrics" not in signals


def test_openobserve_reachable_requires_healthz():
    mod = _load()
    with patch.object(mod, "oo_base_url", return_value="http://127.0.0.1:5080"):
        with patch("urllib.request.urlopen", side_effect=OSError("refused")):
            assert mod.openobserve_reachable() is False


def test_post_otlp_partial_success_raises():
    mod = _load()

    class _Resp:
        status = 206

        def read(self):
            return json.dumps(
                {
                    "partialSuccess": {
                        "rejectedSpans": 2,
                        "errorMessage": "retention",
                    }
                }
            ).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with patch.object(mod, "oo_auth_header", return_value="Basic x"):
        with patch.object(mod, "oo_base_url", return_value="http://oo"):
            with patch("urllib.request.urlopen", return_value=_Resp()):
                try:
                    mod.post_otlp(signal="traces", body=b'{"resourceSpans":[]}')
                    raise AssertionError("expected RuntimeError")
                except RuntimeError as exc:
                    assert "rejected" in str(exc).lower()


def test_pipeline_event_uses_severity_text():
    mod = _load()
    body = json.loads(
        mod.pipeline_event_to_otlp_logs(
            {
                "event_type": "dlt.load.completed",
                "status": "ok",
                "recorded_at": "2026-09-27T00:00:00Z",
                "nexus.component": "dlt",
            }
        ).decode()
    )
    rec = body["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]
    assert rec["severityText"] == "INFO"
    assert "severityNumberText" not in rec
