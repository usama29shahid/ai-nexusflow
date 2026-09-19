"""Guards for scripts/nexus_publish_bind.sh (sourced by start.sh; no Docker).

    uv run python tests/unit/scripts/test_start_publish_bind.py
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BIND_SH = REPO_ROOT / "scripts" / "nexus_publish_bind.sh"


class StartPublishBindTest(unittest.TestCase):
    def _run(self, mode: str, bind: str | None) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "check.sh"
            bind_line = (
                f"NEXUS_PUBLISH_BIND={bind!r}\n"
                if bind is not None
                else "unset NEXUS_PUBLISH_BIND || true\n"
            )
            script.write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    # shellcheck source=/dev/null
                    source {BIND_SH.as_posix()!r}
                    NEXUS_EDGE_MODE={mode!r}
                    {bind_line}nexus_resolve_publish_bind
                    echo OK_BIND="${{NEXUS_PUBLISH_BIND}}"
                    """
                ),
                encoding="utf-8",
            )
            script.chmod(0o755)
            return subprocess.run(
                ["bash", str(script)],
                cwd=REPO_ROOT,
                env={**os.environ},
                capture_output=True,
                text=True,
                check=False,
            )

    def test_vps_default_bind_ok(self) -> None:
        proc = self._run("vps", None)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("OK_BIND=127.0.0.1", proc.stdout)

    def test_vps_rejects_0_0_0_0(self) -> None:
        proc = self._run("vps", "0.0.0.0")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("cannot use NEXUS_PUBLISH_BIND=0.0.0.0", proc.stderr)

    def test_vps_rejects_ipv6_any(self) -> None:
        proc = self._run("vps", "::")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("cannot use NEXUS_PUBLISH_BIND=::", proc.stderr)

    def test_vps_rejects_bracketed_ipv6_any(self) -> None:
        proc = self._run("vps", "[::]")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("cannot use NEXUS_PUBLISH_BIND=[::]", proc.stderr)

    def test_local_allows_public_bind(self) -> None:
        proc = self._run("local", None)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("OK_BIND=0.0.0.0", proc.stdout)

    def test_vps_explicit_loopback_ok(self) -> None:
        proc = self._run("vps", "127.0.0.1")
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("OK_BIND=127.0.0.1", proc.stdout)


if __name__ == "__main__":
    unittest.main()
