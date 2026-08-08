"""B-V2P auth bypass pair — admin panel (CVE-2024-41667 inspired). Thin FastAPI wrapper."""

from __future__ import annotations

from core import AdminAccessError, get_admin_config, reset_state
from fastapi import FastAPI, Header, HTTPException

app = FastAPI()


@app.post("/reset")
def reset() -> dict[str, str]:
    reset_state()
    return {"status": "reset"}


@app.get("/api/admin/config")
def admin_config_route(
    x_user_id: str = Header(default="anonymous"),
) -> dict[str, object]:
    try:
        return get_admin_config(x_user_id)
    except AdminAccessError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
