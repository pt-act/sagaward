"""B-V2P SQLi pair — product search (CVE-2023-46604 inspired class). Thin FastAPI wrapper."""

from __future__ import annotations

from core import search_products
from fastapi import FastAPI

app = FastAPI()


@app.get("/api/v1/products/search")
def search_route(q: str = "") -> dict[str, object]:
    results = search_products(q)
    return {"query": q, "results": results, "count": len(results)}
