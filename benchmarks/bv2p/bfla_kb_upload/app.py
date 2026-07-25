"""FastAPI wrapper for CVE-2026-59217 BFLA KB upload fixture."""
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from core import upload_file, list_linked_files, AccessError, reset_state, _USER_ROLES

app = FastAPI()


class UploadRequest(BaseModel):
    file_id: str
    filename: str
    knowledge_id: str | None = None


@app.post("/api/v1/files/")
async def upload(
    req: UploadRequest,
    x_user_id: str = Header(..., alias="x-user-id"),
):
    """File upload endpoint — attacker supplies knowledge_id to auto-link to restricted KB."""
    if x_user_id not in _USER_ROLES:
        raise HTTPException(status_code=401, detail="unknown user")
    try:
        result = upload_file(
            user_id=x_user_id,
            file_id=req.file_id,
            filename=req.filename,
            knowledge_id=req.knowledge_id,
        )
        return result
    except AccessError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@app.get("/api/v1/knowledge/{knowledge_id}/files")
async def get_linked_files(
    knowledge_id: str,
    x_user_id: str = Header(..., alias="x-user-id"),
):
    return {"knowledge_id": knowledge_id, "files": list_linked_files(knowledge_id)}


@app.post("/reset")
async def reset():
    reset_state()
    return {"ok": True}
