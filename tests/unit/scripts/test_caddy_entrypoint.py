"""Guards for docker/caddy/docker-entrypoint.sh mode checks (no Docker daemon).

    uv run python tests/unit/scripts/test_caddy_entrypoint.py
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ENTRYPOINT = REPO_ROOT / "docker" / "caddy" / "docker-entrypoint.sh"
CADDY_DIR = REPO_ROOT / "docker" / "caddy"
START_SH = REPO_ROOT / "scripts" / "start.sh"
# Default frozen clock for most tests.
_FAKE_NOW = 1_700_000_000


class CaddyEntrypointTest(unittest.TestCase):
    def _run(
        self,
        env: dict[str, str],
        *,
        now: int = _FAKE_NOW,
    ) -> tuple[subprocess.CompletedProcess[str], str, str]:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            caddy_etc = tmp_path / "caddy"
            caddy_etc.mkdir()
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()
            fake = bin_dir / "caddy"
            fake.write_text(
                "#!/bin/sh\n"
                "echo 'caddy hash-password must not be used' >&2\n"
                "exit 1\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            clock = bin_dir / "date"
            clock.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = '+%s' ]; then\n"
                f"  printf '%s\\n' {now}\n"
                "  exit 0\n"
                "fi\n"
                "echo \"unexpected date args: $*\" >&2\n"
                "exit 1\n",
                encoding="utf-8",
            )
            clock.chmod(0o755)
            htpasswd = bin_dir / "htpasswd"
            htpasswd.write_text(
                "#!/bin/sh\n"
                "cat >/dev/null\n"
                "user_arg=''\n"
                "for arg in \"$@\"; do\n"
                "  case \"$arg\" in\n"
                "    -*) ;;\n"
                "    *) user_arg=\"$arg\" ;;\n"
                "  esac\n"
                "done\n"
                "printf '%s\\n' \"${user_arg}:\\$2a\\$14\\$fixedtesthash\"\n",
                encoding="utf-8",
            )
            htpasswd.chmod(0o755)
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
            merged = {
                **os.environ,
                "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
                **env,
            }
            if "NEXUS_DOCS_BASIC_AUTH_USER" not in env:
                merged["NEXUS_DOCS_BASIC_AUTH_USER"] = "nexus"
            if "NEXUS_DOCS_BASIC_AUTH_PASSWORD" not in env:
                merged["NEXUS_DOCS_BASIC_AUTH_PASSWORD"] = "test-password"
            merged["NEXUS_CADDY_GATE_REFRESH"] = "0"
            proc = subprocess.run(
                ["sh", str(wrapped)],
                cwd=REPO_ROOT,
                env=merged,
                capture_output=True,
                text=True,
                check=False,
            )
            snippet_path = caddy_etc / "docs-basicauth.caddy"
            snippet = snippet_path.read_text(encoding="utf-8") if snippet_path.is_file() else ""
            sites_path = caddy_etc / "sites.caddy"
            sites = sites_path.read_text(encoding="utf-8") if sites_path.is_file() else ""
            return proc, snippet, sites

    def _ttl(self) -> int:
        ttl = re.search(r"^DOCS_GATE_TTL=(\d+)$", ENTRYPOINT.read_text(encoding="utf-8"), re.M)
        self.assertIsNotNone(ttl)
        return int(ttl.group(1))

    def _gate(self, password: str = "test-password", *, now: int = _FAKE_NOW) -> str:
        ttl = self._ttl()
        window = now // ttl
        return hashlib.sha256(f"cube-docs-gate-v2:{password}:{window}".encode()).hexdigest()

    def _max_age(self, *, now: int = _FAKE_NOW) -> int:
        ttl = self._ttl()
        return ttl - (now % ttl)

    def _assert_cookie_only_on_2xx(self, sites: str) -> None:
        # One shared snippet; both Cube 2xx paths import it.
        self.assertEqual(sites.count("(docs_gate_set_cookie)"), 1)
        self.assertEqual(sites.count("Set-Cookie"), 1)
        self.assertEqual(sites.count("import docs_gate_set_cookie"), 2)
        cube = sites.split("cube.{$NEXUS_PUBLIC_HOST}", 1)[1].split("docs.{$NEXUS_PUBLIC_HOST}", 1)[0]
        self.assertEqual(cube.count("handle_response"), 2)
        self.assertEqual(cube.count("status 2xx"), 2)
        self.assertEqual(cube.count("import docs_gate_set_cookie"), 2)
        self.assertNotIn("Set-Cookie", cube)
        # Exact cookie match — not header Cookie *docs_gate=…* (substring bypass).
        self.assertIn("header_regexp Cookie", cube)
        self.assertIn("(^|;\\s*)docs_gate=", cube)
        self.assertIn("(;|$)", cube)
        self.assertNotIn("*docs_gate=", cube)
        # Each cookie import sits under a reverse_proxy that matches status 2xx only
        # (@ok / @signed_in + handle_response). 401 never reaches the Set-Cookie snippet.
        for match in re.finditer(r"import docs_gate_set_cookie", cube):
            before = cube[: match.start()]
            block = before[before.rindex("reverse_proxy") :]
            self.assertIn("status 2xx", block)
            self.assertIn("handle_response", block)
            self.assertLess(block.index("status 2xx"), block.index("handle_response"))
            self.assertLess(block.index("handle_response"), len(block))

    def _assert_refresh_loop_contract(self) -> None:
        text = ENTRYPOINT.read_text(encoding="utf-8")
        self.assertIn("DOCS_GATE_REFRESH_INTERVAL=3600", text)
        self.assertIn("DOCS_GATE_RETRY_DELAY=30", text)
        self.assertIn("docs_gate_sleep_delay", text)
        self.assertIn("refresh_docs_gate", text)
        self.assertIn('until refresh_docs_gate; do', text)
        self.assertIn('sleep "${DOCS_GATE_RETRY_DELAY}"', text)
        self.assertNotIn("will retry next window", text)
        self.assertNotIn("apply_docs_gate || exit 0", text)
        # Failure path must not fall through to the long interval sleep.
        retry_at = text.index('sleep "${DOCS_GATE_RETRY_DELAY}"')
        until_at = text.index("until refresh_docs_gate")
        self.assertLess(until_at, retry_at)
        # reload re-adapts the Caddyfile; local mode must keep http:// or :80 dies.
        refresh_fn = text[text.index("refresh_docs_gate()") : text.index("\napply_docs_gate()")]
        self.assertIn('NEXUS_CADDY_SITE_SCHEME:-http://', refresh_fn)
        self.assertIn("caddy reload", refresh_fn)
        self.assertIn('${before}"="${after}"', refresh_fn.replace(" ", ""))
        apply_start = text.index("apply_docs_gate()")
        apply_fn = text[apply_start : text.index("\nwrite_docs_basic_auth\n", apply_start)]
        self.assertIn("rm -f \"${tmp}\"", apply_fn)
        self.assertIn("cmp -s", apply_fn)
        self.assertIn('if ! cp ', apply_fn)
        self.assertIn("if ! sed -i", apply_fn)

    def test_local_ok(self) -> None:
        proc, _snippet, _sites = self._run(
            {
                "NEXUS_EDGE_MODE": "local",
                "NEXUS_PUBLIC_HOST": "localhost.com",
                "NEXUS_CADDY_SITE_SCHEME": "",
            }
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("OK_WOULD_RUN_CADDY", proc.stdout)
        self.assertIn("(docs_basic_auth)", _snippet)
        self.assertIn("nexus $2a$14$fixedtesthash", _snippet)
        self.assertIn("basic_auth", _snippet)
        gate = self._gate()
        self.assertNotIn("__NEXUS_DOCS_GATE__", _sites)
        self.assertNotIn("__NEXUS_DOCS_COOKIE_MAX_AGE__", _sites)
        self.assertIn(f"docs_gate={gate}", _sites)
        self.assertEqual(self._max_age(), 6400)
        self.assertIn("Max-Age=6400", _sites)
        self.assertIn("docs gate cookie lines missing", ENTRYPOINT.read_text(encoding="utf-8"))
        self.assertNotIn("test-password", _sites)
        self.assertNotIn("; Secure", _sites)
        self._assert_cookie_only_on_2xx(_sites)
        self._assert_refresh_loop_contract()

    def test_max_age_tracks_remaining_window(self) -> None:
        later = _FAKE_NOW + 100
        proc, _, sites = self._run(
            {
                "NEXUS_EDGE_MODE": "local",
                "NEXUS_PUBLIC_HOST": "localhost.com",
                "NEXUS_CADDY_SITE_SCHEME": "",
            },
            now=later,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertEqual(self._max_age(now=later), 6300)
        self.assertIn("Max-Age=6300", sites)
        self.assertIn(f"docs_gate={self._gate(now=later)}", sites)

    def test_sleep_delay_prefers_refresh_interval_and_boundary(self) -> None:
        """docs_gate_sleep_delay: refresh interval, or sooner at the window edge."""
        ttl = self._ttl()
        text = ENTRYPOINT.read_text(encoding="utf-8")
        start = text.index("DOCS_GATE_TTL=")
        end = text.index("\napply_docs_gate()")
        # Real constants + docs_gate_sleep_delay from the entrypoint (no drift).
        helpers = text[start:end]
        self.assertIn("docs_gate_sleep_delay()", helpers)
        cases = [
            # Mid-window: refresh interval.
            (_FAKE_NOW, "3600"),
            # 90s before boundary: sleep until boundary.
            (((_FAKE_NOW // ttl) + 1) * ttl - 90, "90"),
            # Exact boundary: apply quickly.
            (((_FAKE_NOW // ttl) + 1) * ttl, "1"),
        ]
        for now, expected in cases:
            with self.subTest(now=now, expected=expected):
                with tempfile.TemporaryDirectory() as tmp:
                    bin_dir = Path(tmp) / "bin"
                    bin_dir.mkdir()
                    clock = bin_dir / "date"
                    clock.write_text(
                        "#!/bin/sh\n"
                        f"printf '%s\\n' {now}\n",
                        encoding="utf-8",
                    )
                    clock.chmod(0o755)
                    proc = subprocess.run(
                        ["sh", "-c", helpers + "\ndocs_gate_sleep_delay\n"],
                        env={**os.environ, "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}"},
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
                    self.assertEqual(proc.stdout.strip(), expected)

    def test_missing_docs_password_exits(self) -> None:
        proc, snippet, _sites = self._run(
            {
                "NEXUS_EDGE_MODE": "local",
                "NEXUS_PUBLIC_HOST": "localhost.com",
                "NEXUS_DOCS_BASIC_AUTH_USER": "nexus",
                "NEXUS_DOCS_BASIC_AUTH_PASSWORD": "",
            }
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("NEXUS_DOCS_BASIC_AUTH_USER and NEXUS_DOCS_BASIC_AUTH_PASSWORD are required", proc.stderr)
        self.assertEqual(snippet, "")

    def test_vps_rejects_http_scheme(self) -> None:
        proc, _snippet, _sites = self._run(
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
        proc, _snippet, _sites = self._run(
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
        proc, _snippet, _sites = self._run(
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
        proc, _snippet, _sites = self._run(
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
        gate = self._gate()
        self.assertIn(f"docs_gate={gate}", _sites)
        self.assertIn(f"Max-Age={self._max_age()}", _sites)
        self.assertIn("; Secure", _sites)
        self.assertNotIn("test-password", _sites)
        self._assert_cookie_only_on_2xx(_sites)

    def test_start_profiles_builds_caddy_and_requires_cube_sql(self) -> None:
        text = START_SH.read_text(encoding="utf-8")
        start_fn = text[text.index("start_profiles()") : text.index("stop_all()")]
        self.assertIn("require_cube_sql_password", start_fn)
        self.assertIn('*",cube,"*', start_fn)
        self.assertIn("build_caddy", start_fn)
        self.assertIn('*",proxy,"*', start_fn)
        self.assertLess(start_fn.index("build_caddy"), start_fn.index("docker compose up -d"))
        build_fn = text[text.index("build_caddy()") : text.index("ensure_cube()")]
        self.assertIn('NEXUS_CADDY_BUILT:-0', build_fn)
        self.assertIn("NEXUS_CADDY_BUILT=1", build_fn)
        ensure_proxy = text[text.index("ensure_proxy()") : text.index("ensure_signoz()")]
        self.assertIn("build_caddy", ensure_proxy)
        # Raw `docker compose` must not start Cube with an empty SQL password.
        compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("CUBEJS_SQL_PASSWORD:?", compose)
        self.assertNotIn("CUBEJS_SQL_PASSWORD:-}", compose)


if __name__ == "__main__":
    unittest.main()
