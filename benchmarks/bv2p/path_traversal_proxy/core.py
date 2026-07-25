"""Path traversal proxy decode-cap bypass — CVE-2026-59221 (open-webui).

Real vulnerability: _safe_static_redirect_path() and _sanitize_proxy_path() decoded
URL-encoded sequences in a loop up to a cap (MAX_DECODE=20), but did NOT check whether
the final path was still encoded after the loop. A value requiring >20 decode rounds
(or crafted with mixed encoding) could bypass the traversal guard.

Minimal diff: after the decode loop, if unquote(path) != path → fail closed (return None).
``VULN_MODE=1``: no fail-close check — over-encoded traversal sequences pass through.
``VULN_MODE=0``: fail-close check present — still-encoded paths are rejected.
"""
from __future__ import annotations
import os
import posixpath
from urllib.parse import unquote

MAX_DECODE = 5  # cap for test purposes (real code uses 20)


def is_vuln() -> bool:
    return os.getenv("VULN_MODE", "1") == "1"


# Simulated static files available under /static/
_STATIC_FILES: dict[str, bytes] = {
    "/static/index.html": b"<html>index</html>",
    "/static/style.css": b"body { color: black; }",
    "/static/public/readme.txt": b"public readme",
    "/etc/passwd": b"root:x:0:0:root:/root:/bin/bash\nalice:x:1000:1000::/home/alice:/bin/bash",
    "/app/secrets.env": b"SECRET_KEY=supersecret\nDB_PASSWORD=hunter2",
}


def sanitize_proxy_path(path: str) -> str | None:
    """
    Decode URL encoding up to MAX_DECODE rounds to normalise the path.
    Returns None if the path is unsafe.

    VULN_MODE=1: no fail-close → over-encoded traversal bypasses guard.
    VULN_MODE=0: fail-close → still-encoded paths rejected.
    """
    decoded = path
    for _ in range(MAX_DECODE):
        once = unquote(decoded)
        if once == decoded:
            break
        decoded = once

    # PATCH: fail closed — if still encoded after the cap, reject
    if not is_vuln() and unquote(decoded) != decoded:
        return None

    # Standard traversal guards
    if "\x00" in decoded or "\\" in decoded:
        return None
    if not decoded.startswith("/"):
        decoded = "/" + decoded
    normalized = posixpath.normpath(decoded)
    if not normalized.startswith("/"):
        return None
    return normalized


def read_static_file(raw_path: str) -> tuple[int, bytes | str]:
    """
    Returns (status_code, content).
    VULN_MODE=1: over-encoded traversal paths bypass the sanitizer; the /static/ prefix
                 check is skipped when the decoded path escapes /static/ prefix via normpath.
    VULN_MODE=0: sanitizer rejects still-encoded paths → 400.
    """
    safe_path = sanitize_proxy_path(raw_path)
    if safe_path is None:
        # Patched path: fail-closed — over-encoded path rejected here
        return 400, "invalid path"

    # Check if path is within /static/
    if safe_path.startswith("/static/"):
        content = _STATIC_FILES.get(safe_path)
        if content is None:
            return 404, "not found"
        return 200, content

    # Path escaped /static/ via traversal
    if is_vuln():
        # Vuln: traversal succeeded — serve whatever the path resolves to
        content = _STATIC_FILES.get(safe_path)
        if content:
            return 200, content
        # Even if we don't have the file, the traversal bypass is confirmed by returning 200
        return 200, b"[traversal reached outside /static/]"
    else:
        return 403, "access denied"
