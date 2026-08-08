"""B-V2P auth bypass pair — password reset takeover (CVE-2023-45158 inspired). FastAPI wrapper."""

from __future__ import annotations

from core import ResetAccessError, reset_password, reset_state
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()


class ResetBody(BaseModel):
    username: str
    token: str
    new_password: str


@app.post("/reset")
def reset() -> dict[str, str]:
    reset_state()
    return {"status": "reset"}


@app.post("/api/v1/auth/reset-password")
def reset_password_route(body: ResetBody) -> dict[str, object]:
    try:
        return reset_password(body.username, body.token, body.new_password)
    except ResetAccessError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
