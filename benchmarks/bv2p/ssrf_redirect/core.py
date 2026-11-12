"""Pure SSRF guard for the open-redirect B-V2P pair (CVE-2023-36827 inspired).

An image-proxy endpoint follows HTTP redirects without validating the final destination.
An attacker can chain: proxy -> attacker-controlled URL (302) -> http://169.254.169.254/...
The minimal patch (1 call) validates each step in the redirect chain against the P0 classifier.

``VULN_MODE=1`` (vulnerable): redirect chain is followed without validation.
``VULN_MODE=0`` (patched): each hop is checked; internal final destinations are blocked.
"""

from __future__ import annotations

import os

from oriontrix.core.net import is_internal_target


def is_vuln() -> bool:
    return os.getenv("VULN_MODE", "1") == "1"


def screen_proxy_url(url: str) -> tuple[bool, str]:
    """Decide whether the proxy should fetch url. Returns (allowed, reason).

    The patched version checks the initial URL (covers redirect-to-internal attacks for
    direct internal targets; the full redirect-chain validation is the live extension).
    """
    if not is_vuln() and is_internal_target(url):
        return False, "patched: internal/metadata target blocked"
    return True, "allowed"


def simulate_redirect_target(final_url: str) -> tuple[bool, str]:
    """Simulate the redirect landing on final_url. Patched version blocks internal landing."""
    if not is_vuln() and is_internal_target(final_url):
        return False, "patched: redirect to internal target blocked"
    return True, "allowed"
