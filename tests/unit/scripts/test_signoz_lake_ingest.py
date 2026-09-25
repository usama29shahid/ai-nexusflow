"""Unit tests for scripts/signoz_lake_ingest.py (no Docker / MinIO).

Run from repo root:

    uv run python tests/unit/scripts/test_signoz_lake_ingest.py
"""

from __future__ import annotations

import importlib.util
import io
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_MODULE_PATH = REPO_ROOT / "scripts" / "signoz_lake_ingest.py"
_SPEC = importlib.util.spec_from_file_location("signoz_lake_ingest", _MODULE_PATH)
assert _SPEC and _SPEC.loader
ingest = importlib.util.module_from_spec(_SPEC)
sys.modules["signoz_lake_ingest"] = ingest
_SPEC.loader.exec_module(ingest)


class ParseLakeKeyTest(unittest.TestCase):
    def test_traces_key(self) -> None:
        obj = ingest.parse_lake_key("otel/2026/09/24/19/46/traces_abc.json")
        assert obj is not None
        self.assertEqual(obj.signal, "traces")
        self.assertEqual(
            obj.partition_time,
            datetime(2026, 9, 24, 19, 46, tzinfo=timezone.utc),
        )

    def test_metrics_and_logs(self) -> None:
        m = ingest.parse_lake_key("otel/2026/01/02/03/04/metrics_x.json")
        l = ingest.parse_lake_key("otel/2026/01/02/03/04/logs_y.json")
        assert m is not None and l is not None
        self.assertEqual(m.signal, "metrics")
        self.assertEqual(l.signal, "logs")

    def test_rejects_non_otel(self) -> None:
        self.assertIsNone(ingest.parse_lake_key("events/pipeline/foo.json"))
        self.assertIsNone(ingest.parse_lake_key("otel/bad/key.json"))
        self.assertIsNone(ingest.parse_lake_key("otel/2026/09/24/19/46/other_x.json"))


class WindowAndMarkerTest(unittest.TestCase):
    def test_in_window_half_open(self) -> None:
        obj = ingest.parse_lake_key("otel/2026/09/24/12/00/traces_a.json")
        assert obj is not None
        since = datetime(2026, 9, 24, 11, 0, tzinfo=timezone.utc)
        until = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
        self.assertFalse(ingest.in_window(obj, since=since, until=until))
        until2 = datetime(2026, 9, 24, 12, 1, tzinfo=timezone.utc)
        self.assertTrue(ingest.in_window(obj, since=since, until=until2))

    def test_marker_key_flattens_path(self) -> None:
        self.assertEqual(
            ingest.marker_key("otel/2026/09/24/19/46/traces_a.json"),
            "indexes/signoz/otel__2026__09__24__19__46__traces_a.json.ingested",
        )

    def test_select_objects_orders_and_filters(self) -> None:
        keys = [
            "summaries/runs/x.json",
            "otel/2026/09/24/10/00/traces_old.json",
            "otel/2026/09/24/12/00/metrics_b.json",
            "otel/2026/09/24/11/00/traces_a.json",
        ]
        since = datetime(2026, 9, 24, 11, 0, tzinfo=timezone.utc)
        until = datetime(2026, 9, 24, 13, 0, tzinfo=timezone.utc)
        selected = ingest.select_objects(keys, since=since, until=until)
        self.assertEqual(
            [o.key for o in selected],
            [
                "otel/2026/09/24/11/00/traces_a.json",
                "otel/2026/09/24/12/00/metrics_b.json",
            ],
        )


class ParseIsoUtcTest(unittest.TestCase):
    def test_z_suffix_and_naive(self) -> None:
        self.assertEqual(
            ingest.parse_iso_utc("2026-09-24T12:00:00Z"),
            datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            ingest.parse_iso_utc("2026-09-24T12:00:00"),
            datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc),
        )


class _FakeClientError(Exception):
    def __init__(self, response: dict) -> None:
        super().__init__("client error")
        self.response = response


class MarkerExistsTest(unittest.TestCase):
    def test_true_when_head_ok(self) -> None:
        client = mock.Mock()
        client.head_object.return_value = {}
        self.assertTrue(ingest.marker_exists(client, "bucket", "otel/a/traces_x.json"))

    def test_false_on_404_code(self) -> None:
        client = mock.Mock()
        client.exceptions.ClientError = _FakeClientError
        client.head_object.side_effect = _FakeClientError(
            {"Error": {"Code": "404"}, "ResponseMetadata": {}}
        )
        self.assertFalse(ingest.marker_exists(client, "bucket", "otel/a/traces_x.json"))

    def test_reraises_other_errors(self) -> None:
        client = mock.Mock()
        client.exceptions.ClientError = _FakeClientError
        client.head_object.side_effect = _FakeClientError(
            {"Error": {"Code": "403"}, "ResponseMetadata": {"HTTPStatusCode": 403}}
        )
        with self.assertRaises(_FakeClientError):
            ingest.marker_exists(client, "bucket", "otel/a/traces_x.json")


class RunIngestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.since = datetime(2026, 9, 24, 11, 0, tzinfo=timezone.utc)
        self.until = datetime(2026, 9, 24, 13, 0, tzinfo=timezone.utc)
        self.key = "otel/2026/09/24/12/00/traces_a.json"

    def test_skips_when_marker_exists_without_force(self) -> None:
        client = mock.Mock()
        with (
            mock.patch.object(ingest, "signoz_container_running", return_value=True),
            mock.patch.object(ingest, "telemetry_bucket", return_value="nexus-telemetry-dev"),
            mock.patch.object(ingest, "_s3_client", return_value=client),
            mock.patch.object(ingest, "list_otel_objects", return_value=[self.key]),
            mock.patch.object(ingest, "marker_exists", return_value=True) as marker,
            mock.patch.object(ingest, "post_otlp_inside_signoz") as post,
            mock.patch.object(ingest, "write_marker") as write,
        ):
            rc = ingest.run_ingest(
                since=self.since, until=self.until, force=False, dry_run=False
            )
        self.assertEqual(rc, 0)
        marker.assert_called_once()
        post.assert_not_called()
        write.assert_not_called()

    def test_force_posts_even_with_marker(self) -> None:
        client = mock.Mock()
        client.get_object.return_value = {"Body": io.BytesIO(b'{"resourceSpans":[]}')}
        with (
            mock.patch.object(ingest, "signoz_container_running", return_value=True),
            mock.patch.object(ingest, "telemetry_bucket", return_value="nexus-telemetry-dev"),
            mock.patch.object(ingest, "_s3_client", return_value=client),
            mock.patch.object(ingest, "list_otel_objects", return_value=[self.key]),
            mock.patch.object(ingest, "marker_exists", return_value=True) as marker,
            mock.patch.object(ingest, "post_otlp_inside_signoz") as post,
            mock.patch.object(ingest, "write_marker") as write,
        ):
            rc = ingest.run_ingest(
                since=self.since, until=self.until, force=True, dry_run=False
            )
        self.assertEqual(rc, 0)
        marker.assert_not_called()
        post.assert_called_once()
        write.assert_called_once()

    def test_post_failure_does_not_write_marker(self) -> None:
        client = mock.Mock()
        client.get_object.return_value = {"Body": io.BytesIO(b'{"resourceSpans":[]}')}
        with (
            mock.patch.object(ingest, "signoz_container_running", return_value=True),
            mock.patch.object(ingest, "telemetry_bucket", return_value="nexus-telemetry-dev"),
            mock.patch.object(ingest, "_s3_client", return_value=client),
            mock.patch.object(ingest, "list_otel_objects", return_value=[self.key]),
            mock.patch.object(ingest, "marker_exists", return_value=False),
            mock.patch.object(
                ingest,
                "post_otlp_inside_signoz",
                side_effect=RuntimeError("OTLP POST failed"),
            ),
            mock.patch.object(ingest, "write_marker") as write,
            self.assertRaises(RuntimeError),
        ):
            ingest.run_ingest(
                since=self.since, until=self.until, force=False, dry_run=False
            )
        write.assert_not_called()

    def test_container_down_returns_2(self) -> None:
        with mock.patch.object(ingest, "signoz_container_running", return_value=False):
            rc = ingest.run_ingest(
                since=self.since, until=self.until, force=False, dry_run=False
            )
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
