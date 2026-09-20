"""Guards for scripts/minio_license.sh (sourced by start.sh / setup.sh; no Docker).

    uv run python tests/unit/scripts/test_minio_license.py
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LICENSE_SH = REPO_ROOT / "scripts" / "minio_license.sh"


class MinioLicenseGuardTest(unittest.TestCase):
    def _run(self, license_path: Path | None, *, make_dir: bool = False) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            default = root / ".nexusflow" / "minio.license"
            default.parent.mkdir(parents=True)
            env_line = "unset MINIO_LICENSE_FILE || true\n"
            if license_path is None:
                if make_dir:
                    default.mkdir()
                else:
                    default.write_text("license-bytes\n", encoding="utf-8")
            else:
                env_line = f"MINIO_LICENSE_FILE={str(license_path)!r}\n"
            script = root / "check.sh"
            script.write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env bash
                    set -euo pipefail
                    ROOT={str(root)!r}
                    # shellcheck source=/dev/null
                    source {LICENSE_SH.as_posix()!r}
                    {env_line}require_minio_license
                    echo OK
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

    def test_default_file_ok(self) -> None:
        proc = self._run(None)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("OK", proc.stdout)

    def test_missing_file_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "no-such.license"
            proc = self._run(missing)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Missing MinIO AIStor license", proc.stderr)

    def test_directory_fails(self) -> None:
        proc = self._run(None, make_dir=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("license path is a directory", proc.stderr)


if __name__ == "__main__":
    unittest.main()
