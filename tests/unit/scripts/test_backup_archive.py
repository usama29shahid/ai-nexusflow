"""Guards for scripts/backup-archive.sh (no Compose / R2).

    uv run python tests/unit/scripts/test_backup_archive.py
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "backup-archive.sh"


class BackupArchiveTest(unittest.TestCase):
    def test_bash_n(self) -> None:
        proc = subprocess.run(
            ["bash", "-n", str(SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_missing_backup_env_fails_without_vault_file(self) -> None:
        """With env backend and empty backup keys, script exits before docker."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / "scripts"
            scripts.mkdir()
            script = scripts / "backup-archive.sh"
            script.write_text(SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
            script.chmod(0o755)
            (scripts / "load-secrets.sh").write_text(
                textwrap.dedent(
                    """\
                    # stub — env backend path should not need this if keys set;
                    # when keys empty, real script sources this after .env
                    return 0 2>/dev/null || exit 0
                    """
                ),
                encoding="utf-8",
            )
            (root / ".env").write_text(
                "NEXUS_ENV=dev\n"
                "NEXUS_SECRETS_BACKEND=env\n"
                "NEXUS_BACKUP_ENDPOINT=\n"
                "NEXUS_BACKUP_ACCESS_KEY=\n"
                "NEXUS_BACKUP_SECRET_KEY=\n"
                "MINIO_LOADER_USER=\n"
                "MINIO_LOADER_PASSWORD=\n",
                encoding="utf-8",
            )
            env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": tmp,
                "NEXUS_SECRETS_BACKEND": "env",
            }
            proc = subprocess.run(
                ["bash", str(script)],
                cwd=str(root),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("NEXUS_BACKUP_ENDPOINT is empty", proc.stderr)

    def test_injected_keys_survive_empty_dotenv(self) -> None:
        """Non-empty env-file values must win over empty .env assignments."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / "scripts"
            scripts.mkdir()
            # Truncate after require_* so we never hit docker.
            body = SCRIPT.read_text(encoding="utf-8")
            marker = "if ! docker inspect minio"
            self.assertIn(marker, body)
            stub = body.split(marker, 1)[0]
            stub += 'echo "PRESERVE_OK endpoint=${NEXUS_BACKUP_ENDPOINT}"\nexit 0\n'
            script = scripts / "backup-archive.sh"
            script.write_text(stub, encoding="utf-8")
            script.chmod(0o755)
            (root / ".env").write_text(
                "NEXUS_ENV=dev\n"
                "NEXUS_BACKUP_ENDPOINT=\n"
                "NEXUS_BACKUP_ACCESS_KEY=\n"
                "NEXUS_BACKUP_SECRET_KEY=\n"
                "MINIO_LOADER_USER=\n"
                "MINIO_LOADER_PASSWORD=\n",
                encoding="utf-8",
            )
            env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": tmp,
                "NEXUS_BACKUP_ENDPOINT": "https://example.r2.cloudflarestorage.com",
                "NEXUS_BACKUP_ACCESS_KEY": "ak-test",
                "NEXUS_BACKUP_SECRET_KEY": "sk-test",
                "MINIO_LOADER_USER": "nexus_loader",
                "MINIO_LOADER_PASSWORD": "loader-secret",
            }
            proc = subprocess.run(
                ["bash", str(script)],
                cwd=str(root),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            self.assertIn(
                "PRESERVE_OK endpoint=https://example.r2.cloudflarestorage.com",
                proc.stdout,
            )

    def test_vault_ensure_seeds_backup_kv(self) -> None:
        ensure = (REPO_ROOT / "scripts" / "vault-ensure.sh").read_text(
            encoding="utf-8"
        )
        tpl = (
            REPO_ROOT / "docker" / "vault" / "templates" / "secrets.env.tpl"
        ).read_text(encoding="utf-8")
        self.assertIn("ensure_backup_secret", ensure)
        self.assertIn("backup_creds_in_file", ensure)
        self.assertIn('/backup"', ensure)
        self.assertEqual(ensure.count("ensure_backup_secret"), 3)  # def + 2 calls
        self.assertIn("NEXUS_BACKUP_ENDPOINT={{ .Data.data.endpoint }}", tpl)
        self.assertIn("NEXUS_BACKUP_ACCESS_KEY={{ .Data.data.access_key }}", tpl)
        self.assertIn("NEXUS_BACKUP_SECRET_KEY={{ .Data.data.secret_key }}", tpl)


if __name__ == "__main__":
    unittest.main(verbosity=2)
