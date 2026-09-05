"""Unit guards for common.observability.publish (no Compose).

Run from repo root:

    uv run python tests/unit/common/test_observability_publish.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class PublishDltLoadEventTest(unittest.TestCase):
    def test_ok_uses_completed_event(self) -> None:
        from common.observability import publish as pub

        with (
            patch.object(pub, "publish_pipeline_event") as event,
            patch.object(pub, "publish_run_summary", return_value="s3://summary"),
            patch.object(pub, "record_dlt_load") as otel,
        ):
            pub.publish_dlt_load(
                branch="dlt_dbt_clickhouse",
                component="dlt",
                pipeline_name="route_products",
                status="ok",
                run_id="local-test",
                row_count=56,
            )
        self.assertEqual(event.call_args.kwargs["event_type"], "dlt.load.completed")
        otel.assert_called_once()
        self.assertEqual(otel.call_args.kwargs["row_count"], 56)
        self.assertEqual(otel.call_args.kwargs["status"], "ok")

    def test_failed_uses_failed_event(self) -> None:
        from common.observability import publish as pub

        with (
            patch.object(pub, "publish_pipeline_event") as event,
            patch.object(pub, "publish_run_summary", return_value="s3://summary"),
            patch.object(pub, "record_dlt_load") as otel,
        ):
            pub.publish_dlt_load(
                branch="dlt_dbt_clickhouse",
                component="dlt",
                pipeline_name="route_products",
                status="failed",
                run_id="local-test",
                row_count=0,
            )
        self.assertEqual(event.call_args.kwargs["event_type"], "dlt.load.failed")
        otel.assert_called_once()
        self.assertEqual(otel.call_args.kwargs["event_type"], "dlt.load.failed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
