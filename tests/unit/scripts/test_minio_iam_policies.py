"""Policy JSON for MinIO IAM. No MinIO server required.

    uv run python tests/unit/scripts/test_minio_iam_policies.py
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPO_ROOT / "scripts" / "minio_iam_policies.py"


def _load():
    spec = importlib.util.spec_from_file_location("minio_iam_policies", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MinioIamPoliciesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.mod = _load()

    def test_loader_allows_multipart_and_denies_delete(self) -> None:
        text = self.mod.render_policy("nexus-loader", "dev")
        self.assertIn("s3:AbortMultipartUpload", text)
        self.assertIn("s3:ListBucketMultipartUploads", text)
        self.assertIn("s3:ListMultipartUploadParts", text)
        self.assertIn("s3:PutObject", text)
        self.assertIn('"Effect": "Deny"', text)
        self.assertIn("s3:DeleteObject", text)
        self.assertIn("arn:aws:s3:::nexus-dlt-dbt-clickhouse-dev/*", text)
        self.assertIn("arn:aws:s3:::nexus-telemetry-dev/*", text)
        self.assertIn("nexus-dlt-dbt-spark-iceberg-dev", text)
        self.assertIn("nexus-dlt-dbt-spark-iceberg-archive-dev", text)
        deny = text.split('"Effect": "Deny"', 1)[1]
        self.assertIn("nexus-dlt-dbt-clickhouse-dev/*", deny)
        self.assertIn("nexus-telemetry-dev/*", deny)
        self.assertIn("nexus-dlt-dbt-spark-iceberg-archive-dev/*", deny)
        self.assertNotIn("nexus-airflow-logs-dev/*", deny)
        # Iceberg warehouse may delete (compaction); deny block must not cover it.
        self.assertNotIn(
            "arn:aws:s3:::nexus-dlt-dbt-spark-iceberg-dev/*",
            deny,
        )

    def test_reader_marker_prefixes_only(self) -> None:
        text = self.mod.render_policy("nexus-reader", "dev")
        self.assertIn("arn:aws:s3:::nexus-telemetry-dev/*", text)
        self.assertIn("indexes/signoz/*", text)
        self.assertIn("indexes/openobserve/*", text)
        self.assertIn("indexes/openmetadata/*", text)
        self.assertNotIn("nexus-dlt-dbt-clickhouse-dev", text)
        self.assertNotIn("nexus-airflow-logs-dev", text)
        delete_at = text.find("s3:DeleteObject")
        self.assertGreater(delete_at, 0)
        self.assertIn("indexes/openobserve/*", text[delete_at:])
        self.assertNotIn("indexes/signoz/*", text[delete_at:])

    def test_admin_covers_five_buckets(self) -> None:
        text = self.mod.render_policy("nexus-admin", "prd")
        for bucket in (
            "nexus-dlt-dbt-clickhouse-prd",
            "nexus-telemetry-prd",
            "nexus-airflow-logs-prd",
            "nexus-dlt-dbt-spark-iceberg-archive-prd",
            "nexus-dlt-dbt-spark-iceberg-prd",
        ):
            self.assertIn(bucket, text)

    def test_platform_reader_is_read_only_all_buckets(self) -> None:
        text = self.mod.render_policy("nexus-platform-reader", "dev")
        for bucket in (
            "nexus-dlt-dbt-clickhouse-dev",
            "nexus-telemetry-dev",
            "nexus-airflow-logs-dev",
            "nexus-dlt-dbt-spark-iceberg-archive-dev",
            "nexus-dlt-dbt-spark-iceberg-dev",
        ):
            self.assertIn(bucket, text)
        self.assertIn("s3:GetObject", text)
        self.assertIn("s3:ListBucket", text)
        self.assertNotIn("s3:PutObject", text)
        self.assertNotIn("s3:DeleteObject", text)

    def test_rejects_unsafe_env(self) -> None:
        with self.assertRaises(ValueError):
            self.mod.render_policy("nexus-loader", "dev;drop")


if __name__ == "__main__":
    unittest.main(verbosity=2)
