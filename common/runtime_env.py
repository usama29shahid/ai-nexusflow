"""Host vs orchestrated runtime environment loading.

Manual Cursor / ``uv run`` loads ``.env`` and optional Vault Agent ``secrets.env``.
Airflow ``nexus-elt`` jobs set ``NEXUS_ELT_JOB=1`` and already receive env via
``docker run --env-file`` / ``-e`` — skip file loads so Compose DNS is not
overwritten if secrets ever include host keys.
"""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: Path, *, overwrite: bool = False) -> None:
    """Load ``KEY=VALUE`` lines into ``os.environ``.

    Missing or unreadable files are skipped (no raise) so a locked Vault Agent
    ``secrets.env`` does not abort a manual host run.
    """
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if overwrite:
            os.environ[key] = value
        else:
            os.environ.setdefault(key, value)


def load_runtime_env(repo_root: Path) -> None:
    """Load host env files unless this process is an orchestrated ELT job."""
    if os.environ.get("NEXUS_ELT_JOB") == "1":
        return
    root = Path(repo_root)
    load_dotenv(root / ".env")
    secrets_file = root / ".nexusflow" / "secrets.env"
    if os.environ.get("NEXUS_SECRETS_BACKEND", "env") == "vault" and secrets_file.is_file():
        load_dotenv(secrets_file, overwrite=True)
