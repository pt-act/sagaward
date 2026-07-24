"""B-V2P mass assignment pair — user profile (CVE-2024-5489 inspired). Thin FastAPI wrapper."""

from __future__ import annotations

from typing import Any

from core import ProfileAccessError, reset_state, update_profile
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()


class ProfileUpdateBody(BaseModel):
    fields: dict[str, Any]


@app.post("/reset")
def reset() -> dict[str, str]:
    reset_state()
    return {"status": "reset"}


@app.patch("/api/v1/users/{username}/profile")
def update_profile_route(username: str, body: ProfileUpdateBody) -> dict[str, object]:
    try:
        return update_profile(username, body.fields)
    except ProfileAccessError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
