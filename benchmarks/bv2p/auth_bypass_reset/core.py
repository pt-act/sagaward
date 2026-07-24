"""Pure auth-bypass logic for the password-reset B-V2P pair (CVE-2023-45158 inspired).

An account takeover: the password-reset endpoint accepts a token but does not verify it
belongs to the supplied username. Any valid token (from any account) can reset any password.
The minimal patch (1 line) checks the token is bound to the requesting username.

``VULN_MODE=1`` (vulnerable): any valid token can reset any account's password.
``VULN_MODE=0`` (patched): token must be bound to the supplied username.
"""

from __future__ import annotations

import os


class ResetAccessError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


_RESET_TOKENS: dict[str, str] = {}   # token -> bound_username
_PASSWORDS: dict[str, str] = {}      # username -> password_hash


def is_vuln() -> bool:
    return os.getenv("VULN_MODE", "1") == "1"


def reset_state() -> None:
    _RESET_TOKENS.clear()
    _PASSWORDS.clear()
    _RESET_TOKENS["tok-abc"] = "alice"  # valid token bound to alice
    _RESET_TOKENS["tok-xyz"] = "bob"    # valid token bound to bob
    _PASSWORDS["alice"] = "hash-alice-original"
    _PASSWORDS["bob"] = "hash-bob-original"


reset_state()


def reset_password(username: str, token: str, new_password: str) -> dict[str, object]:
    """Reset password using a reset token. Raises ResetAccessError on invalid/cross-account token."""
    if token not in _RESET_TOKENS:
        raise ResetAccessError(400, "invalid_token")
    if not is_vuln() and _RESET_TOKENS[token] != username:
        # Patched: one-line token-binding check — the minimal diff.
        raise ResetAccessError(403, "token_not_bound_to_user")
    _PASSWORDS[username] = new_password
    return {"username": username, "status": "password_reset"}
