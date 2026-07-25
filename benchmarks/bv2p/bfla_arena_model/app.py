"""FastAPI wrapper for CVE-2026-59225 BFLA arena model bypass fixture."""
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from core import generate_via_arena, AccessError, _USER_ROLES

app = FastAPI()


class ArenaRequest(BaseModel):
    model: str
    prompt: str
    bypass_filter: bool = False


@app.post("/api/v1/arena/complete")
async def arena_complete(
    req: ArenaRequest,
    x_user_id: str = Header(..., alias="x-user-id"),
):
    """Arena completion endpoint — attacker uses bypass_filter=True to skip access check."""
    if x_user_id not in _USER_ROLES:
        raise HTTPException(status_code=401, detail="unknown user")
    try:
        result = generate_via_arena(
            user_id=x_user_id,
            model_id=req.model,
            prompt=req.prompt,
            bypass_filter=req.bypass_filter,
        )
        return result
    except AccessError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@app.post("/reset")
async def reset():
    return {"ok": True}
