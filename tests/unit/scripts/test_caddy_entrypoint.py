"""Guards for docker/caddy/docker-entrypoint.sh mode checks (no Docker daemon).

    uv run python tests/unit/scripts/test_caddy_entrypoint.py
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ENTRYPOINT = REPO_ROOT / "docker" / "caddy" / "docker-entrypoint.sh"
CADDY_DIR = REPO_ROOT / "docker" / "caddy"


class CaddyEntrypointTest(unittest.TestCase):
    def _run(self, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            caddy_etc = tmp_path / "caddy"
            caddy_etc.mkdir()
            body = ENTRYPOINT.read_text(encoding="utf-8")
            body = body.replace("/templates/", f"{CADDY_DIR.as_posix()}/")
            body = body.replace("/etc/caddy/", f"{caddy_etc.as_posix()}/")
            body = body.replace(
                f"exec caddy run --config {caddy_etc.as_posix()}/Caddyfile --adapter caddyfile",
                "echo OK_WOULD_RUN_CADDY; exit 0",
            )
            wrapped = tmp_path / "entrypoint.sh"
            wrapped.write_text(body, encoding="utf-8")
            wrapped.chmod(0o755)
            return subprocess.run(
                ["sh", str(wrapped)],
                cwd=REPO_ROOT,
                env={**os.environ, **env},
                capture_output=True,
                text=True,
                check=False,
            )

    def test_local_ok(self) -> None:
        proc = self._run(
            {
                "NEXUS_EDGE_MODE": "local",
                "NEXUS_PUBLIC_HOST": "localhost.com",
                "NEXUS_CADDY_SITE_SCHEME": "",
            }
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("OK_WOULD_RUN_CADDY", proc.stdout)

    def test_vps_rejects_http_scheme(self) -> None:
        proc = self._run(
            {
                "NEXUS_EDGE_MODE": "vps",
                "NEXUS_PUBLIC_HOST": "example.com",
                "NEXUS_CADDY_SITE_SCHEME": "http://",
                "NEXUS_CADDY_ACME_EMAIL": "ops@example.com",
            }
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("cannot use NEXUS_CADDY_SITE_SCHEME=http://", proc.stderr)

    def test_vps_rejects_missing_acme_email(self) -> None:
        proc = self._run(
            {
                "NEXUS_EDGE_MODE": "vps",
                "NEXUS_PUBLIC_HOST": "example.com",
                "NEXUS_CADDY_SITE_SCHEME": "",
                "NEXUS_CADDY_ACME_EMAIL": "",
            }
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("NEXUS_CADDY_ACME_EMAIL is required", proc.stderr)

    def test_vps_rejects_public_publish_bind(self) -> None:
        proc = self._run(
            {
                "NEXUS_EDGE_MODE": "vps",
                "NEXUS_PUBLIC_HOST": "example.com",
                "NEXUS_CADDY_SITE_SCHEME": "",
                "NEXUS_CADDY_ACME_EMAIL": "ops@example.com",
                "NEXUS_PUBLISH_BIND": "0.0.0.0",
            }
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("cannot use NEXUS_PUBLISH_BIND=0.0.0.0", proc.stderr)

    def test_vps_ok(self) -> None:
        proc = self._run(
            {
                "NEXUS_EDGE_MODE": "vps",
                "NEXUS_PUBLIC_HOST": "example.com",
                "NEXUS_CADDY_SITE_SCHEME": "",
                "NEXUS_CADDY_ACME_EMAIL": "ops@example.com",
                "NEXUS_PUBLISH_BIND": "127.0.0.1",
            }
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("OK_WOULD_RUN_CADDY", proc.stdout)


if __name__ == "__main__":
    unittest.main()
