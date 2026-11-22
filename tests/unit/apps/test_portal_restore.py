"""The website page clears a saved login that Auth did not renew."""

from __future__ import annotations

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PORTAL_ROOT = REPO_ROOT / "apps" / "portal"
_MODULES_TOUCHED = ("streamlit", "supabase", "portal_app", "auth_flow", "password_rules")


class _ScriptStop(Exception):
    pass


class _SessionState(dict):
    def __getattr__(self, name: str):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: object) -> None:
        self[name] = value


def _install_import_stubs() -> _SessionState:
    state = _SessionState()
    streamlit = types.ModuleType("streamlit")
    streamlit._portal_test_stub = True
    streamlit.session_state = state

    def stop() -> None:
        raise _ScriptStop()

    def noop(*_args: object, **_kwargs: object) -> None:
        return None

    for name in (
        "set_page_config",
        "markdown",
        "error",
        "info",
        "caption",
        "subheader",
        "text_input",
        "radio",
        "button",
        "columns",
        "form",
        "form_submit_button",
        "chat_input",
        "chat_message",
        "write",
        "rerun",
    ):
        setattr(streamlit, name, noop)
    streamlit.stop = stop
    sys.modules["streamlit"] = streamlit

    supabase = types.ModuleType("supabase")
    supabase._portal_test_stub = True
    supabase.Client = object
    supabase.create_client = lambda *_args, **_kwargs: object()
    sys.modules["supabase"] = supabase
    return state


def _restore_modules(saved: dict[str, types.ModuleType | None]) -> None:
    for name, previous in saved.items():
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous


def _load_app():
    saved_env = {
        "SUPABASE_URL": os.environ.get("SUPABASE_URL"),
        "SUPABASE_ANON_KEY": os.environ.get("SUPABASE_ANON_KEY"),
    }
    saved_modules = {name: sys.modules.get(name) for name in _MODULES_TOUCHED}
    os.environ["SUPABASE_URL"] = ""
    os.environ["SUPABASE_ANON_KEY"] = ""
    sys.path.insert(0, str(PORTAL_ROOT))
    state = _install_import_stubs()
    module = None
    try:
        spec = importlib.util.spec_from_file_location("portal_app", PORTAL_ROOT / "app.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["portal_app"] = module
        try:
            spec.loader.exec_module(module)
        except _ScriptStop:
            pass
    finally:
        sys.path.remove(str(PORTAL_ROOT))
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        _restore_modules(saved_modules)
    assert module is not None
    module._state = state
    return module


class _Auth:
    def __init__(self, result: object) -> None:
        self._result = result

    def set_session(self, _access: str, _refresh: str) -> object:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class _Client:
    def __init__(self, result: object) -> None:
        self.auth = _Auth(result)


class _EmptyResponse:
    session = None


class PortalRestoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _load_app()
        cls.sessions = sys.modules["browser_session"]

    def setUp(self) -> None:
        self.app._state.clear()
        self.app.st.context = types.SimpleNamespace(cookies={})
        self.app._state.update(
            {
                "access_token": "old-access",
                "refresh_token": "old-refresh",
                "profile_user_id": "user-a",
                "profile_email": "a@example.com",
                "chat_messages": [{"role": "user", "content": "secret"}],
            }
        )

    def test_unrecognized_auth_error_returns_home_and_clears_the_previous_person(self) -> None:
        unknown = type("AuthUnknownError", (Exception,), {})("not json")
        user = self.app._restore_user(_Client(unknown))
        self.assertIsNone(user)
        for key in ("access_token", "refresh_token", "profile_user_id", "profile_email", "chat_messages"):
            self.assertNotIn(key, self.app._state)

    def test_empty_auth_reply_clears_email_and_chat(self) -> None:
        user = self.app._restore_user(_Client(_EmptyResponse()))
        self.assertIsNone(user)
        self.assertNotIn("profile_email", self.app._state)
        self.assertNotIn("chat_messages", self.app._state)
        self.assertNotIn("access_token", self.app._state)

    def test_import_stubs_are_not_left_installed(self) -> None:
        for name in ("streamlit", "supabase"):
            installed = sys.modules.get(name)
            self.assertFalse(getattr(installed, "_portal_test_stub", False))

    def test_short_outage_keeps_the_saved_login(self) -> None:
        retryable = type("AuthRetryableError", (Exception,), {"status": 503})("down")
        with self.assertRaises(_ScriptStop):
            self.app._restore_user(_Client(retryable))
        self.assertEqual(self.app._state["access_token"], "old-access")
        self.assertEqual(self.app._state["profile_email"], "a@example.com")
        self.assertEqual(self.app._state["chat_messages"][0]["content"], "secret")

    def test_refresh_restores_the_login_from_the_site_cookie(self) -> None:
        self.app._state.clear()
        session_id = self.sessions.save_login("kept-access", "kept-refresh")
        self.assertIsNotNone(session_id)
        self.app.st.context = types.SimpleNamespace(cookies={"nf_session": session_id})
        seen: dict[str, str] = {}

        class _User:
            id = "user-b"
            email = "b@example.com"

        class _Session:
            access_token = "rotated-access"
            refresh_token = "rotated-refresh"
            user = _User()

        class _Response:
            session = _Session()

        class _RememberingAuth:
            def set_session(self, access: str, refresh: str) -> object:
                seen["access"] = access
                seen["refresh"] = refresh
                return _Response()

        class _RememberingClient:
            auth = _RememberingAuth()

        user = self.app._restore_user(_RememberingClient())
        self.assertEqual(user.id, "user-b")
        self.assertEqual(seen["access"], "kept-access")
        self.assertEqual(seen["refresh"], "kept-refresh")
        self.assertEqual(self.app._state["access_token"], "rotated-access")
        self.assertNotIn("nf_signed_out", self.app._state)
        self.assertEqual(
            self.sessions.load_login(session_id or ""),
            ("rotated-access", "rotated-refresh"),
        )

    def test_sign_out_ignores_the_cookie_until_the_next_visit(self) -> None:
        session_id = self.sessions.save_login("kept-access", "kept-refresh")
        self.assertIsNotNone(session_id)
        self.app.st.context = types.SimpleNamespace(cookies={"nf_session": session_id})
        self.app._state["_login_sid"] = session_id
        self.app._clear_session()
        self.assertIsNone(self.sessions.load_login(session_id or ""))
        user = self.app._restore_user(_Client(_EmptyResponse()))
        self.assertIsNone(user)
        self.assertNotIn("access_token", self.app._state)
        self.app._state.pop("nf_signed_out", None)
        user = self.app._restore_user(_Client(_EmptyResponse()))
        self.assertIsNone(user)

    def test_cookie_script_is_sent_only_after_the_run_finishes(self) -> None:
        sent: list[str] = []

        def record(body: str, height: int = 0, width: int = 0) -> None:
            sent.append(body)

        self.app.st.components = types.SimpleNamespace(v1=types.SimpleNamespace(html=record))
        self.app.st.context = types.SimpleNamespace(cookies={}, url="https://app.example.com")

        class _Stored:
            access_token = "secret-access"
            refresh_token = "secret-refresh"

        self.app._store_session(_Stored())
        self.assertEqual(sent, [])
        self.app._flush_browser_cookie()
        self.assertEqual(len(sent), 1)
        self.assertEqual(self.app._state["access_token"], "secret-access")
        self.assertNotIn("secret-access", sent[0])
        self.assertNotIn("secret-refresh", sent[0])
        self.assertIn("Secure", sent[0])
        self.app._flush_browser_cookie()
        self.assertEqual(len(sent), 1)
        self.app._clear_session()
        self.assertEqual(len(sent), 1)
        self.app._flush_browser_cookie()
        self.assertEqual(len(sent), 2)
        self.assertIn("Max-Age=0", sent[1])
        self.assertIn("Secure", sent[1])

    def test_session_cookie_round_trip_rejects_garbage(self) -> None:
        session_id = self.sessions.save_login("access.jwt", "refresh")
        self.assertEqual(
            self.sessions.load_login(session_id or ""),
            ("access.jwt", "refresh"),
        )
        same_id = self.sessions.save_login(
            "next-access",
            "next-refresh",
            session_id,
            expected_refresh="refresh",
        )
        self.assertEqual(same_id, session_id)
        self.assertIsNone(
            self.sessions.save_login(
                "stale-access",
                "stale-refresh",
                session_id,
                expected_refresh="refresh",
            )
        )
        self.assertEqual(
            self.sessions.load_login(session_id or ""),
            ("next-access", "next-refresh"),
        )
        self.sessions.delete_login(session_id or "")
        self.assertIsNone(
            self.sessions.save_login(
                "again-access",
                "again-refresh",
                session_id,
                expected_refresh="next-refresh",
            )
        )
        self.assertIsNone(self.sessions.save_login("bad\ntoken", "refresh"))
        self.assertFalse(self.sessions.valid_session_id("not a cookie"))
        document = self.sessions.session_cookie_document(session_id, secure=False)
        self.assertIn("nf_session=", document)
        self.assertNotIn("access.jwt", document)
        self.assertNotIn("Secure", document)
        secure_clear = self.sessions.session_cookie_document(None, secure=True)
        self.assertIn("Max-Age=0", secure_clear)
        self.assertIn("Secure", secure_clear)
        plain_clear = self.sessions.session_cookie_document(None, secure=False)
        self.assertNotIn("Secure", plain_clear)

    def test_another_tab_sign_out_is_not_signed_back_in(self) -> None:
        session_id = self.sessions.save_login("tab-access", "tab-refresh")
        self.assertIsNotNone(session_id)
        self.app._state["_login_sid"] = session_id
        self.sessions.delete_login(session_id or "")

        class _MustNotRun:
            def set_session(self, _access: str, _refresh: str) -> object:
                raise AssertionError("a signed-out login was used again")

        user = self.app._restore_user(_MustNotRun())
        self.assertIsNone(user)
        self.assertNotIn("access_token", self.app._state)
        self.assertNotIn("_login_sid", self.app._state)
        self.assertIsNone(self.sessions.load_login(session_id or ""))

    def test_open_tab_uses_the_refresh_token_stored_by_the_other_tab(self) -> None:
        session_id = self.sessions.save_login("access-v1", "refresh-v1")
        self.sessions.save_login(
            "access-v2",
            "refresh-v2",
            session_id,
            expected_refresh="refresh-v1",
        )
        self.app._state["access_token"] = "access-v1"
        self.app._state["refresh_token"] = "refresh-v1"
        self.app._state["_login_sid"] = session_id
        seen: dict[str, str] = {}

        class _User:
            id = "user-b"

        class _Session:
            access_token = "access-v2"
            refresh_token = "refresh-v2"
            user = _User()

        class _Response:
            session = _Session()

        class _Auth:
            def set_session(self, access: str, refresh: str) -> object:
                seen["access"] = access
                seen["refresh"] = refresh
                return _Response()

        class _ClientSeen:
            auth = _Auth()

        user = self.app._restore_user(_ClientSeen())
        self.assertEqual(user.id, "user-b")
        self.assertEqual(seen["access"], "access-v2")
        self.assertEqual(seen["refresh"], "refresh-v2")

    def test_failed_refresh_keeps_a_login_another_tab_replaced(self) -> None:
        session_id = self.sessions.save_login("access-v2", "refresh-v2")
        self.app._state["_login_sid"] = session_id
        reruns: list[str] = []

        def stop_rerun() -> None:
            reruns.append("rerun")
            raise _ScriptStop()

        self.app.st.rerun = stop_rerun
        try:
            with self.assertRaises(_ScriptStop):
                self.app._drop_failed_login("refresh-v1")
        finally:
            self.app.st.rerun = lambda *_args, **_kwargs: None
        self.assertEqual(reruns, ["rerun"])
        self.assertEqual(
            self.sessions.load_login(session_id or ""),
            ("access-v2", "refresh-v2"),
        )
        self.assertNotIn("nf_signed_out", self.app._state)
        self.assertEqual(self.app._state["_login_sid"], session_id)
        self.app._drop_failed_login("refresh-v1")
        self.assertEqual(reruns, ["rerun"])
        self.assertEqual(
            self.sessions.load_login(session_id or ""),
            ("access-v2", "refresh-v2"),
        )

    def test_save_after_sign_out_does_not_mint_a_new_login(self) -> None:
        session_id = self.sessions.save_login("kept-access", "kept-refresh")
        self.assertIsNotNone(session_id)
        self.app._state["_login_sid"] = session_id
        seen: dict[str, str] = {}

        class _User:
            id = "user-b"

        class _Session:
            access_token = "kept-access"
            refresh_token = "kept-refresh"
            user = _User()

        class _Response:
            session = _Session()

        class _Auth:
            def set_session(_self, access: str, refresh: str) -> object:
                seen["refresh"] = refresh
                self.sessions.delete_login(session_id or "")
                return _Response()

        class _ClientDelete:
            auth = _Auth()

        user = self.app._restore_user(_ClientDelete())
        self.assertEqual(seen["refresh"], "kept-refresh")
        self.assertIsNone(user)
        self.assertNotIn("access_token", self.app._state)
        self.assertNotIn("_login_sid", self.app._state)
        wanted = self.app._state.get("_browser_cookie_wanted")
        self.assertTrue(wanted in (None, ""))
        self.assertIsNone(self.sessions.load_login(session_id or ""))

    def test_save_does_not_overwrite_a_newer_refresh_token(self) -> None:
        session_id = self.sessions.save_login("access-v2", "refresh-v2")
        self.assertIsNotNone(session_id)
        self.app._state["_login_sid"] = session_id
        reruns: list[str] = []

        class _User:
            id = "user-b"

        class _Session:
            access_token = "access-v2"
            refresh_token = "refresh-v2"
            user = _User()

        class _Response:
            session = _Session()

        class _Auth:
            def set_session(_self, _access: str, _refresh: str) -> object:
                self.sessions.save_login(
                    "access-v3",
                    "refresh-v3",
                    session_id,
                    expected_refresh="refresh-v2",
                )
                return _Response()

        class _ClientReplace:
            auth = _Auth()

        def stop_rerun() -> None:
            reruns.append("rerun")
            raise _ScriptStop()

        self.app.st.rerun = stop_rerun
        try:
            with self.assertRaises(_ScriptStop):
                self.app._restore_user(_ClientReplace())
        finally:
            self.app.st.rerun = lambda *_args, **_kwargs: None
        self.assertEqual(reruns, ["rerun"])
        self.assertEqual(
            self.sessions.load_login(session_id or ""),
            ("access-v3", "refresh-v3"),
        )
        self.assertEqual(self.app._state.get("_login_sid"), session_id)
        self.assertNotIn("access_token", self.app._state)


if __name__ == "__main__":
    unittest.main()
