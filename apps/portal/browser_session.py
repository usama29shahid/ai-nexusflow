"""Keep a signed-in visit across a browser refresh.

Streamlit drops its server session on a full page refresh. The browser cookie
holds a random id only. The access token and refresh token stay in this
process, keyed by that id. The id is not placed in the address bar.

The page script sets the cookie because this app has no separate server that
can send an HttpOnly cookie. Page scripts can see the id. They cannot see the
tokens.
"""

from __future__ import annotations

import secrets
import threading
import time

COOKIE_NAME = "nf_session"
MAX_AGE_SECONDS = 14 * 24 * 60 * 60
_ID_ALPHABET = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
_MAX_TOKEN_LENGTH = 4000
_LOCK = threading.Lock()
_LOGINS: dict[str, tuple[str, str, float]] = {}


def save_login(
    access_token: str,
    refresh_token: str,
    session_id: str | None = None,
    expected_refresh: str | None = None,
) -> str | None:
    """Store tokens under a random id.

    An existing id is updated only when ``expected_refresh`` is still the
    stored refresh token. A removed id is not replaced with a new one.
    """
    if not _usable_token(access_token) or not _usable_token(refresh_token):
        return None
    expires_at = time.time() + MAX_AGE_SECONDS
    with _LOCK:
        _drop_expired_locked()
        if session_id:
            if not _known_locked(session_id):
                return None
            if expected_refresh is None or _LOGINS[session_id][1] != expected_refresh:
                return None
            _LOGINS[session_id] = (access_token, refresh_token, expires_at)
            return session_id
        new_id = secrets.token_urlsafe(32)
        _LOGINS[new_id] = (access_token, refresh_token, expires_at)
        return new_id


def load_login(session_id: str) -> tuple[str, str] | None:
    if not valid_session_id(session_id):
        return None
    with _LOCK:
        _drop_expired_locked()
        row = _LOGINS.get(session_id)
        if row is None:
            return None
        access_token, refresh_token, _expires_at = row
        return access_token, refresh_token


def delete_login(session_id: str) -> None:
    if not valid_session_id(session_id):
        return
    with _LOCK:
        _LOGINS.pop(session_id, None)


def delete_login_if_current(session_id: str, refresh_token: str) -> bool:
    """Drop the login only when it still holds this refresh token.

    Return False when another tab has already stored a newer token under this id.
    Return True when the login is gone.
    """
    if not valid_session_id(session_id):
        return True
    with _LOCK:
        row = _LOGINS.get(session_id)
        if row is None:
            return True
        if row[1] != refresh_token:
            return False
        _LOGINS.pop(session_id, None)
        return True


def valid_session_id(value: str) -> bool:
    return bool(value) and len(value) <= 128 and all(char in _ID_ALPHABET for char in value)


def session_cookie_document(value: str | None, *, secure: bool) -> str:
    """HTML document that stores or clears the login id on this host."""
    if value is None:
        flags = "Path=/; Max-Age=0; SameSite=Lax"
        if secure:
            flags += "; Secure"
        assignment = f"{COOKIE_NAME}=; {flags}"
    else:
        if not valid_session_id(value):
            return "<!doctype html>"
        flags = f"Path=/; Max-Age={MAX_AGE_SECONDS}; SameSite=Lax"
        if secure:
            flags += "; Secure"
        assignment = f"{COOKIE_NAME}={value}; {flags}"
    script = (
        "(function(){var c="
        + _js_string(assignment)
        + ";try{document.cookie=c;}catch(e){}"
        + "try{window.parent.document.cookie=c;}catch(e){}})();"
    )
    return "<!doctype html><meta charset=utf-8><script>" + script + "</script>"


def _usable_token(token: str) -> bool:
    return bool(token) and "\n" not in token and "\r" not in token and len(token) <= _MAX_TOKEN_LENGTH


def _known_locked(session_id: str) -> bool:
    return valid_session_id(session_id) and session_id in _LOGINS


def _drop_expired_locked() -> None:
    now = time.time()
    expired = [key for key, row in _LOGINS.items() if row[2] <= now]
    for key in expired:
        _LOGINS.pop(key, None)


def _js_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
