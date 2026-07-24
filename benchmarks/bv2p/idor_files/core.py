"""Pure IDOR logic for the file-download B-V2P pair (CVE-2024-0204 inspired).

A user can download any file by guessing its UUID because no ownership check is performed.
The minimal patch (1 line) verifies the requesting user owns the file.

``VULN_MODE=1`` (vulnerable): any authenticated user can download any file.
``VULN_MODE=0`` (patched): caller must be the file owner.
"""

from __future__ import annotations

import os


class FileAccessError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class StoredFile:
    def __init__(self, owner: str, filename: str, content: str) -> None:
        self.owner = owner
        self.filename = filename
        self.content = content


_FILES: dict[str, StoredFile] = {}


def is_vuln() -> bool:
    return os.getenv("VULN_MODE", "1") == "1"


def reset_state() -> None:
    _FILES.clear()
    _FILES["file-a1b2"] = StoredFile("alice", "secret.pdf", "alice confidential report")
    _FILES["file-c3d4"] = StoredFile("bob", "contract.pdf", "bob contract data")


reset_state()


def download_file(file_id: str, caller: str) -> dict[str, object]:
    """Return file metadata+content. Raises FileAccessError on 404/403."""
    f = _FILES.get(file_id)
    if f is None:
        raise FileAccessError(404, "not_found")
    if not is_vuln() and f.owner != caller:
        # Patched: one-line ownership check — the minimal diff.
        raise FileAccessError(403, "forbidden")
    return {"file_id": file_id, "owner": f.owner, "filename": f.filename, "content": f.content}
