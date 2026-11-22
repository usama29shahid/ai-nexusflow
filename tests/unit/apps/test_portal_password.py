"""Password rules for the website stay aligned with GoTrue."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_rules():
    path = REPO_ROOT / "apps" / "portal" / "password_rules.py"
    spec = importlib.util.spec_from_file_location("portal_password_rules", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["password_rules"] = module
    spec.loader.exec_module(module)
    return module


def _load_auth_flow():
    _load_rules()
    path = REPO_ROOT / "apps" / "portal" / "auth_flow.py"
    spec = importlib.util.spec_from_file_location("portal_auth_flow", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _ApiError(Exception):
    def __init__(self, status: int, message: str, code: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code


class _Retryable(_ApiError):
    pass


_Retryable.__name__ = "AuthRetryableError"
_ApiError.__name__ = "AuthApiError"


class _InvalidJwt(Exception):
    def __init__(self) -> None:
        super().__init__("invalid JWT: http://kong:8000")
        self.message = self.args[0]


_InvalidJwt.__name__ = "AuthInvalidJwtError"


class _WeakPassword(Exception):
    def __init__(self) -> None:
        super().__init__("Password should contain at least one character of each class")
        self.message = self.args[0]


_WeakPassword.__name__ = "AuthWeakPasswordError"


class PortalAuthFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.flow = _load_auth_flow()

    def test_sign_in_skips_the_signup_password_checklist(self) -> None:
        self.assertIsNone(self.flow.account_form_error("Sign in", "person@example.com", "short"))

    def test_create_account_still_requires_the_password_shape(self) -> None:
        message = self.flow.account_form_error("Create account", "person@example.com", "short")
        self.assertIsNotNone(message)
        self.assertIn("8 characters", message)

    def test_auth_errors_hide_raw_text_and_internal_hosts(self) -> None:
        taken = _ApiError(422, "User already registered at http://kong:8000")
        shown = self.flow.public_auth_message(taken, creating=True)
        self.assertEqual(shown, self.flow.SIGN_UP_FAILED)
        self.assertNotIn("kong", shown)
        self.assertEqual(
            self.flow.public_auth_message(_InvalidJwt(), creating=False),
            self.flow.SIGN_IN_FAILED,
        )
        unavailable = self.flow.public_auth_message(
            _Retryable(503, "timeout talking to http://kong:8000"),
            creating=False,
        )
        self.assertEqual(unavailable, self.flow.AUTH_UNAVAILABLE)
        weak = self.flow.public_auth_message(_WeakPassword(), creating=True)
        self.assertIn("8 characters", weak)
        self.assertNotIn("each class", weak)

    def test_only_a_rejected_session_clears_saved_tokens(self) -> None:
        self.assertTrue(self.flow.session_failure_clears_tokens(_ApiError(401, "invalid refresh")))
        self.assertTrue(self.flow.session_failure_clears_tokens(_InvalidJwt()))
        self.assertTrue(
            self.flow.session_failure_clears_tokens(
                _ApiError(404, "User from sub claim in JWT does not exist", "user_not_found")
            )
        )
        self.assertTrue(self.flow.session_failure_clears_tokens(_ApiError(422, "session rejected")))
        self.assertFalse(self.flow.session_failure_clears_tokens(_ApiError(500, "unexpected_failure")))
        self.assertFalse(self.flow.session_failure_clears_tokens(_ApiError(429, "slow down")))
        self.assertFalse(self.flow.session_failure_clears_tokens(_Retryable(503, "upstream timeout")))
        self.assertFalse(self.flow.session_failure_clears_tokens(ConnectionError("http://kong:8000")))
        self.assertFalse(self.flow.session_failure_clears_tokens(TimeoutError("timed out")))
        unknown = type("AuthUnknownError", (Exception,), {})("html 404 from http://kong:8000")
        self.assertTrue(self.flow.session_failure_clears_tokens(unknown))
        self.assertTrue(self.flow.session_failure_clears_tokens(RuntimeError("unexpected")))

    def test_empty_auth_response_is_not_a_usable_session(self) -> None:
        class _Response:
            session = None

        self.assertIsNone(self.flow.session_from_auth_response(_Response()))

        class _User:
            id = "user-1"

        class _Session:
            user = _User()

        class _SignedIn:
            session = _Session()

        signed_in = _SignedIn()
        self.assertIs(self.flow.session_from_auth_response(signed_in), signed_in.session)

    def test_sign_in_without_a_session_does_not_say_the_account_was_created(self) -> None:
        level, text = self.flow.notice_when_session_missing(creating=False)
        self.assertEqual(level, "error")
        self.assertEqual(text, self.flow.SIGN_IN_FAILED)
        created_level, created_text = self.flow.notice_when_session_missing(creating=True)
        self.assertEqual((created_level, created_text), ("info", self.flow.ACCOUNT_CREATED))


class PortalPasswordTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rules = _load_rules()

    def test_rejects_short_and_simple_passwords(self) -> None:
        problems = self.rules.password_problems("short")
        self.assertGreaterEqual(len(problems), 2)

    def test_accepts_a_password_with_every_class(self) -> None:
        self.assertEqual(self.rules.password_problems("Nexus-flow1"), [])

    def test_gotrue_compose_uses_the_same_classes(self) -> None:
        compose = (REPO_ROOT / "docker" / "supabase" / "docker-compose.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("GOTRUE_PASSWORD_MIN_LENGTH: ${GOTRUE_PASSWORD_MIN_LENGTH:-8}", compose)
        self.assertIn(self.rules.REQUIRED_CHARACTERS, compose)
        self.assertIn(
            "GOTRUE_SECURITY_REFRESH_TOKEN_ROTATION_ENABLED: ${GOTRUE_SECURITY_REFRESH_TOKEN_ROTATION_ENABLED:-true}",
            compose,
        )
        self.assertIn(
            "GOTRUE_SECURITY_REFRESH_TOKEN_REUSE_INTERVAL: ${GOTRUE_SECURITY_REFRESH_TOKEN_REUSE_INTERVAL:-10}",
            compose,
        )
        example = (REPO_ROOT / "docker" / "supabase" / ".env.example").read_text(encoding="utf-8")
        self.assertIn(
            'GOTRUE_PASSWORD_REQUIRED_CHARACTERS="' + self.rules.REQUIRED_CHARACTERS + '"',
            example,
        )
        self.assertIn("GOTRUE_SECURITY_REFRESH_TOKEN_REUSE_INTERVAL=10", example)

    def test_caddy_publishes_only_the_app_host(self) -> None:
        sites = (REPO_ROOT / "docker" / "caddy" / "sites.caddy").read_text(encoding="utf-8")
        self.assertIn("app.{$NEXUS_PUBLIC_HOST}", sites)
        self.assertIn("reverse_proxy portal:8501", sites)
        self.assertIn("X-Frame-Options SAMEORIGIN", sites)
        hosts = (REPO_ROOT / "scripts" / "proxy-hosts.sh").read_text(encoding="utf-8")
        self.assertIn("\n  app\n", hosts)
        compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        portal = compose.split("container_name: nexus-portal", 1)[1].split("volumes:", 1)[0]
        self.assertNotIn("8501:", portal)

    def test_signed_in_tool_links_use_the_laptop_addresses(self) -> None:
        path = REPO_ROOT / "apps" / "portal" / "tool_links.py"
        spec = importlib.util.spec_from_file_location("portal_tool_links", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        links = dict(module.TOOL_LINKS)
        self.assertEqual(
            links,
            {
                "Vault": "http://127.0.0.1:8200",
                "ClickHouse HTTP": "http://127.0.0.1:8123",
                "CloudBeaver": "http://127.0.0.1:8978",
                "MinIO console": "http://127.0.0.1:9001",
                "Airflow": "http://127.0.0.1:8081",
                "OpenObserve": "http://127.0.0.1:5080",
                "OpenMetadata": "http://127.0.0.1:8585",
                "Cube": "http://127.0.0.1:4000",
                "Supabase Studio": "http://127.0.0.1:3001",
                "dbt docs": "http://docs.localhost.com:8080",
                "Elementary": "http://elementary.localhost.com:8080",
            },
        )
        self.assertNotIn("http://app.localhost.com:8080", links.values())
        app_text = (REPO_ROOT / "apps" / "portal" / "app.py").read_text(encoding="utf-8")
        main_text = app_text[app_text.index("def main") :]
        public_branch = main_text.split("if user is None:", 1)[1].split("else:", 1)[0]
        signed_in_branch = main_text.split("else:", 1)[1]
        self.assertNotIn("_tool_sidebar()", public_branch)
        self.assertIn("_tool_sidebar()", signed_in_branch)
        self.assertIn('target="_blank"', app_text)
        self.assertIn('[data-testid="stExpandSidebarButton"] { visibility: visible; }', app_text)
        self.assertIn("position: fixed;", app_text)
        self.assertIn("margin-top: auto;", app_text)
        start_sh = (REPO_ROOT / "scripts" / "start.sh").read_text(encoding="utf-8")
        self.assertIn(
            'echo "Website profile portal has no host port; starting Caddy (proxy) with it."\n'
            '      export COMPOSE_PROFILES="${COMPOSE_PROFILES},proxy"',
            start_sh,
        )


if __name__ == "__main__":
    unittest.main()
