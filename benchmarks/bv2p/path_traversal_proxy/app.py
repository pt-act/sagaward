"""FastAPI wrapper for CVE-2026-59221 path traversal proxy fixture."""
from fastapi import FastAPI, Request
from fastapi.responses import Response
from core import read_static_file

app = FastAPI()


@app.get("/proxy/static/{path:path}")
async def proxy_static(path: str):
    """
    Proxy endpoint. Attacker sends over-encoded path to bypass traversal guard.
    e.g. GET /proxy/static/%252e%252e%252fetc%252fpasswd
    (double-encoded: %25 = '%', so %252e = %2e = '.')
    """
    status, content = read_static_file("/" + path)
    if isinstance(content, bytes):
        return Response(content=content, status_code=status, media_type="text/plain")
    return Response(content=content, status_code=status, media_type="text/plain")


@app.post("/reset")
async def reset():
    return {"ok": True}
