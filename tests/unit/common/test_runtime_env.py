"""Guards for common.runtime_env (no Compose).

    uv run python tests/unit/common/test_runtime_env.py
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from common.runtime_env import load_dotenv, load_runtime_env


class RuntimeEnvTest(unittest.TestCase):
    def test_elt_job_skips_file_loads(self) -> None:
        with patch.dict(os.environ, {"NEXUS_ELT_JOB": "1"}, clear=False):
            with patch("common.runtime_env.load_dotenv") as load:
                load_runtime_env(Path("/tmp/unused"))
                load.assert_not_called()

    def test_manual_loads_dotenv_then_optional_vault(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("NEXUS_ENV=dev\n", encoding="utf-8")
            nexus = root / ".nexusflow"
            nexus.mkdir()
            (nexus / "secrets.env").write_text(
                "CLICKHOUSE_PASSWORD=from-vault\n", encoding="utf-8"
            )
            env = {
                k: v
                for k, v in os.environ.items()
                if k not in {"NEXUS_ELT_JOB", "NEXUS_SECRETS_BACKEND", "CLICKHOUSE_PASSWORD"}
            }
            env["NEXUS_SECRETS_BACKEND"] = "vault"
            with patch.dict(os.environ, env, clear=True):
                load_runtime_env(root)
                self.assertEqual(os.environ.get("NEXUS_ENV"), "dev")
                self.assertEqual(os.environ.get("CLICKHOUSE_PASSWORD"), "from-vault")

    def test_load_dotenv_skips_unreadable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "locked.env"
            path.write_text("FOO=from-file\n", encoding="utf-8")
            with patch.dict(os.environ, {"FOO": "existing"}, clear=False):
                with patch.object(Path, "read_text", side_effect=PermissionError("locked")):
                    load_dotenv(path, overwrite=True)
                self.assertEqual(os.environ["FOO"], "existing")

    def test_load_dotenv_setdefault_vs_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.env"
            path.write_text("FOO=a\n", encoding="utf-8")
            with patch.dict(os.environ, {"FOO": "existing"}, clear=False):
                load_dotenv(path, overwrite=False)
                self.assertEqual(os.environ["FOO"], "existing")
                load_dotenv(path, overwrite=True)
                self.assertEqual(os.environ["FOO"], "a")


if __name__ == "__main__":
    unittest.main(verbosity=2)
