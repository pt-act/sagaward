"""Pure BFLA logic for the invoice-download B-V2P pair (CVE-2023-49070 inspired).

Broken Function Level Authorization: a regular user can fetch *any* organisation's invoice
because the endpoint checks authentication (valid session) but not authorization (correct org).
The minimal patch (1 line) adds an org-membership check.

``VULN_MODE=1`` (vulnerable): any authenticated user can retrieve any invoice.
``VULN_MODE=0`` (patched): caller must belong to the invoice's organisation.
"""

from __future__ import annotations

import os


class InvoiceAccessError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class Invoice:
    def __init__(self, org_id: str, amount: float) -> None:
        self.org_id = org_id
        self.amount = amount


class User:
    def __init__(self, org_id: str) -> None:
        self.org_id = org_id


_INVOICES: dict[str, Invoice] = {}
_USERS: dict[str, User] = {}


def is_vuln() -> bool:
    return os.getenv("VULN_MODE", "1") == "1"


def reset_state() -> None:
    _INVOICES.clear()
    _USERS.clear()
    _INVOICES["inv-1"] = Invoice("org-A", 1000.0)
    _INVOICES["inv-2"] = Invoice("org-B", 2000.0)
    _USERS["alice"] = User("org-A")
    _USERS["bob"] = User("org-B")
    _USERS["carol"] = User("org-C")


reset_state()


def get_invoice(invoice_id: str, caller: str) -> dict[str, object]:
    """Return invoice. Raises InvoiceAccessError on 404/403."""
    invoice = _INVOICES.get(invoice_id)
    if invoice is None:
        raise InvoiceAccessError(404, "not_found")
    user = _USERS.get(caller)
    if user is None:
        raise InvoiceAccessError(401, "unauthenticated")
    if not is_vuln() and user.org_id != invoice.org_id:
        # Patched: one-line org membership check — the minimal diff.
        raise InvoiceAccessError(403, "forbidden")
    return {"invoice_id": invoice_id, "org_id": invoice.org_id, "amount": invoice.amount}
