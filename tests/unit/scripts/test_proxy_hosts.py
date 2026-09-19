"""Guards for scripts/proxy-hosts.sh hosts-block rewriting (no sudo).

    uv run python tests/unit/scripts/test_proxy_hosts.py
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "proxy-hosts.sh"


class ProxyHostsTest(unittest.TestCase):
    def _run(self, cmd: str, hosts_file: Path) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "NEXUS_PROXY_HOSTS_FILE": str(hosts_file),
            "NEXUS_PUBLIC_HOST": "localhost.com",
        }
        return subprocess.run(
            ["bash", str(SCRIPT), cmd],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_install_appends_complete_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hosts = Path(tmp) / "hosts"
            hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
            proc = self._run("install", hosts)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            text = hosts.read_text(encoding="utf-8")
            self.assertIn("127.0.0.1 localhost", text)
            self.assertIn("# nexus-edge-proxy BEGIN (localhost.com)", text)
            self.assertIn("# nexus-edge-proxy END (localhost.com)", text)
            self.assertIn("127.0.0.1 minio.localhost.com", text)

    def test_install_replaces_existing_block_without_duplicating(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hosts = Path(tmp) / "hosts"
            hosts.write_text(
                "\n".join(
                    [
                        "127.0.0.1 localhost",
                        "# nexus-edge-proxy BEGIN (localhost.com)",
                        "127.0.0.1 old.localhost.com",
                        "# nexus-edge-proxy END (localhost.com)",
                        "10.0.0.1 other",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            proc = self._run("install", hosts)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            text = hosts.read_text(encoding="utf-8")
            self.assertEqual(text.count("# nexus-edge-proxy BEGIN (localhost.com)"), 1)
            self.assertNotIn("old.localhost.com", text)
            self.assertIn("127.0.0.1 localhost", text)
            self.assertIn("10.0.0.1 other", text)
            self.assertIn("minio.localhost.com", text)

    def test_install_aborts_when_begin_without_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hosts = Path(tmp) / "hosts"
            original = "\n".join(
                [
                    "127.0.0.1 localhost",
                    "# nexus-edge-proxy BEGIN (localhost.com)",
                    "127.0.0.1 dangling.localhost.com",
                    "10.0.0.1 must-survive",
                    "",
                ]
            )
            hosts.write_text(original, encoding="utf-8")
            proc = self._run("install", hosts)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("BEGIN without matching END", proc.stderr)
            self.assertEqual(hosts.read_text(encoding="utf-8"), original)

    def test_remove_aborts_when_begin_without_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hosts = Path(tmp) / "hosts"
            original = "\n".join(
                [
                    "127.0.0.1 localhost",
                    "# nexus-edge-proxy BEGIN (localhost.com)",
                    "10.0.0.1 must-survive",
                    "",
                ]
            )
            hosts.write_text(original, encoding="utf-8")
            proc = self._run("remove", hosts)
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(hosts.read_text(encoding="utf-8"), original)

    def test_env_override_wins_over_dotenv_file(self) -> None:
        """Caller/env NEXUS_PUBLIC_HOST must not be replaced by .env."""
        with tempfile.TemporaryDirectory() as tmp:
            hosts = Path(tmp) / "hosts"
            dotenv = Path(tmp) / "dotenv"
            hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
            dotenv.write_text("NEXUS_PUBLIC_HOST=fromfile.test\n", encoding="utf-8")
            env = {
                **os.environ,
                "NEXUS_PROXY_HOSTS_FILE": str(hosts),
                "NEXUS_PROXY_DOTENV": str(dotenv),
                "NEXUS_PUBLIC_HOST": "fromenv.test",
            }
            proc = subprocess.run(
                ["bash", str(SCRIPT), "install"],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            text = hosts.read_text(encoding="utf-8")
            self.assertIn("# nexus-edge-proxy BEGIN (fromenv.test)", text)
            self.assertIn("minio.fromenv.test", text)
            self.assertNotIn("fromfile.test", text)

    def test_reads_host_from_dotenv_when_env_unset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hosts = Path(tmp) / "hosts"
            dotenv = Path(tmp) / "dotenv"
            hosts.write_text("127.0.0.1 localhost\n", encoding="utf-8")
            dotenv.write_text('NEXUS_PUBLIC_HOST="fromfile.test"\n', encoding="utf-8")
            env = {
                **os.environ,
                "NEXUS_PROXY_HOSTS_FILE": str(hosts),
                "NEXUS_PROXY_DOTENV": str(dotenv),
            }
            env.pop("NEXUS_PUBLIC_HOST", None)
            proc = subprocess.run(
                ["bash", str(SCRIPT), "install"],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            text = hosts.read_text(encoding="utf-8")
            self.assertIn("# nexus-edge-proxy BEGIN (fromfile.test)", text)
            self.assertIn("minio.fromfile.test", text)

    def test_install_replaces_block_for_different_public_host(self) -> None:
        """Domain switch must drop the old nexus block (local → VPS host rename)."""
        with tempfile.TemporaryDirectory() as tmp:
            hosts = Path(tmp) / "hosts"
            hosts.write_text(
                "\n".join(
                    [
                        "127.0.0.1 localhost",
                        "# nexus-edge-proxy BEGIN (localhost.com)",
                        "127.0.0.1 minio.localhost.com",
                        "# nexus-edge-proxy END (localhost.com)",
                        "10.0.0.1 other",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            env = {
                **os.environ,
                "NEXUS_PROXY_HOSTS_FILE": str(hosts),
                "NEXUS_PUBLIC_HOST": "example.com",
            }
            proc = subprocess.run(
                ["bash", str(SCRIPT), "install"],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            text = hosts.read_text(encoding="utf-8")
            self.assertNotIn("localhost.com", text)
            self.assertIn("# nexus-edge-proxy BEGIN (example.com)", text)
            self.assertIn("minio.example.com", text)
            self.assertIn("127.0.0.1 localhost", text)
            self.assertIn("10.0.0.1 other", text)

    def test_remove_drops_all_nexus_blocks_regardless_of_host(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hosts = Path(tmp) / "hosts"
            hosts.write_text(
                "\n".join(
                    [
                        "127.0.0.1 localhost",
                        "# nexus-edge-proxy BEGIN (old.test)",
                        "127.0.0.1 minio.old.test",
                        "# nexus-edge-proxy END (old.test)",
                        "# nexus-edge-proxy BEGIN (localhost.com)",
                        "127.0.0.1 airflow.localhost.com",
                        "# nexus-edge-proxy END (localhost.com)",
                        "10.0.0.1 other",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            proc = self._run("remove", hosts)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            text = hosts.read_text(encoding="utf-8")
            self.assertNotIn("nexus-edge-proxy", text)
            self.assertIn("127.0.0.1 localhost", text)
            self.assertIn("10.0.0.1 other", text)

    def test_remove_complete_block_preserves_other_lines(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hosts = Path(tmp) / "hosts"
            hosts.write_text(
                "\n".join(
                    [
                        "127.0.0.1 localhost",
                        "# nexus-edge-proxy BEGIN (localhost.com)",
                        "127.0.0.1 minio.localhost.com",
                        "# nexus-edge-proxy END (localhost.com)",
                        "10.0.0.1 other",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            proc = self._run("remove", hosts)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            text = hosts.read_text(encoding="utf-8")
            self.assertNotIn("nexus-edge-proxy", text)
            self.assertIn("127.0.0.1 localhost", text)
            self.assertIn("10.0.0.1 other", text)


if __name__ == "__main__":
    unittest.main()
