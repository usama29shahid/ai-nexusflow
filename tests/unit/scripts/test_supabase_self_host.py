"""Contracts for the self-hosted Supabase slice (no Docker).

    uv run python tests/unit/scripts/test_supabase_self_host.py
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
START_SH = REPO_ROOT / "scripts" / "start.sh"
VAULT_SH = REPO_ROOT / "scripts" / "vault-bootstrap.sh"
SEED_SH = REPO_ROOT / "scripts" / "supabase-vault-seed.sh"
RBAC_SH = REPO_ROOT / "scripts" / "supabase-rbac-bootstrap.sh"
ENSURE_ENV_SH = REPO_ROOT / "scripts" / "supabase-ensure-env.sh"
VAULT_SYNC_SH = REPO_ROOT / "scripts" / "supabase-vault-sync.sh"
COMPOSE_SH = REPO_ROOT / "scripts" / "supabase-compose.sh"
MIGRATION_002 = (
    REPO_ROOT
    / "docker"
    / "supabase"
    / "migrations"
    / "002_reader_catalog_select_admin_bypassrls.sql"
)
VECTOR_OTEL = REPO_ROOT / "docker" / "supabase" / "volumes" / "logs" / "vector-otel.yml"
VECTOR_UPSTREAM = REPO_ROOT / "docker" / "supabase" / "volumes" / "logs" / "vector.yml"
OO_SUPABASE_DASH = (
    REPO_ROOT / "docker" / "openobserve" / "dashboards" / "supabase-logs.json"
)
NEXUS_COMPOSE = REPO_ROOT / "docker" / "supabase" / "docker-compose.nexus.yml"


class SupabaseSelfHostTest(unittest.TestCase):
    def test_vector_otel_config_is_tracked_and_upstream_vector_yml_is_ignored(self) -> None:
        self.assertTrue(VECTOR_OTEL.is_file())
        tracked = subprocess.run(
            ["git", "check-ignore", "-q", "--", str(VECTOR_OTEL)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            tracked.returncode,
            1,
            "vector-otel.yml must not match .gitignore (exit 1 from check-ignore -q)",
        )
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", "--", str(VECTOR_UPSTREAM)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(ignored.returncode, 0, ignored.stderr)

    def test_vector_otel_yml_otlp_and_filter_contracts(self) -> None:
        """Catch regressions that previously broke lake/OO shipping (no Docker)."""
        text = VECTOR_OTEL.read_text(encoding="utf-8")
        self.assertIn("codec: otlp", text)
        self.assertIn("resourceLogs", text)
        self.assertIn('service.name', text)
        self.assertIn("supabase.component", text)
        # PostgREST stamp has colons inside the timestamp.
        self.assertIn(
            r"\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2} [+-]\d{4}",
            text,
        )
        self.assertNotIn(r"(?P<time>[^:]+): (?P<body>.*)", text)
        # DB: keep WARNING+ only; drop companions / LOG noise.
        self.assertIn("STATEMENT|HINT|CONTEXT|DETAIL", text)
        self.assertIn("WARNING|ERROR|FATAL|PANIC", text)
        self.assertIn("drop_on_abort: true", text)
        # Auth: never archive raw non-JSON / free-text GoTrue msg (emails).
        self.assertIn("auth log (non-json redacted)", text)
        self.assertIn("parse_json(msg)", text)
        self.assertIn('.message = "auth log"', text)
        self.assertIn('.supabase.error = "present"', text)
        self.assertNotIn(".supabase.error = string!(parsed.error)", text)
        self.assertNotIn("replace(raw_msg", text)
        self.assertNotIn("string(parsed.msg)", text)
        self.assertIn("api:\n  enabled: false", text)
        self.assertNotIn("address: 0.0.0.0:9001", text)

    def test_compose_clears_every_leaked_env_file_key(self) -> None:
        """Any shell var named in supabase.env must be unset before Compose."""
        text = COMPOSE_SH.read_text(encoding="utf-8")
        self.assertIn("supabase_clear_env_file_overrides", text)
        self.assertIn("--env-file \"${ENV_FILE}\"", text)
        self.assertNotIn("source \"${ENV_FILE}\"", text)
        self.assertNotIn("unset POSTGRES_PASSWORD JWT_SECRET", text)
        proc = self._bash(
            f"""
            source {COMPOSE_SH.as_posix()!r}
            envfile="$(mktemp)"
            cat >"$envfile" <<'EOF'
# comment
POSTGRES_PASSWORD=real-pg-password
JWT_SECRET=real-jwt
export SECRET_KEY_BASE=real-secret
ANON_KEY=real-anon
EOF
            export POSTGRES_PASSWORD=leaked-pg
            export JWT_SECRET=leaked-jwt
            export SECRET_KEY_BASE=leaked-secret
            export ANON_KEY=leaked-anon
            export NEXUS_UNRELATED_KEEP=keep-me
            supabase_clear_env_file_overrides "$envfile"
            rm -f "$envfile"
            [[ -z "${{POSTGRES_PASSWORD+x}}" ]]
            [[ -z "${{JWT_SECRET+x}}" ]]
            [[ -z "${{SECRET_KEY_BASE+x}}" ]]
            [[ -z "${{ANON_KEY+x}}" ]]
            [[ "${{NEXUS_UNRELATED_KEEP}}" == keep-me ]]
            echo cleared
            """
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("cleared", proc.stdout)

    def test_ensure_env_symlink_and_placeholder_guard(self) -> None:
        text = ENSURE_ENV_SH.read_text(encoding="utf-8")
        self.assertIn("ln -sfn", text)
        self.assertIn("supabase_env_has_placeholders", text)
        self.assertIn("Adopting generated secrets", text)
        self.assertIn("Placeholder secrets still present", text)
        self.assertIn("refuse_divergent_sibling_clobber", text)
        self.assertIn("Refusing to replace", text)
        self.assertIn("NEXUSFLOW_ALLOW_ROOT_OVERRIDE", text)
        self.assertNotIn('echo "Supabase env exists: ${ENV_FILE}"\n  exit 0', text)

    def test_rbac_bootstrap_does_not_swallow_secret_load_failure(self) -> None:
        text = RBAC_SH.read_text(encoding="utf-8")
        self.assertIn("source \"${ROOT}/scripts/load-secrets.sh\"", text)
        self.assertNotIn("load-secrets.sh\" || true", text)
        self.assertNotIn("load-secrets.sh' || true", text)
        self.assertIn("def qident(name: str)", text)
        self.assertIn("create role {qi[user]}", text)
        self.assertNotIn("create role {user} login", text)

    def _realish_supabase_env(self, path: Path, *, suffix: str) -> None:
        path.write_text(
            "\n".join(
                [
                    f"JWT_SECRET=generated-jwt-secret-value-{suffix}-at-least-32-chars",
                    f"POSTGRES_PASSWORD=generated-pg-password-{suffix}",
                    f"ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.{suffix}.anon",
                    f"SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.{suffix}.service",
                    "DASHBOARD_PASSWORD=lab-dashboard",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    def test_ensure_env_refuses_divergent_sibling_env(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            supabase = root / "docker" / "supabase"
            nexus = root / ".nexusflow"
            supabase.mkdir(parents=True)
            nexus.mkdir(parents=True)
            (supabase / ".env.example").write_text(
                "JWT_SECRET=your-super-secret-jwt-token-with-at-least-32-characters-long\n"
                "POSTGRES_PASSWORD=your-postgres-password\n"
                "ANON_KEY=your-anon-key\n"
                "SERVICE_ROLE_KEY=your-service-role-key\n",
                encoding="utf-8",
            )
            self._realish_supabase_env(nexus / "supabase.env", suffix="canonical")
            self._realish_supabase_env(supabase / ".env", suffix="sibling")
            proc = subprocess.run(
                ["bash", str(ENSURE_ENV_SH)],
                cwd=REPO_ROOT,
                env={
                    **os.environ,
                    "NEXUSFLOW_ROOT": str(root),
                    "NEXUSFLOW_ALLOW_ROOT_OVERRIDE": "1",
                },
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("Refusing to replace", proc.stderr)
            self.assertTrue((supabase / ".env").is_file())
            self.assertFalse((supabase / ".env").is_symlink())

    def test_ensure_env_rejects_root_override_without_allow_flag(self) -> None:
        proc = subprocess.run(
            ["bash", str(ENSURE_ENV_SH)],
            cwd=REPO_ROOT,
            env={
                **os.environ,
                "NEXUSFLOW_ROOT": "/tmp/nexusflow-should-not-apply",
            },
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("NEXUSFLOW_ALLOW_ROOT_OVERRIDE=1", proc.stderr)

    def test_ensure_env_symlinks_matching_sibling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            supabase = root / "docker" / "supabase"
            nexus = root / ".nexusflow"
            supabase.mkdir(parents=True)
            nexus.mkdir(parents=True)
            (supabase / ".env.example").write_text(
                "JWT_SECRET=your-super-secret-jwt-token-with-at-least-32-characters-long\n"
                "POSTGRES_PASSWORD=your-postgres-password\n"
                "ANON_KEY=your-anon-key\n"
                "SERVICE_ROLE_KEY=your-service-role-key\n",
                encoding="utf-8",
            )
            self._realish_supabase_env(nexus / "supabase.env", suffix="same")
            self._realish_supabase_env(supabase / ".env", suffix="same")
            proc = subprocess.run(
                ["bash", str(ENSURE_ENV_SH)],
                cwd=REPO_ROOT,
                env={
                    **os.environ,
                    "NEXUSFLOW_ROOT": str(root),
                    "NEXUSFLOW_ALLOW_ROOT_OVERRIDE": "1",
                },
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertTrue((supabase / ".env").is_symlink())
            self.assertIn("Supabase env OK", proc.stdout)

    def test_vault_sync_fills_empty_api_fields_via_seed_helpers(self) -> None:
        """Behavioral: empty Vault anon_key is patched from supabase.env."""
        proc = self._bash(
            f"""
            source {SEED_SH.as_posix()!r}
            NEXUS_DIR="$(mktemp -d)"
            kv_base="secret/nexusflow/dev"
            cat >"$NEXUS_DIR/supabase.env" <<'EOF'
ANON_KEY=file-anon-key
SERVICE_ROLE_KEY=file-service-key
JWT_SECRET=file-jwt-secret-at-least-32-characters-long
POSTGRES_PASSWORD=file-pg-password
SUPABASE_PUBLISHABLE_KEY=
SUPABASE_SECRET_KEY=
EOF
            patched=0
            vault_exec() {{
              case "$*" in
                *"kv get"*supabase)
                  printf '%s' '{{"data":{{"data":{{"anon_key":"","service_role_key":"","jwt_secret":"","postgres_password":"","publishable_key":"","secret_key":""}}}}}}'
                  ;;
                *"kv patch"*supabase*)
                  patched=1
                  printf '%s\\n' "$*" >"$NEXUS_DIR/last_patch"
                  ;;
                *)
                  return 0
                  ;;
              esac
            }}
            SUPABASE_VAULT_CHANGED=0
            seed_supabase_api
            test "$SUPABASE_VAULT_CHANGED" = "1"
            test "$patched" = "1"
            grep -q 'anon_key=file-anon-key' "$NEXUS_DIR/last_patch"
            grep -q 'jwt_secret=file-jwt-secret-at-least-32-characters-long' "$NEXUS_DIR/last_patch"
            rm -rf "$NEXUS_DIR"
            """
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)

    def test_vector_otel_validate_via_docker_when_available(self) -> None:
        """Optional: `vector validate` with docker.sock (skip if Docker missing)."""
        if os.environ.get("SKIP_VECTOR_VALIDATE") == "1":
            self.skipTest("SKIP_VECTOR_VALIDATE=1")
        probe = subprocess.run(
            ["docker", "info"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if probe.returncode != 0:
            self.skipTest("docker not available")
        sock = Path("/var/run/docker.sock")
        if not sock.exists():
            self.skipTest("docker.sock missing")
        proc = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{VECTOR_OTEL}:/etc/vector/vector.yml:ro",
                "-v",
                f"{sock}:/var/run/docker.sock:ro",
                "timberio/vector:0.53.0-alpine",
                "validate",
                "--config-yaml",
                "/etc/vector/vector.yml",
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        combined = proc.stdout + proc.stderr
        self.assertEqual(proc.returncode, 0, combined)
        self.assertNotIn("Configuration error", combined)
        self.assertNotIn("Component errors", combined)

    def test_auth_health_failure_exits_before_migrate(self) -> None:
        text = START_SH.read_text(encoding="utf-8")
        fn = text[text.index("ensure_supabase()") : text.index("stop_supabase()")]
        fail_at = fn.index("Supabase API gateway did not become healthy")
        migrate_at = fn.index('"${ROOT}/scripts/supabase-migrate.sh"', fail_at)
        self.assertLess(fail_at, migrate_at)
        self.assertIn("exit 1", fn[fail_at:migrate_at])
        self.assertIn("api_ready=1", fn[:fail_at])
        # ANON_KEY must not be interpolated into curl -H argv.
        self.assertIn('curl -sf -o /dev/null -K "${curl_cfg}"', fn)
        self.assertNotIn('-H "apikey: $(grep', fn)
        self.assertIn('trap \'rm -f "${curl_cfg}"\' EXIT RETURN', fn)
        self.assertIn("supabase-vault-sync.sh", fn)

    def test_openobserve_supabase_dashboard_matches_vector_attrs(self) -> None:
        dash = OO_SUPABASE_DASH.read_text(encoding="utf-8")
        vector = VECTOR_OTEL.read_text(encoding="utf-8")
        for needle in (
            "service_name = 'supabase'",
            "supabase_component",
            "severity",
            "container_name",
            '"stream_type": "logs"',
        ):
            self.assertIn(needle, dash)
        # Vector OTLP attrs that OO flattens to the dashboard columns above.
        self.assertIn('"service.name"', vector)
        self.assertIn("supabase.component", vector)
        self.assertIn("container.name", vector)

    def test_vector_docker_sock_is_read_only(self) -> None:
        text = NEXUS_COMPOSE.read_text(encoding="utf-8")
        self.assertIn("/var/run/docker.sock:ro", text)

    def test_ready_line_puts_supabase_back_after_start(self) -> None:
        text = START_SH.read_text(encoding="utf-8")
        fn = text[text.index("start_profiles()") : text.index("stop_all()")]
        start_at = fn.index("ensure_supabase")
        restore_at = fn.index('export COMPOSE_PROFILES="${COMPOSE_PROFILES},supabase"')
        self.assertLess(start_at, restore_at)
        self.assertIn('export COMPOSE_PROFILES="supabase"', fn[restore_at:])

    def test_reader_and_catalog_select_and_admin_bypassrls(self) -> None:
        sql = MIGRATION_002.read_text(encoding="utf-8")
        self.assertIn("document_chunks_select_reader", sql)
        self.assertIn("profiles_select_reader", sql)
        self.assertIn("to nexus_reader, nexus_catalog", sql)
        self.assertIn("alter role nexus_admin bypassrls", sql)
        rbac = RBAC_SH.read_text(encoding="utf-8")
        self.assertIn("alter role {qi[admin_u]} bypassrls;", rbac)

    def test_vault_bootstrap_seeds_five_supabase_paths(self) -> None:
        text = VAULT_SH.read_text(encoding="utf-8")
        seed_helpers = SEED_SH.read_text(encoding="utf-8")
        sync = VAULT_SYNC_SH.read_text(encoding="utf-8")
        agent_at = text.index("Starting Vault Agent")
        seed = text[:agent_at]
        self.assertIn("seed_supabase_api", seed)
        self.assertIn("supabase-vault-seed.sh", seed)
        self.assertIn("supabase-vault-sync.sh", seed)
        api_fn = seed_helpers[
            seed_helpers.index("seed_supabase_api()") : seed_helpers.index(
                "seed_supabase_role()"
            )
        ]
        self.assertIn("Filling empty fields at ${path}", api_fn)
        self.assertIn('secret_json="$(supabase_read_secret_json "${path}")"', api_fn)
        fill_at = api_fn.index("Filling empty fields at ${path}")
        patch_at = api_fn.index("vault_exec kv patch", fill_at)
        create_at = api_fn.index('echo "  Seeding: ${path}"', patch_at)
        put_at = api_fn.index("vault_exec kv put", create_at)
        self.assertLess(api_fn.index("supabase_read_secret_json"), patch_at)
        self.assertLess(patch_at, put_at)
        role_fn = seed_helpers[seed_helpers.index("seed_supabase_role()") :]
        role_fill = role_fn.index("Filling empty password at ${path}")
        self.assertLess(role_fill, role_fn.index("vault_exec kv patch", role_fill))
        self.assertLess(
            role_fn.index("vault_exec kv patch", role_fill),
            role_fn.index("vault_exec kv put", role_fill),
        )
        self.assertNotIn('[[ -n "${current}" || -z "${anon}" ]]', api_fn)
        for path in (
            "supabase_loader",
            "supabase_reader",
            "supabase_catalog",
            "supabase_admin",
        ):
            self.assertIn(f"${{kv_base}}/{path}", seed)
        self.assertLess(seed.index("seed_supabase_api"), agent_at)
        self.assertIn("SUPABASE_VAULT_CHANGED", seed_helpers)
        self.assertIn("force-recreate vault-agent", sync)
        self.assertIn("seed_supabase_api", sync)
        timeout_at = sync.index("waiting for SUPABASE_ANON_KEY")
        self.assertIn("exit 1", sync[timeout_at : timeout_at + 200])
        self.assertNotIn("exit 0", sync[timeout_at : timeout_at + 200])
        start_fn = START_SH.read_text(encoding="utf-8")
        ensure = start_fn[
            start_fn.index("ensure_supabase()") : start_fn.index("stop_supabase()")
        ]
        self.assertIn('"${ROOT}/scripts/supabase-vault-sync.sh"', ensure)
        self.assertNotIn("supabase-vault-sync.sh\" || true", ensure)
        self.assertNotIn("supabase-vault-sync.sh' || true", ensure)

    def _bash(self, body: str) -> subprocess.CompletedProcess[str]:
        script = "#!/usr/bin/env bash\nset -euo pipefail\n" + textwrap.dedent(body)
        return subprocess.run(
            ["bash", "-c", script],
            cwd=REPO_ROOT,
            env={**os.environ},
            capture_output=True,
            text=True,
            check=False,
        )

    def test_merge_keeps_vault_value_and_fills_empty_under_set_e(self) -> None:
        proc = self._bash(
            f"""
            source {SEED_SH.as_posix()!r}
            fill=0
            if supabase_needs_fill "vault-anon" "file-anon"; then fill=1; fi
            if supabase_needs_fill "" "pub-from-file"; then fill=1; fi
            pub="$(supabase_merge_value "" "pub-from-file")"
            anon="$(supabase_merge_value "vault-anon" "file-anon")"
            printf 'fill=%s\\npub=%s\\nanon=%s\\n' "$fill" "$pub" "$anon"
            """
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("fill=1", proc.stdout)
        self.assertIn("pub=pub-from-file", proc.stdout)
        self.assertIn("anon=vault-anon", proc.stdout)

    def test_failed_secret_read_refuses_rewrite(self) -> None:
        proc = self._bash(
            f"""
            source {SEED_SH.as_posix()!r}
            vault_exec() {{ echo "vault down" >&2; return 1; }}
            if supabase_read_secret_json "secret/nexusflow/dev/supabase"; then
              echo rewrote
              exit 1
            fi
            echo refused
            """
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("refused", proc.stdout)
        self.assertNotIn("rewrote", proc.stdout)
        self.assertIn("Refusing to rewrite", proc.stderr)

    def test_json_read_treats_missing_field_as_empty(self) -> None:
        proc = self._bash(
            f"""
            source {SEED_SH.as_posix()!r}
            vault_exec() {{
              printf '%s' '{{"data":{{"data":{{"anon_key":"vault-anon"}}}}}}'
            }}
            json="$(supabase_read_secret_json "secret/nexusflow/dev/supabase")"
            pub="$(supabase_secret_field "$json" publishable_key)"
            anon="$(supabase_secret_field "$json" anon_key)"
            merged_pub="$(supabase_merge_value "$pub" "from-file")"
            merged_anon="$(supabase_merge_value "$anon" "file-anon")"
            printf 'pub=%s\\nanon=%s\\n' "$merged_pub" "$merged_anon"
            """
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("pub=from-file", proc.stdout)
        self.assertIn("anon=vault-anon", proc.stdout)


if __name__ == "__main__":
    unittest.main()
