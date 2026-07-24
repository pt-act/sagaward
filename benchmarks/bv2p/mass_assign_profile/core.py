"""Pure mass-assignment logic for the user-profile update B-V2P pair (CVE-2024-5489 inspired).

A user profile update endpoint blindly updates all fields supplied by the caller, including
``is_admin``. The minimal patch (1-3 lines) strips privileged fields via an allowlist before
applying the update.

``VULN_MODE=1`` (vulnerable): all supplied fields are written, including ``is_admin``.
``VULN_MODE=0`` (patched): only allowlisted fields (name, bio, avatar_url) can be updated.
"""

from __future__ import annotations

import os


class ProfileAccessError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


_ALLOWED_FIELDS: frozenset[str] = frozenset({"name", "bio", "avatar_url"})


class UserProfile:
    def __init__(self, name: str, bio: str, is_admin: bool = False) -> None:
        self.name = name
        self.bio = bio
        self.avatar_url = ""
        self.is_admin = is_admin


_PROFILES: dict[str, UserProfile] = {}


def is_vuln() -> bool:
    return os.getenv("VULN_MODE", "1") == "1"


def reset_state() -> None:
    _PROFILES.clear()
    _PROFILES["alice"] = UserProfile("Alice", "regular user")
    _PROFILES["bob"] = UserProfile("Bob", "another user")


reset_state()


def update_profile(username: str, fields: dict[str, object]) -> dict[str, object]:
    """Update user profile. Raises ProfileAccessError on 404."""
    profile = _PROFILES.get(username)
    if profile is None:
        raise ProfileAccessError(404, "not_found")

    if is_vuln():
        # Vulnerable: apply all supplied fields (mass assignment).
        for k, v in fields.items():
            setattr(profile, k, v)
    else:
        # Patched: strip privileged fields — the minimal diff (1-line allowlist filter).
        safe = {k: v for k, v in fields.items() if k in _ALLOWED_FIELDS}
        for k, v in safe.items():
            setattr(profile, k, v)

    return {
        "username": username,
        "name": profile.name,
        "bio": profile.bio,
        "avatar_url": profile.avatar_url,
        "is_admin": profile.is_admin,
    }
