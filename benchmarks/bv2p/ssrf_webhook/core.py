"""Pure SSRF guard for the webhook-delivery B-V2P pair (CVE-2024-21672 inspired).

An application allows users to register webhooks pointing to arbitrary URLs. The vulnerable
version performs no URL validation, allowing SSRF to internal services. The minimal patch
(1 call) adds the P0 net classifier check before accepting the URL.

``VULN_MODE=1`` (vulnerable): any URL is accepted for webhook registration.
``VULN_MODE=0`` (patched): internal/metadata URLs are rejected.
"""

from __future__ import annotations

import os

from strix.core.net import is_internal_target


def is_vuln() -> bool:
    return os.getenv("VULN_MODE", "1") == "1"


_WEBHOOKS: dict[str, str] = {}


def reset_state() -> None:
    _WEBHOOKS.clear()


reset_state()


def register_webhook(webhook_id: str, url: str) -> tuple[bool, str]:
    """Register a webhook URL. Returns (accepted, reason).

    The patched version rejects internal/metadata targets.
    """
    if not is_vuln() and is_internal_target(url):
        return False, "patched: internal/metadata target blocked"
    _WEBHOOKS[webhook_id] = url
    return True, "registered"


def get_webhook(webhook_id: str) -> str | None:
    return _WEBHOOKS.get(webhook_id)
