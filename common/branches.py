"""Read config/branches.yaml without a YAML dependency."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG = _REPO_ROOT / "config" / "branches.yaml"


def is_branch_enabled(name: str, config_path: Path | None = None) -> bool:
    """Return whether ``name`` is listed under branches: with enabled: true."""
    path = config_path or _DEFAULT_CONFIG
    text = path.read_text(encoding="utf-8")
    in_branch = False
    seen = False
    for raw in text.splitlines():
        if raw.startswith("  ") and not raw.startswith("    ") and raw.rstrip().endswith(":"):
            current = raw.strip()[:-1]
            in_branch = current == name
            if in_branch:
                seen = True
            continue
        if in_branch and "enabled:" in raw:
            return raw.split(":", 1)[1].strip().lower() == "true"
    if not seen:
        raise ValueError(f"unknown execution branch: {name}")
    raise ValueError(f"branch {name} has no enabled: key")
