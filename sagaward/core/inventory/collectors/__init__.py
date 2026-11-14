"""Inventory source collectors."""

from __future__ import annotations

from sagaward.core.inventory.collectors.code import collect_code
from sagaward.core.inventory.collectors.external import (
    collect_arjun,
    collect_ffuf,
    collect_httpx,
    collect_katana,
)
from sagaward.core.inventory.collectors.js import collect_js
from sagaward.core.inventory.collectors.sitemap import collect_sitemap


__all__ = [
    "collect_arjun",
    "collect_code",
    "collect_ffuf",
    "collect_httpx",
    "collect_js",
    "collect_katana",
    "collect_sitemap",
]
