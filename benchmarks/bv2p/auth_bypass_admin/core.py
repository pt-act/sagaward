"""Pure auth-bypass logic for the admin-panel B-V2P pair (CVE-2024-41667 inspired).

A Grafana-style admin endpoint checks that the user is authenticated but forgets to check
the ``is_admin`` flag. The minimal patch (1 line) adds the admin role check.

``VULN_MODE=1`` (vulnerable): any authenticated user can access the admin endpoint.
``VULN_MODE=0`` (patched): caller must have the admin role.
"""

from __future__ import annotations

import os


class AdminAccessError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class User:
    def __init__(self, is_admin: bool) -> None:
        self.is_admin = is_admin


_USERS: dict[str, User] = {}
_ADMIN_CONFIG: dict[str, object] = {}


def is_vuln() -> bool:
    return os.getenv("VULN_MODE", "1") == "1"


def reset_state() -> None:
    _USERS.clear()
    _ADMIN_CONFIG.clear()
    _USERS["admin"] = User(is_admin=True)
    _USERS["alice"] = User(is_admin=False)
    _ADMIN_CONFIG["secret_key"] = "s3cr3t-admin-key"
    _ADMIN_CONFIG["debug_mode"] = True


reset_state()


def get_admin_config(caller: str) -> dict[str, object]:
    """Return admin configuration. Raises AdminAccessError on 401/403."""
    user = _USERS.get(caller)
    if user is None:
        raise AdminAccessError(401, "unauthenticated")
    if not is_vuln() and not user.is_admin:
        # Patched: one-line role check — the minimal diff.
        raise AdminAccessError(403, "forbidden")
    return dict(_ADMIN_CONFIG)
