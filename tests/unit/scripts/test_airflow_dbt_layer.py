"""Preflight for scripts/airflow-dbt-layer.sh (no dbt hub)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "airflow-dbt-layer.sh"


def _missing(project: Path) -> str:
    proc = subprocess.run(
        ["bash", "-c", f'source "{SCRIPT}"; missing_dbt_package_names "$1"', "bash", str(project)],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout.strip()


def test_missing_when_package_project_file_absent(tmp_path: Path) -> None:
    (tmp_path / "package-lock.yml").write_text(
        "packages:\n  - name: dbt_utils\n    version: 1.4.1\n",
        encoding="utf-8",
    )
    (tmp_path / "dbt_packages" / "dbt_utils" / "macros").mkdir(parents=True)
    assert _missing(tmp_path) == "dbt_utils"


def test_complete_install_reports_nothing(tmp_path: Path) -> None:
    (tmp_path / "package-lock.yml").write_text(
        "packages:\n  - name: dbt_utils\n  - name: elementary\n",
        encoding="utf-8",
    )
    for name in ("dbt_utils", "elementary"):
        pkg = tmp_path / "dbt_packages" / name
        pkg.mkdir(parents=True)
        (pkg / "dbt_project.yml").write_text("name: x\n", encoding="utf-8")
    assert _missing(tmp_path) == ""


def test_missing_lock_is_reported(tmp_path: Path) -> None:
    assert _missing(tmp_path) == "package-lock.yml"


def _ensure(project: Path, uv_body: str) -> subprocess.CompletedProcess[str]:
    bindir = project / "bin"
    bindir.mkdir()
    uv = bindir / "uv"
    uv.write_text(uv_body, encoding="utf-8")
    uv.chmod(0o755)
    return subprocess.run(
        [
            "bash",
            "-c",
            f'source "{SCRIPT}"; ensure_dbt_packages "$1"',
            "bash",
            str(project),
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"},
    )


def test_complete_install_skips_dbt_deps(tmp_path: Path) -> None:
    (tmp_path / "package-lock.yml").write_text(
        "packages:\n  - name: dbt_utils\n",
        encoding="utf-8",
    )
    pkg = tmp_path / "dbt_packages" / "dbt_utils"
    pkg.mkdir(parents=True)
    (pkg / "dbt_project.yml").write_text("name: dbt_utils\n", encoding="utf-8")
    marker = tmp_path / "uv-called"
    proc = _ensure(tmp_path, f"#!/bin/sh\ntouch {marker}\nexit 99\n")
    assert proc.returncode == 0, proc.stderr
    assert not marker.exists()


def test_deps_that_leaves_packages_missing_exits(tmp_path: Path) -> None:
    (tmp_path / "package-lock.yml").write_text(
        "packages:\n  - name: dbt_utils\n",
        encoding="utf-8",
    )
    (tmp_path / "dbt_packages" / "dbt_utils").mkdir(parents=True)
    proc = _ensure(tmp_path, "#!/bin/sh\nexit 0\n")
    assert proc.returncode == 1
    assert "did not restore" in proc.stderr


def test_parallel_ensures_do_not_overlap_deps(tmp_path: Path) -> None:
    (tmp_path / "package-lock.yml").write_text(
        "packages:\n  - name: dbt_utils\n",
        encoding="utf-8",
    )
    (tmp_path / "dbt_packages" / "dbt_utils").mkdir(parents=True)
    log = tmp_path / "deps.log"
    uv_body = f"""#!/bin/sh
if [ -f "{tmp_path}/busy" ]; then echo overlap >> "{log}"; fi
touch "{tmp_path}/busy"
sleep 0.3
rm -f "{tmp_path}/busy"
echo ran >> "{log}"
"""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    uv = bindir / "uv"
    uv.write_text(uv_body, encoding="utf-8")
    uv.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bindir}:{env['PATH']}"
    cmd = ["bash", "-c", f'source "{SCRIPT}"; ensure_dbt_packages "$1"', "bash", str(tmp_path)]
    first = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    second = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    first.wait(timeout=10)
    second.wait(timeout=10)
    assert first.returncode == 1
    assert second.returncode == 1
    assert "overlap" not in log.read_text(encoding="utf-8")
    assert log.read_text(encoding="utf-8").count("ran") == 2
