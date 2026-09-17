"""Unit guards for Airflow ELT job-image helper (no Compose).

    uv run python tests/unit/orchestration/test_nexus_elt_exec.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DAGS = REPO_ROOT / "orchestration" / "airflow" / "dags"
if str(DAGS) not in sys.path:
    sys.path.insert(0, str(DAGS))


class EltExecTest(unittest.TestCase):
    def test_docker_run_wraps_network_and_run_id(self) -> None:
        from nexus_elt_exec import elt_bash_command

        cmd = elt_bash_command(
            "uv run python branches/dlt_dbt_clickhouse/dlt/route/products.py"
        )
        self.assertIn("docker run --rm", cmd)
        self.assertIn("NEXUS_REPO_ROOT", cmd)
        self.assertIn("CLICKHOUSE_HOST=clickhouse", cmd)
        self.assertIn("MINIO_ENDPOINT_URL=http://minio:9000", cmd)
        self.assertIn("NEXUS_ELT_JOB=1", cmd)
        self.assertIn("{{ run_id }}", cmd)
        self.assertIn("/opt/airflow/nexus_elt.env", cmd)
        self.assertNotIn("secrets.env", cmd)
        self.assertNotIn("airflow-write-elt-env.sh", cmd)
        self.assertNotIn("ssh ", cmd)
        self.assertNotIn("bash -lc './scripts/start.sh", cmd)

    def test_quoted_remote_preserves_run_id_argv(self) -> None:
        """Regression: remote!r must not put quote chars into --run-id."""
        import subprocess
        import tempfile
        from pathlib import Path

        from nexus_elt_exec import elt_bash_command

        with tempfile.TemporaryDirectory() as tmp:
            stub = Path(tmp) / "printargs.sh"
            stub.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$#\"\n"
                "printf '%s\\n' \"$@\"\n",
                encoding="utf-8",
            )
            stub.chmod(0o755)
            rid = "manual__2026-09-17T17:12:52.906792+00:00"
            # Only the bash -lc line from the helper (skip docker / envfile gates).
            full = elt_bash_command(f"{stub} --run-id '{rid}'")
            lc_line = next(line for line in full.splitlines() if "bash -lc" in line)
            proc = subprocess.run(
                ["bash", "-c", lc_line.strip()],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            lines = proc.stdout.splitlines()
            self.assertEqual(lines[0], "2")
            self.assertEqual(lines[1], "--run-id")
            self.assertEqual(lines[2], rid)

    def test_bronze_run_id_uses_single_quotes(self) -> None:
        import shlex

        from nexus_elt_exec import elt_bash_command

        remote = (
            "uv run python branches/dlt_dbt_clickhouse/dlt/route/products.py "
            "--run-id '{{ run_id }}'"
        )
        cmd = elt_bash_command(remote)
        self.assertIn("{{ run_id }}", cmd)
        self.assertIn(shlex.quote(remote), cmd)
        self.assertNotIn('--run-id "{{ run_id }}"', remote)

    def test_dbt_layer_never_build(self) -> None:
        from nexus_elt_exec import elt_dbt_layer

        cmd = elt_dbt_layer("tag:products,tag:staging")
        self.assertNotIn("dbt build", cmd)
        self.assertIn("airflow-dbt-layer.sh", cmd)
        self.assertIn("tag:products,tag:staging", cmd)

    def test_dbt_layer_quotes_select_with_apostrophe(self) -> None:
        """Selectors with ' must remain one argv after bash -lc."""
        import shlex
        import subprocess
        import tempfile
        from pathlib import Path

        from nexus_elt_exec import elt_bash_command, elt_dbt_layer

        select = "tag:prod'ucts,tag:staging"
        self.assertIn("airflow-dbt-layer.sh", elt_dbt_layer(select))
        self.assertIn("prod", elt_dbt_layer(select))

        with tempfile.TemporaryDirectory() as tmp:
            stub = Path(tmp) / "airflow-dbt-layer.sh"
            stub.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$#\"\n"
                "printf '%s\\n' \"$@\"\n",
                encoding="utf-8",
            )
            stub.chmod(0o755)
            full = elt_bash_command(f"{stub} {shlex.quote(select)}")
            lc_line = next(line for line in full.splitlines() if "bash -lc" in line)
            proc = subprocess.run(
                ["bash", "-c", lc_line.strip()],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            lines = proc.stdout.splitlines()
            self.assertEqual(lines[0], "1")
            self.assertEqual(lines[1], select)

    def test_products_dag_uses_elt_helper(self) -> None:
        text = (
            REPO_ROOT
            / "orchestration"
            / "airflow"
            / "dags"
            / "route_clickhouse"
            / "products.py"
        ).read_text(encoding="utf-8")
        self.assertIn("nexus_elt_exec", text)
        self.assertIn("elt_bash_command", text)
        self.assertNotIn("nexus_host_exec", text)
        self.assertIn("observability_failed", text)
        self.assertIn("TriggerRule.ONE_FAILED", text)
        self.assertIn("observability-publish-run.sh failed", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
