"""Pure SQLi logic for the product-search B-V2P pair (CVE-2023-46604 inspired class).

A search endpoint builds a query via string interpolation, allowing SQL injection. The
vulnerable version returns data from injected queries (different rows/schema). The patch
(1-3 lines) uses parameterised queries — no data returned for injected payloads.

This fixture uses a pure in-memory dict to simulate SQL rows without a real DB, so it's
hermetically testable without any infrastructure.

``VULN_MODE=1`` (vulnerable): query is executed via string interpolation; injected payloads
    can return rows from other "tables" (simulated as privileged_data dict).
``VULN_MODE=0`` (patched): query is parameterised — injected metacharacters don't alter result.
"""

from __future__ import annotations

import os
import re


_PRODUCTS: dict[str, dict[str, object]] = {
    "widget": {"name": "widget", "price": 9.99},
    "gadget": {"name": "gadget", "price": 19.99},
}

# Rows that should NEVER be returned via the search API.
_PRIVILEGED_DATA: dict[str, dict[str, object]] = {
    "admin-token": {"token": "super-secret-admin-token", "user": "admin"},
}


def is_vuln() -> bool:
    return os.getenv("VULN_MODE", "1") == "1"


def reset_state() -> None:
    pass  # stateless in this fixture


def _is_injected(query: str) -> bool:
    """Detect SQL metacharacters that indicate injection."""
    return bool(re.search(r"['\";#\-\-]|union|select|from", query, re.IGNORECASE))


def search_products(query: str) -> list[dict[str, object]]:
    """Search products by name substring.

    Vulnerable: injection via UNION-style metacharacters returns privileged rows.
    Patched: query is sanitised (parameterised equivalent) — metacharacters yield empty results.
    """
    if is_vuln() and _is_injected(query):
        # Simulates UNION injection returning privileged_data rows.
        return list(_PRIVILEGED_DATA.values())

    # Safe path (both vuln normal queries and all patched queries).
    return [row for name, row in _PRODUCTS.items() if query.lower() in name.lower()]
