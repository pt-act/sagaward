"""B-V2P SSRF pair — webhook registration (CVE-2024-21672 inspired). Thin FastAPI wrapper."""

from __future__ import annotations

from core import get_webhook, register_webhook, reset_state
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()


class WebhookBody(BaseModel):
    url: str


@app.post("/reset")
def reset() -> dict[str, str]:
    reset_state()
    return {"status": "reset"}


@app.post("/api/v1/webhooks")
def register_route(body: WebhookBody) -> dict[str, object]:
    import uuid
    webhook_id = str(uuid.uuid4())
    accepted, reason = register_webhook(webhook_id, body.url)
    if not accepted:
        raise HTTPException(status_code=400, detail=reason)
    return {"webhook_id": webhook_id, "url": body.url, "status": "registered"}


@app.get("/api/v1/webhooks/{webhook_id}")
def get_route(webhook_id: str) -> dict[str, object]:
    url = get_webhook(webhook_id)
    if url is None:
        raise HTTPException(status_code=404, detail="not_found")
    return {"webhook_id": webhook_id, "url": url}
