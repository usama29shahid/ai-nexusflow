"""Guards for Route products ingest (no Compose).

Run from repo root:

    uv run python branches/dlt_dbt_clickhouse/tests/dlt/route/unit/test_products_guards.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

# …/tests/dlt/route/unit/this_file → branch = parents[4], repo = parents[6]
REPO_ROOT = Path(__file__).resolve().parents[6]
BRANCH_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PRODUCTS_PATH = BRANCH_ROOT / "dlt" / "route" / "products.py"


def _load_products_module():
    spec = importlib.util.spec_from_file_location("route_products", PRODUCTS_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["route_products"] = mod
    spec.loader.exec_module(mod)
    return mod


class RouteProductsGuardsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.products = _load_products_module()

    def test_required_raises_runtime_error(self) -> None:
        with patch.object(self.products.os.environ, "get", return_value=None):
            with self.assertRaises(RuntimeError) as ctx:
                self.products._required("CLICKHOUSE_PASSWORD")
        self.assertIn("CLICKHOUSE_PASSWORD", str(ctx.exception))

    def test_assert_load_ok_raises_on_failed_jobs(self) -> None:
        load_info = MagicMock()
        load_info.has_failed_jobs = True
        load_info.raise_on_failed_jobs.side_effect = RuntimeError("job failed")
        with self.assertRaises(RuntimeError):
            self.products._assert_load_ok(load_info)
        load_info.raise_on_failed_jobs.assert_called_once()

    def test_assert_load_ok_passes_when_clean(self) -> None:
        load_info = MagicMock()
        load_info.has_failed_jobs = False
        self.products._assert_load_ok(load_info)
        load_info.raise_on_failed_jobs.assert_not_called()

    def test_route_session_sets_connect_read_timeout(self) -> None:
        with patch("dlt.sources.helpers.requests.retry.Client") as client_cls:
            client_cls.return_value.session = MagicMock(name="session")
            session = self.products._route_rest_session()
        client_cls.assert_called_once_with(
            raise_for_status=False,
            request_timeout=(10, 60),
            request_max_attempts=5,
            respect_retry_after_header=True,
        )
        self.assertIs(session, client_cls.return_value.session)

    def test_load_span_cm_falls_back_when_get_tracer_fails(self) -> None:
        with patch(
            "common.observability.otel.get_tracer",
            side_effect=RuntimeError("collector down"),
        ):
            cm = self.products._products_load_span_cm(
                run_id="local-test",
                env="dev",
            )
        with cm as load_span:
            self.assertIsNone(load_span)
            # Ingest body would run here — context enter/exit must not raise.
            ran = True
        self.assertTrue(ran)

    def test_load_span_cm_uses_tracer_when_available(self) -> None:
        fake_span = MagicMock(name="span")
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_span
        fake_cm.__exit__.return_value = None
        tracer = MagicMock()
        tracer.start_as_current_span.return_value = fake_cm
        with patch("common.observability.otel.get_tracer", return_value=tracer):
            cm = self.products._products_load_span_cm(
                run_id="local-test",
                env="dev",
            )
        with cm as load_span:
            self.assertIs(load_span, fake_span)
        tracer.start_as_current_span.assert_called_once()
        self.assertEqual(
            tracer.start_as_current_span.call_args.args[0],
            "route.products.load",
        )

    def test_filesystem_uses_minio_endpoint_url_override(self) -> None:
        env = {
            "MINIO_ENDPOINT_URL": "http://minio:9000",
            "MINIO_ROOT_USER": "minioadmin",
            "MINIO_ROOT_PASSWORD": "minioadmin123",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch.object(self.products, "filesystem", return_value=MagicMock()) as fs:
                _dest, _bucket, endpoint = self.products._filesystem_destination(
                    env="dev",
                    run_id="local-test",
                    dt="2026-09-05",
                )
        self.assertEqual(endpoint, "http://minio:9000")
        self.assertEqual(
            fs.call_args.kwargs["credentials"]["endpoint_url"],
            "http://minio:9000",
        )

    def test_filesystem_defaults_to_localhost_port(self) -> None:
        env = {
            "MINIO_API_PORT": "9002",
            "MINIO_ROOT_USER": "minioadmin",
            "MINIO_ROOT_PASSWORD": "minioadmin123",
        }
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("MINIO_ENDPOINT_URL", None)
            with patch.object(self.products, "filesystem", return_value=MagicMock()):
                _dest, _bucket, endpoint = self.products._filesystem_destination(
                    env="dev",
                    run_id="local-test",
                    dt="2026-09-05",
                )
        self.assertEqual(endpoint, "http://localhost:9002")

    def test_set_load_span_status_ok(self) -> None:
        span = MagicMock()
        with patch("opentelemetry.trace.Status") as status_cls:
            with patch("opentelemetry.trace.StatusCode") as code:
                code.OK = "OK"
                code.ERROR = "ERROR"
                self.products._set_load_span_status(span, status="ok")
        span.set_attribute.assert_called_once_with("status", "ok")
        span.set_status.assert_called_once()
        status_cls.assert_called_once_with(code.OK)

    def test_set_load_span_status_error(self) -> None:
        span = MagicMock()
        with patch("opentelemetry.trace.Status") as status_cls:
            with patch("opentelemetry.trace.StatusCode") as code:
                code.OK = "OK"
                code.ERROR = "ERROR"
                self.products._set_load_span_status(
                    span,
                    status="failed",
                    description="boom",
                )
        span.set_attribute.assert_called_once_with("status", "failed")
        span.set_status.assert_called_once()
        status_cls.assert_called_once_with(code.ERROR, "boom")

    def test_set_load_span_status_noop_when_none(self) -> None:
        self.products._set_load_span_status(None, status="failed")


class ResolveRunIdTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.products = _load_products_module()

    def test_cli_wins_over_env(self) -> None:
        now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
        run_id, source = self.products._resolve_run_id(
            "cli-id",
            env_run_id="env-id",
            now=now,
        )
        self.assertEqual(run_id, "cli-id")
        self.assertEqual(source, "cli")

    def test_env_used_when_no_cli(self) -> None:
        now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
        run_id, source = self.products._resolve_run_id(
            None,
            env_run_id="env-id",
            now=now,
        )
        self.assertEqual(run_id, "env-id")
        self.assertEqual(source, "env")

    def test_generates_local_utc_when_unset(self) -> None:
        now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
        run_id, source = self.products._resolve_run_id(
            None,
            env_run_id=None,
            now=now,
        )
        self.assertEqual(run_id, "local-20260905T120000Z")
        self.assertEqual(source, "generated")

    def test_blank_env_falls_through_to_mint(self) -> None:
        now = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)
        run_id, source = self.products._resolve_run_id(
            None,
            env_run_id="   ",
            now=now,
        )
        self.assertEqual(run_id, "local-20260905T120000Z")
        self.assertEqual(source, "generated")

    def test_empty_cli_run_id_rejected(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            self.products._resolve_run_id("", env_run_id="env-id")
        self.assertIn("--run-id", str(ctx.exception))

    def test_path_like_run_id_rejected(self) -> None:
        with self.assertRaises(RuntimeError):
            self.products._validate_run_id("../evil", source="--run-id")
        with self.assertRaises(RuntimeError):
            self.products._validate_run_id("a/b", source="--run-id")

    def test_airflow_style_run_id_allowed(self) -> None:
        rid = "manual__2026-09-05T12:00:00+00:00"
        self.assertEqual(
            self.products._validate_run_id(rid, source="--run-id"),
            rid,
        )

    def test_strips_whitespace(self) -> None:
        run_id, source = self.products._resolve_run_id(
            "  local-ok  ",
            env_run_id=None,
        )
        self.assertEqual(run_id, "local-ok")
        self.assertEqual(source, "cli")

    def test_parse_args_run_id(self) -> None:
        args = self.products._parse_args(["--run-id", "local-explicit"])
        self.assertEqual(args.run_id, "local-explicit")

    def test_parse_args_default_none(self) -> None:
        args = self.products._parse_args([])
        self.assertIsNone(args.run_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
