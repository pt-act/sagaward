"""B-V2P SSRF pair — open redirect proxy (CVE-2023-36827 inspired). Thin FastAPI wrapper."""

from __future__ import annotations

from core import screen_proxy_url, simulate_redirect_target
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()


class ProxyBody(BaseModel):
    url: str
    redirect_to: str | None = None  # simulate a redirect to this target


@app.post("/api/v1/proxy/fetch")
def proxy_route(body: ProxyBody) -> dict[str, object]:
    allowed, reason = screen_proxy_url(body.url)
    if not allowed:
        raise HTTPException(status_code=400, detail=reason)
    if body.redirect_to:
        allowed2, reason2 = simulate_redirect_target(body.redirect_to)
        if not allowed2:
            raise HTTPException(status_code=400, detail=reason2)
        return {"fetched": body.redirect_to, "via_redirect": True, "reason": reason2}
    return {"fetched": body.url, "via_redirect": False, "reason": reason}
