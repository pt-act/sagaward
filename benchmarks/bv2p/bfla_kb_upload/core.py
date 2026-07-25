"""BFLA knowledge-base upload write-access bypass — CVE-2026-59217 (open-webui).

Real vulnerability: POST /api/v1/files/ accepted a client-supplied metadata.knowledge_id
and auto-linked the uploaded file to that knowledge base WITHOUT checking write permission.
Any user who could upload a file could attach it to any knowledge base they had no write access to.

Minimal diff: access check (`can_write`) inserted before the auto-link call.
``VULN_MODE=1``: auto-link runs without checking write access.
``VULN_MODE=0``: access check runs — only owner/admin/write-grant may link.
"""
from __future__ import annotations
import os

def is_vuln() -> bool:
    return os.getenv("VULN_MODE", "1") == "1"


# Simulated knowledge bases: id -> {owner, write_grants}
_KNOWLEDGE_BASES: dict[str, dict] = {
    "kb-alice": {"owner": "alice", "write_grants": {"alice"}},
    "kb-shared": {"owner": "admin", "write_grants": {"alice", "bob", "admin"}},
    "kb-restricted": {"owner": "admin", "write_grants": {"admin"}},  # bob should NOT link here
}

_USER_ROLES: dict[str, str] = {
    "alice": "user",
    "bob": "user",
    "admin": "admin",
}

_FILES: dict[str, dict] = {}
_LINKED_FILES: list[dict] = []


class AccessError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def reset_state() -> None:
    _FILES.clear()
    _LINKED_FILES.clear()


reset_state()


def upload_file(user_id: str, file_id: str, filename: str, knowledge_id: str | None = None) -> dict:
    """
    Upload a file and optionally auto-link it to a knowledge base.

    VULN_MODE=1: auto-links without write-access check (CVE-2026-59217).
    VULN_MODE=0: checks write access before linking.
    """
    role = _USER_ROLES.get(user_id, "user")
    file_item = {"file_id": file_id, "filename": filename, "owner": user_id}
    _FILES[file_id] = file_item

    if knowledge_id:
        kb = _KNOWLEDGE_BASES.get(knowledge_id)
        if kb is None:
            raise AccessError(404, f"Knowledge base {knowledge_id!r} not found")

        if is_vuln():
            # Bug: no access check — any user can link to any KB
            _LINKED_FILES.append({"file_id": file_id, "knowledge_id": knowledge_id, "linked_by": user_id})
        else:
            # Patch: check write access before linking
            can_write = (
                kb["owner"] == user_id
                or role == "admin"
                or user_id in kb.get("write_grants", set())
            )
            if not can_write:
                raise AccessError(
                    403,
                    f"User {user_id!r} does not have write access to knowledge base {knowledge_id!r}"
                )
            _LINKED_FILES.append({"file_id": file_id, "knowledge_id": knowledge_id, "linked_by": user_id})

    return {
        "file_id": file_id,
        "filename": filename,
        "linked_to": knowledge_id,
        "status": "uploaded",
    }


def list_linked_files(knowledge_id: str) -> list[dict]:
    return [f for f in _LINKED_FILES if f["knowledge_id"] == knowledge_id]
