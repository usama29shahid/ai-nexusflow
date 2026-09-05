"""Unit guards for common.observability.otel (no Compose).

Run from repo root:

    uv run python tests/unit/common/test_observability_otel.py
"""

from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class RecordDltLoadBestEffortTest(unittest.TestCase):
    def test_swallows_get_tracer_failure(self) -> None:
        from common.observability import otel as otel_mod

        stderr = io.StringIO()
        with (
            patch.object(otel_mod, "get_tracer", side_effect=RuntimeError("collector down")),
            patch.object(sys, "stderr", stderr),
        ):
            otel_mod.record_dlt_load(
                run_id="local-test",
                branch="dlt_dbt_clickhouse",
                component="dlt",
                pipeline_name="route_products",
                status="ok",
                event_type="dlt.load.completed",
                row_count=56,
            )
        self.assertIn("OTLP emit failed", stderr.getvalue())
        self.assertIn("collector down", stderr.getvalue())

    def test_swallows_force_flush_failure(self) -> None:
        from common.observability import otel as otel_mod

        fake_span = MagicMock()
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_span
        fake_cm.__exit__.return_value = None
        tracer = MagicMock()
        tracer.start_as_current_span.return_value = fake_cm

        stderr = io.StringIO()
        with (
            patch.object(otel_mod, "get_tracer", return_value=tracer),
            patch.object(otel_mod, "_rows_counter", None),
            patch.object(otel_mod, "_force_flush", side_effect=RuntimeError("flush failed")),
            patch.object(sys, "stderr", stderr),
        ):
            otel_mod.record_dlt_load(
                run_id="local-test",
                branch="dlt_dbt_clickhouse",
                component="dlt",
                pipeline_name="route_products",
                status="failed",
                event_type="dlt.load.failed",
                row_count=0,
            )
        self.assertIn("OTLP emit failed", stderr.getvalue())
        self.assertIn("flush failed", stderr.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
