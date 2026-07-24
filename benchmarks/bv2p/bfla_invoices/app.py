"""B-V2P BFLA pair — invoice download (CVE-2023-49070 inspired). Thin FastAPI wrapper."""

from __future__ import annotations

from core import InvoiceAccessError, get_invoice, reset_state
from fastapi import FastAPI, Header, HTTPException

app = FastAPI()


@app.post("/reset")
def reset() -> dict[str, str]:
    reset_state()
    return {"status": "reset"}


@app.get("/api/v1/invoices/{invoice_id}")
def invoice_route(
    invoice_id: str, x_user_id: str = Header(default="anonymous")
) -> dict[str, object]:
    try:
        return get_invoice(invoice_id, x_user_id)
    except InvoiceAccessError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
