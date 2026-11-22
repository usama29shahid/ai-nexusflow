"""Password rules shared with the GoTrue settings on the Auth container.

GoTrue checks each colon-separated class in GOTRUE_PASSWORD_REQUIRED_CHARACTERS.
Keep REQUIRED_CHARACTERS aligned with docker/supabase/docker-compose.yml.
"""

from __future__ import annotations

MIN_LENGTH = 8
REQUIRED_CHARACTERS = (
    "abcdefghijklmnopqrstuvwxyz:ABCDEFGHIJKLMNOPQRSTUVWXYZ:0123456789:!@#%^&*()_+-="
)

_RULES = (
    (MIN_LENGTH, "Use at least 8 characters."),
    ("abcdefghijklmnopqrstuvwxyz", "Include a lowercase letter."),
    ("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "Include an uppercase letter."),
    ("0123456789", "Include a digit."),
    ("!@#%^&*()_+-=", "Include a symbol such as ! or #."),
)


def password_problems(password: str) -> list[str]:
    """Return the rules this password still fails. Empty means it can be submitted."""
    problems: list[str] = []
    if len(password) < MIN_LENGTH:
        problems.append(_RULES[0][1])
    for charset, message in _RULES[1:]:
        if not any(character in charset for character in password):
            problems.append(message)
    return problems


def password_rules_text() -> str:
    return "At least 8 characters, with a lowercase letter, an uppercase letter, a digit, and a symbol."
