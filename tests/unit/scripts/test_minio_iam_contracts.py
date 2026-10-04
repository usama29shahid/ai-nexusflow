"""Static contracts for MinIO IAM bootstrap / setup / service-check (no Docker).

    uv run python tests/unit/scripts/test_minio_iam_contracts.py
"""

from __future__ import annotations

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SETUP_SH = REPO_ROOT / "scripts" / "setup.sh"
START_SH = REPO_ROOT / "scripts" / "start.sh"
APPLY_SH = REPO_ROOT / "docker" / "minio" / "iam" / "apply.sh"
BOOTSTRAP_SH = REPO_ROOT / "scripts" / "minio-iam-bootstrap.sh"
SERVICE_CHECK_SH = REPO_ROOT / "scripts" / "minio-iam-service-check.sh"
LOAD_SECRETS_SH = REPO_ROOT / "scripts" / "load-secrets.sh"
STACK_VERIFY_SH = REPO_ROOT / "scripts" / "stack-verify.sh"
COMPOSE_YML = REPO_ROOT / "docker-compose.yml"
MINIO_README = REPO_ROOT / "docker" / "minio" / "README.md"
RUNTIME_ENV_PY = REPO_ROOT / "common" / "runtime_env.py"

# Keep in sync with docker-compose.yml minio-init / bootstrap default.
MC_PIN = "quay.io/minio/aistor/mc:RELEASE.2026-09-06T02-44-40Z"


class MinioIamContractsTest(unittest.TestCase):
    def test_setup_fail_fast_wait_before_iam_and_rest_of_stack(self) -> None:
        text = SETUP_SH.read_text(encoding="utf-8")
        self.assertIn("Starting MinIO (shared infra first)...", text)
        self.assertIn("docker compose up -d minio minio-init", text)
        self.assertIn("Timed out waiting for MinIO / minio-init.", text)
        self.assertIn('minio-init exited ${init_code}', text)
        self.assertIn("minio-iam-bootstrap.sh --apply-only", text)
        # Remaining stack only after IAM apply.
        apply_at = text.index("minio-iam-bootstrap.sh --apply-only")
        rest_at = text.index("Starting remaining infrastructure")
        self.assertLess(apply_at, rest_at)
        timeout_exit = text.index("Timed out waiting for MinIO / minio-init.")
        self.assertIn("exit 1", text[timeout_exit : timeout_exit + 200])

    def test_start_wait_minio_ready_exits_on_failure(self) -> None:
        text = START_SH.read_text(encoding="utf-8")
        self.assertIn("wait_minio_ready()", text)
        self.assertIn("ensure_minio_iam()", text)
        fn = text[text.index("wait_minio_ready()") : text.index("ensure_minio_iam()")]
        self.assertIn("Timed out waiting for MinIO / minio-init.", fn)
        self.assertIn("minio-init exited", fn)
        self.assertGreaterEqual(fn.count("exit 1"), 2)
        shared = text[text.index("ensure_shared_infra()") : text.index("ensure_minio()")]
        self.assertLess(
            shared.index("wait_minio_ready"),
            shared.index("ensure_minio_iam"),
        )
        self.assertLess(
            shared.index("ensure_minio_iam"),
            shared.index("sync_otel_collector_config"),
        )

    def test_apply_sh_upsert_only_no_remove(self) -> None:
        text = APPLY_SH.read_text(encoding="utf-8")
        code_lines = [
            line
            for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        self.assertIn("upsert", text.lower())
        self.assertIn("mc admin policy create", code)
        self.assertIn("mc admin user add", code)
        self.assertNotIn("policy remove", code)
        self.assertNotIn("user remove", code)
        self.assertIn("MINIO_MC_IMAGE", text)

    def test_mc_image_pin_aligned(self) -> None:
        compose = COMPOSE_YML.read_text(encoding="utf-8")
        bootstrap = BOOTSTRAP_SH.read_text(encoding="utf-8")
        readme = MINIO_README.read_text(encoding="utf-8")
        self.assertIn(MC_PIN, compose)
        self.assertIn(MC_PIN, bootstrap)
        self.assertIn(MC_PIN, readme)
        self.assertIn(f"${{MINIO_MC_IMAGE:-{MC_PIN}}}", compose)
        self.assertIn(f'${{MINIO_MC_IMAGE:-{MC_PIN}}}', bootstrap)

    def test_service_check_uses_mc_not_aws_cli(self) -> None:
        text = SERVICE_CHECK_SH.read_text(encoding="utf-8")
        self.assertIn("mc pipe", text)
        self.assertIn("MINIO_MC_IMAGE", text)
        self.assertNotIn("amazon/aws-cli", text)

    def test_service_check_documented_as_live_coverage(self) -> None:
        readme = MINIO_README.read_text(encoding="utf-8")
        self.assertIn("minio-iam-service-check.sh", readme)
        self.assertIn("minio-iam-bootstrap.sh", readme)

    def test_secrets_backend_defaults_to_vault_when_unset(self) -> None:
        load = LOAD_SECRETS_SH.read_text(encoding="utf-8")
        verify = STACK_VERIFY_SH.read_text(encoding="utf-8")
        runtime = RUNTIME_ENV_PY.read_text(encoding="utf-8")
        start = START_SH.read_text(encoding="utf-8")
        self.assertIn('NEXUS_SECRETS_BACKEND:-vault', load)
        self.assertNotIn('NEXUS_SECRETS_BACKEND:-env', load)
        self.assertIn('NEXUS_SECRETS_BACKEND:-vault', verify)
        self.assertNotIn('NEXUS_SECRETS_BACKEND:-env', verify)
        self.assertIn('NEXUS_SECRETS_BACKEND", "vault"', runtime)
        self.assertNotIn('NEXUS_SECRETS_BACKEND", "env"', runtime)
        self.assertIn("NEXUS_SECRETS_BACKEND:-vault", start)
        self.assertNotIn("NEXUS_SECRETS_BACKEND:-env", start)


if __name__ == "__main__":
    unittest.main(verbosity=2)
