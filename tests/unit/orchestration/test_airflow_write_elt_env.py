"""Guards for scripts/airflow-write-elt-env.sh (no Compose).

    uv run python tests/unit/orchestration/test_airflow_write_elt_env.py
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "airflow-write-elt-env.sh"


class AirflowWriteEltEnvTest(unittest.TestCase):
    def test_writes_literal_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "airflow_elt.env"
            env = {
                **os.environ,
                "NEXUS_AIRFLOW_ELT_ENV": str(out),
                "NEXUS_ENV": "dev",
                "CLICKHOUSE_PASSWORD": "p#ass=word",
                "MINIO_ROOT_USER": "minioadmin",
                "MINIO_ROOT_PASSWORD": "minioadmin123",
            }
            proc = subprocess.run(
                [str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            text = out.read_text(encoding="utf-8")
            self.assertIn("NEXUS_ENV=dev\n", text)
            self.assertIn("CLICKHOUSE_PASSWORD=p#ass=word\n", text)

    def test_rejects_newline_preserves_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "airflow_elt.env"
            out.write_text("# keep-me\nNEXUS_ENV=dev\n", encoding="utf-8")
            env = {
                **os.environ,
                "NEXUS_AIRFLOW_ELT_ENV": str(out),
                "NEXUS_ENV": "dev",
                "CLICKHOUSE_PASSWORD": "bad\nvalue",
                "MINIO_ROOT_USER": "minioadmin",
                "MINIO_ROOT_PASSWORD": "minioadmin123",
            }
            proc = subprocess.run(
                [str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("newline", proc.stderr)
            self.assertEqual(out.read_text(encoding="utf-8"), "# keep-me\nNEXUS_ENV=dev\n")
            # No leftover temp siblings from a failed write.
            self.assertEqual(list(Path(tmp).iterdir()), [out])


if __name__ == "__main__":
    unittest.main(verbosity=2)
