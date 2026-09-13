"""Unit guards for config/branches.yaml reader.

    uv run python tests/unit/common/test_branches.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class BranchEnabledTest(unittest.TestCase):
    def test_clickhouse_enabled_in_repo_config(self) -> None:
        from common.branches import is_branch_enabled

        self.assertTrue(is_branch_enabled("dlt_dbt_clickhouse"))
        self.assertFalse(is_branch_enabled("dlt_dbt_spark_iceberg"))

    def test_unknown_branch_raises(self) -> None:
        from common.branches import is_branch_enabled

        with self.assertRaises(ValueError):
            is_branch_enabled("not_a_branch")

    def test_disabled_override(self) -> None:
        from common.branches import is_branch_enabled

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "branches.yaml"
            path.write_text(
                "branches:\n  dlt_dbt_clickhouse:\n    enabled: false\n",
                encoding="utf-8",
            )
            self.assertFalse(is_branch_enabled("dlt_dbt_clickhouse", config_path=path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
