"""B-V2P IDOR pair — file download (CVE-2024-0204 inspired). Thin FastAPI wrapper."""

from __future__ import annotations

from core import FileAccessError, download_file, reset_state
from fastapi import FastAPI, Header, HTTPException

app = FastAPI()


@app.post("/reset")
def reset() -> dict[str, str]:
    reset_state()
    return {"status": "reset"}


@app.get("/api/v1/files/{file_id}/download")
def download_route(
    file_id: str, x_user_id: str = Header(default="anonymous")
) -> dict[str, object]:
    try:
        return download_file(file_id, x_user_id)
    except FileAccessError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
