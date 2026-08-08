"""BFLA arena model bypass logic — CVE-2026-59225 (open-webui).

Real vulnerability: arena fallback path in generate_chat_completion called
bypass_filter=True, which skipped the per-model access check at line ~200.
A user with no access to a restricted model could trigger it via the arena endpoint.

Minimal diff: 6-line authorization check inserted before the bypass_filter dispatch.
``VULN_MODE=1``: check is absent — any user can use any model via arena.
``VULN_MODE=0``: check present — user must have explicit access to the selected model.
"""
from __future__ import annotations
import os


def is_vuln() -> bool:
    return os.getenv("VULN_MODE", "1") == "1"


# Simulated model access control list
# model_id -> set of user_ids allowed
_MODEL_ACL: dict[str, set[str]] = {
    "gpt-4o": {"alice", "admin"},        # restricted model: alice + admin only
    "gpt-4o-mini": {"alice", "bob", "admin"},  # open model: all users
}

# Simulated user roles
_USER_ROLES: dict[str, str] = {
    "alice": "user",
    "bob": "user",
    "admin": "admin",
}


class AccessError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def check_model_access(user_id: str, model_id: str) -> None:
    """Raises AccessError(403) if user lacks access to the requested model."""
    role = _USER_ROLES.get(user_id, "user")
    if role == "admin":
        return  # admin always allowed
    allowed = _MODEL_ACL.get(model_id, set())
    if user_id not in allowed:
        raise AccessError(403, f"User {user_id!r} does not have access to model {model_id!r}")


def generate_via_arena(user_id: str, model_id: str, prompt: str, bypass_filter: bool = False) -> dict:
    """
    Simulate the arena code path. bypass_filter=True is set internally when arena picks
    a fallback model — the bug was that this path skipped check_model_access.

    VULN_MODE=1: bypass_filter skips access check (original bug).
    VULN_MODE=0: access check runs regardless of bypass_filter (patched behavior).
    """
    role = _USER_ROLES.get(user_id, "user")

    # Patched path: always check access for non-admin users, even when bypass_filter=True
    if not is_vuln() and not bypass_filter and role == "user":
        check_model_access(user_id, model_id)

    if not is_vuln() and role == "user":
        # Patched: gate the resolved model BEFORE bypass_filter dispatch
        check_model_access(user_id, model_id)

    # Simulate model response
    return {
        "model": model_id,
        "user": user_id,
        "response": f"[Arena response to: {prompt[:40]}]",
        "bypass_filter_used": bypass_filter,
    }
