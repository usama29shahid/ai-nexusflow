"""Sign-in decisions that do not need Streamlit or a live Auth server."""

from __future__ import annotations

from password_rules import password_problems, password_rules_text

SIGN_IN_FAILED = "That email and password were not accepted."
SIGN_UP_FAILED = "That account could not be created. Check the email and password."
AUTH_UNAVAILABLE = "The sign-in service is not reachable. Try again in a moment."
ACCOUNT_CREATED = "Account created. Sign in with the same email."
MISSING_FIELDS = "Enter an email address and a password."

_DEAD_SESSION = {
    "AuthInvalidJwtError",
    "AuthSessionMissingError",
    "AuthInvalidCredentialsError",
    "UserDoesntExist",
}
# These Auth replies mean the saved login is over. 404 is user_not_found.
_DEAD_API_CODES = {
    "bad_jwt",
    "invalid_jwt",
    "no_authorization",
    "user_not_found",
    "session_not_found",
    "user_banned",
    "invalid_credentials",
}


def account_form_error(mode: str, email: str, password: str) -> str | None:
    """Block the form before Auth is called. Password shape applies only to new accounts."""
    if "@" not in email.strip() or not password:
        return MISSING_FIELDS
    if mode == "Create account":
        problems = password_problems(password)
        if problems:
            return " ".join(problems)
    return None


def public_auth_message(exc: BaseException, *, creating: bool) -> str:
    """A message safe to show. Never includes Auth text or internal hostnames."""
    names = {cls.__name__ for cls in type(exc).__mro__}
    if "AuthRetryableError" in names or "AuthUnknownError" in names:
        return AUTH_UNAVAILABLE
    if "AuthWeakPasswordError" in names:
        return password_rules_text()
    if creating:
        return SIGN_UP_FAILED
    return SIGN_IN_FAILED


def session_failure_clears_tokens(exc: BaseException) -> bool:
    """Drop the saved login unless this is a short Auth outage.

    A removed user, a bad token, and any reply the page does not recognize
    return the person to the public home. Rate limits, server errors, and
    network failures keep the tokens so a short outage does not sign them out.
    """
    names = {cls.__name__ for cls in type(exc).__mro__}
    if "AuthRetryableError" in names or names & {"ConnectionError", "TimeoutError"}:
        return False
    if names & _DEAD_SESSION:
        return True
    if "AuthApiError" in names:
        if getattr(exc, "code", None) in _DEAD_API_CODES:
            return True
        status = getattr(exc, "status", None)
        if status in (408, 429) or (isinstance(status, int) and status >= 500):
            return False
    return True


def session_from_auth_response(response: object) -> object | None:
    """A usable login has both a session and a user. Anything else must be discarded."""
    session = getattr(response, "session", None)
    if session is None or getattr(session, "user", None) is None:
        return None
    return session


def notice_when_session_missing(*, creating: bool) -> tuple[str, str]:
    """Level and text when Auth accepts the form but returns no session."""
    if creating:
        return ("info", ACCOUNT_CREATED)
    return ("error", SIGN_IN_FAILED)
