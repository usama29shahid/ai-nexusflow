"""Unit guards for common.observability.publish (no Compose).

Run from repo root:

    uv run python tests/unit/common/test_observability_publish.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

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


class PublishOrchestratedRunTest(unittest.TestCase):
    def test_ok_writes_airflow_summary(self) -> None:
        from common.observability import publish as pub

        with (
            patch.object(pub, "publish_dbt_run", return_value=(["s3://a"], "s3://old")),
            patch.object(pub, "copy_elementary_report", return_value="s3://el") as elem,
            patch.object(pub, "publish_pipeline_event") as event,
            patch.object(pub, "publish_run_summary", return_value="s3://summary") as summary_write,
            patch.object(pub, "get_tracer"),
            patch("pathlib.Path.is_file", return_value=True),
        ):
            uploaded, summary = pub.publish_orchestrated_run(
                Path("branches/dlt_dbt_clickhouse"),
                run_id="manual__test",
                dag_id="route_clickhouse_products",
                status="ok",
            )
        self.assertEqual(summary, "s3://summary")
        self.assertIn("s3://el", uploaded)
        elem.assert_called_once()
        self.assertEqual(event.call_args.kwargs["event_type"], "airflow.dag.completed")
        self.assertEqual(
            summary_write.call_args.kwargs["extra"]["phases"],
            ["dlt", "dbt", "docs", "elementary"],
        )

    def test_failed_writes_airflow_failed_event(self) -> None:
        from common.observability import publish as pub

        tracer = MagicMock()
        with (
            patch.object(pub, "publish_dbt_run", return_value=([], None)),
            patch.object(pub, "publish_pipeline_event") as event,
            patch.object(pub, "publish_run_summary", return_value="s3://summary") as summary_write,
            patch.object(pub, "get_tracer", return_value=tracer),
            patch("pathlib.Path.is_file", return_value=False),
        ):
            _, summary = pub.publish_orchestrated_run(
                Path("branches/dlt_dbt_clickhouse"),
                run_id="manual__test",
                dag_id="route_clickhouse_products",
                status="failed",
            )
        self.assertEqual(summary, "s3://summary")
        self.assertEqual(event.call_args.kwargs["event_type"], "airflow.dag.failed")
        tracer.start_as_current_span.assert_called()
        self.assertEqual(tracer.start_as_current_span.call_args.args[0], "airflow.dag.failed")
        self.assertEqual(summary_write.call_args.kwargs["extra"]["phases"], ["airflow"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
