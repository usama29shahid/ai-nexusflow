"""Public home and signed-in home for the NexusFlow website.

Auth uses the anon key against Supabase on the Compose network. The service-role
key is never read. Tokens stay in this process. The browser keeps only a
random id for this site, and that id is not put in the URL.
"""

from __future__ import annotations

import os
from typing import Any

import streamlit as st
from supabase import Client, create_client

from auth_flow import (
    AUTH_UNAVAILABLE,
    account_form_error,
    notice_when_session_missing,
    public_auth_message,
    session_failure_clears_tokens,
    session_from_auth_response,
)
from browser_session import (
    COOKIE_NAME,
    delete_login,
    delete_login_if_current,
    load_login,
    save_login,
    session_cookie_document,
    valid_session_id,
)
from password_rules import password_rules_text
from tool_links import TOOL_LINKS

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

PAGE_CSS = """
<style>
  [data-testid="stAppViewContainer"] { top: 4.25rem !important; }
  [data-testid="stHeader"] {
    height: 0 !important;
    min-height: 0 !important;
    overflow: visible !important;
    background: transparent !important;
  }
  [data-testid="stToolbar"], footer { visibility: hidden; }
  [data-testid="stExpandSidebarButton"] { visibility: visible; }
  [data-testid="stExpandSidebarButton"],
  [data-testid="stSidebarCollapseButton"] {
    position: fixed !important;
    top: 1.15rem !important;
    left: 0.85rem !important;
    z-index: 1000006 !important;
    margin: 0 !important;
  }
  [data-testid="stSidebarHeader"] {
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    overflow: visible !important;
  }
  [data-testid="stLogoSpacer"] { display: none !important; }
  [data-testid="stMainBlockContainer"] { padding-top: 1.35rem !important; }
  [data-testid="stMainBlockContainer"] > .stVerticalBlock {
    min-height: calc(100dvh - 8rem);
    display: flex;
    flex-direction: column;
  }
  [data-testid="stElementContainer"]:has(.nf-header) {
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: visible !important;
  }
  [data-testid="stElementContainer"]:has(.nf-foot) { margin-top: auto; }
  .nf-header {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 1000002;
    height: 4.25rem;
    box-sizing: border-box;
    display: flex;
    align-items: center;
    padding: 0 1.5rem 0 3.4rem;
    background: #161b22;
    border-bottom: 1px solid rgba(255,255,255,0.10);
  }
  .block-container { max-width: 1080px; }
  .nf-kicker { letter-spacing: 0.16em; text-transform: uppercase; font-size: 0.82rem;
               font-weight: 650; color: #e7eeea; margin: 0; }
  .nf-tag { margin: 0.12rem 0 0; color: #8b9993; font-size: 0.84rem; }
  .nf-title { font-size: 2.4rem; line-height: 1.1; font-weight: 650; margin: 0 0 0.6rem; }
  .nf-lead { font-size: 1.05rem; color: #d5ddd8; margin-bottom: 1.2rem; }
  .nf-card { border: 1px solid rgba(255,255,255,0.08); border-radius: 16px;
             padding: 1.1rem 1.2rem 0.4rem; background: rgba(255,255,255,0.03); }
  .nf-lock { color: #9aa8a2; font-size: 0.92rem; }
  .nf-top { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; }
  .nf-foot { color: #9aa8a2; font-size: 0.85rem; margin: 0; padding-top: 1.25rem; }
  a.nf-tool { display: block; padding: 0.35rem 0; color: inherit; text-decoration: none; }
  a.nf-tool:hover { color: #e7eeea; }
  [data-testid="stElementContainer"]:has(iframe) { display: none !important; }
</style>
"""


def _page_header() -> None:
    st.markdown(
        '<div class="nf-header">'
        "<div>"
        '<p class="nf-kicker">AI-NexusFlow</p>'
        '<p class="nf-tag">The front door for this lab.</p>'
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def _page_footer() -> None:
    st.markdown(
        '<p class="nf-foot">Tool links open on this computer when the SSH tunnel is up.</p>',
        unsafe_allow_html=True,
    )


def _tool_sidebar() -> None:
    with st.sidebar:
        st.subheader("Lab tools")
        st.caption("Each link opens in a new tab.")
        for label, url in TOOL_LINKS:
            st.markdown(
                f'<a class="nf-tool" href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>',
                unsafe_allow_html=True,
            )


def _require_config() -> None:
    if SUPABASE_URL and SUPABASE_ANON_KEY:
        return
    st.error("The website is missing its Supabase connection settings.")
    st.stop()


def _client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def _cookie_header() -> str:
    context = getattr(st, "context", None)
    cookies = getattr(context, "cookies", None) if context is not None else None
    if cookies is None:
        return ""
    try:
        raw = cookies.get(COOKIE_NAME, "")
    except Exception:
        return ""
    return str(raw or "")


def _cookie_is_secure() -> bool:
    context = getattr(st, "context", None)
    url = str(getattr(context, "url", "") or "") if context is not None else ""
    return url.startswith("https://")


def _queue_browser_cookie(value: str | None) -> None:
    """Remember the cookie to send. A later finished run actually sends it.

    Sign-in and sign-out call st.rerun(), and that discards any script drawn
    in the same run. The id stays queued until a run is allowed to finish.
    """
    st.session_state["_browser_cookie_wanted"] = "" if value is None else value


def _flush_browser_cookie() -> None:
    if "_browser_cookie_wanted" not in st.session_state:
        return
    wanted = st.session_state["_browser_cookie_wanted"]
    if st.session_state.get("_browser_cookie_sent") == wanted:
        return
    components = getattr(st, "components", None)
    html = getattr(getattr(components, "v1", None), "html", None)
    if html is None:
        return
    document = session_cookie_document(
        None if wanted == "" else str(wanted),
        secure=_cookie_is_secure(),
    )
    html(document, height=0, width=0)
    st.session_state["_browser_cookie_sent"] = wanted


def _store_session(session: Any, *, expected_refresh: str | None = None) -> bool:
    """Save the login. Return False when this tab must not keep a private copy."""
    current_id = st.session_state.get("_login_sid")
    session_id = save_login(
        session.access_token,
        session.refresh_token,
        str(current_id) if current_id else None,
        expected_refresh=expected_refresh if current_id else None,
    )
    if not session_id:
        if current_id:
            st.session_state.pop("access_token", None)
            st.session_state.pop("refresh_token", None)
            if load_login(str(current_id)) is None:
                st.session_state.pop("_login_sid", None)
        return False
    st.session_state.access_token = session.access_token
    st.session_state.refresh_token = session.refresh_token
    st.session_state.pop("nf_signed_out", None)
    st.session_state["_login_sid"] = session_id
    _queue_browser_cookie(session_id)
    return True


def _drop_failed_login(refresh: str) -> None:
    """Forget this tab's copy. Keep a login another tab has already replaced."""
    if _clear_session(if_refresh=refresh):
        return
    if st.session_state.get("_login_retry"):
        return
    st.session_state["_login_retry"] = True
    st.rerun()


def _clear_session(*, forget_browser: bool = True, if_refresh: str | None = None) -> bool:
    """Clear this tab. Return False when a newer shared login must be kept."""
    session_id = st.session_state.get("_login_sid")
    removed = True
    if session_id:
        if if_refresh is None:
            delete_login(str(session_id))
        else:
            removed = delete_login_if_current(str(session_id), if_refresh)
        if removed:
            st.session_state.pop("_login_sid", None)
    if not removed:
        st.session_state.pop("access_token", None)
        st.session_state.pop("refresh_token", None)
        return False
    for key in (
        "access_token",
        "refresh_token",
        "profile_user_id",
        "profile_email",
        "chat_messages",
    ):
        st.session_state.pop(key, None)
    if forget_browser:
        st.session_state["nf_signed_out"] = True
        _queue_browser_cookie(None)
    return True


def _saved_tokens() -> tuple[str, str] | None:
    if st.session_state.get("nf_signed_out"):
        return None
    session_id = st.session_state.get("_login_sid")
    if session_id:
        loaded = load_login(str(session_id))
        if loaded is None:
            st.session_state.pop("access_token", None)
            st.session_state.pop("refresh_token", None)
            st.session_state.pop("_login_sid", None)
            return None
        st.session_state.access_token = loaded[0]
        st.session_state.refresh_token = loaded[1]
        return loaded
    access = st.session_state.get("access_token")
    refresh = st.session_state.get("refresh_token")
    if access and refresh:
        return str(access), str(refresh)
    cookie_id = _cookie_header()
    if not valid_session_id(cookie_id):
        return None
    loaded = load_login(cookie_id)
    if loaded is None:
        return None
    st.session_state.access_token = loaded[0]
    st.session_state.refresh_token = loaded[1]
    st.session_state["_login_sid"] = cookie_id
    return loaded


def _restore_user(sb: Client) -> Any | None:
    saved = _saved_tokens()
    if saved is None:
        if _cookie_header() and not st.session_state.get("nf_signed_out"):
            _clear_session()
        else:
            _clear_session(forget_browser=False)
        return None
    access, refresh = saved
    try:
        response = sb.auth.set_session(access, refresh)
    except Exception as exc:
        if session_failure_clears_tokens(exc):
            _drop_failed_login(refresh)
            return None
        st.error(AUTH_UNAVAILABLE)
        st.stop()
    session = session_from_auth_response(response)
    user = getattr(session, "user", None)
    if session is None or user is None:
        _drop_failed_login(refresh)
        return None
    if not _store_session(session, expected_refresh=refresh):
        if st.session_state.get("_login_sid") and not st.session_state.get("_login_retry"):
            st.session_state["_login_retry"] = True
            st.rerun()
        return None
    st.session_state.pop("_login_retry", None)
    previous = st.session_state.get("profile_user_id")
    if previous and previous != str(user.id):
        st.session_state.pop("profile_email", None)
        st.session_state.pop("chat_messages", None)
    st.session_state.profile_user_id = str(user.id)
    return user


def _profile_email(sb: Client, user: Any) -> str:
    fallback = getattr(user, "email", None) or ""
    try:
        result = (
            sb.table("profiles").select("email").eq("id", str(user.id)).limit(1).execute()
        )
    except Exception:
        return fallback
    rows = result.data or []
    if rows and rows[0].get("email"):
        return str(rows[0]["email"])
    return fallback


def _locked_features() -> None:
    left, right = st.columns(2)
    with left:
        st.markdown('<div class="nf-card">', unsafe_allow_html=True)
        st.subheader("Chat")
        st.markdown(
            '<p class="nf-lock">Locked. Sign in to ask about this project.</p>',
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        st.markdown('<div class="nf-card">', unsafe_allow_html=True)
        st.subheader("Warehouse charts")
        st.markdown(
            '<p class="nf-lock">Locked. Sign in to open the chart area.</p>',
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)


def _login_section(sb: Client) -> None:
    st.markdown('<div class="nf-card">', unsafe_allow_html=True)
    mode = st.radio("Account", ["Sign in", "Create account"], horizontal=True, label_visibility="collapsed")
    with st.form("auth-form", clear_on_submit=False):
        email = st.text_input("Email", autocomplete="email")
        password = st.text_input("Password", type="password", autocomplete="current-password")
        if mode == "Create account":
            st.caption(password_rules_text())
        submitted = st.form_submit_button(
            "Create account" if mode == "Create account" else "Sign in",
            use_container_width=True,
            type="primary",
        )
    st.markdown("</div>", unsafe_allow_html=True)
    if not submitted:
        return
    email = email.strip()
    form_error = account_form_error(mode, email, password)
    if form_error:
        st.error(form_error)
        return
    creating = mode == "Create account"
    try:
        if creating:
            response = sb.auth.sign_up({"email": email, "password": password})
        else:
            response = sb.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as exc:
        st.error(public_auth_message(exc, creating=creating))
        return
    session = session_from_auth_response(response)
    if session is None:
        level, text = notice_when_session_missing(creating=creating)
        if level == "info":
            st.info(text)
        else:
            st.error(text)
        return
    _clear_session(forget_browser=False)
    if not _store_session(session):
        st.error(AUTH_UNAVAILABLE)
        return
    st.rerun()


def _public_home(sb: Client) -> None:
    intro, form = st.columns([1.15, 0.85], gap="large")
    with intro:
        st.markdown('<h1 class="nf-title">A warehouse you can sign in to.</h1>', unsafe_allow_html=True)
        st.markdown(
            '<p class="nf-lead">Route catalog data lands in ClickHouse. '
            "This site is the front door. Chat and charts stay locked until you sign in.</p>",
            unsafe_allow_html=True,
        )
        _locked_features()
    with form:
        st.markdown('<p class="nf-kicker">Account</p>', unsafe_allow_html=True)
        _login_section(sb)


def _user_home(sb: Client, user: Any) -> None:
    cached = st.session_state.get("profile_email")
    if st.session_state.get("profile_user_id") != str(user.id):
        cached = None
    email = cached or _profile_email(sb, user)
    st.session_state.profile_user_id = str(user.id)
    st.session_state.profile_email = email
    bar_left, bar_right = st.columns([4, 1])
    with bar_left:
        st.markdown('<h1 class="nf-title">Your home</h1>', unsafe_allow_html=True)
        st.caption(email or "Signed in")
    with bar_right:
        if st.button("Sign out", use_container_width=True):
            try:
                sb.auth.sign_out()
            except Exception:
                pass
            _clear_session()
            st.rerun()

    chart_col, chat_col = st.columns(2, gap="large")
    with chart_col:
        st.subheader("Warehouse charts")
        st.markdown(
            "Unlocked for your account. Product, category, brand, and subcategory "
            "counts are added after the warehouse metrics are in place."
        )
    with chat_col:
        st.subheader("Chat")
        messages: list[dict[str, str]] = st.session_state.setdefault("chat_messages", [])
        for message in messages:
            with st.chat_message(message["role"]):
                st.write(message["content"])
        prompt = st.chat_input("Ask about this project")
        if prompt:
            messages.append({"role": "user", "content": prompt})
            messages.append(
                {
                    "role": "assistant",
                    "content": (
                        "Chat is unlocked for your account. "
                        "Answers are not connected yet."
                    ),
                }
            )
            st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="AI-NexusFlow",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(PAGE_CSS, unsafe_allow_html=True)
    _require_config()
    _page_header()
    sb = _client()
    user = _restore_user(sb)
    if user is None:
        _public_home(sb)
    else:
        _tool_sidebar()
        _user_home(sb, user)
    _page_footer()
    _flush_browser_cookie()


main()
