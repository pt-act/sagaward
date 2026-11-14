"""B-V2P benchmark corpus registry (M2) — research apparatus, quarantined (see sagaward.research).

A Behavioral-V2P pair is the same application at a vulnerable commit and its minimal-diff
security fix, deployed live, with a ground-truth label set ``V`` (the labeled-vulnerable
endpoints). This module is the typed, importable index the experiments consume; the deployable
targets themselves live under ``benchmarks/bv2p/<fixture_dir>``.

Recall is reported as **recall-over-known**: ``V`` is the labeled set only, and every recall
number carries the unknown-unknown caveat (there may be vulnerabilities not in ``V``). The
corpus is deliberately **small-gap-biased** — the E2 primary test is a gap-stratified paired
McNemar, which needs small-gap *discordant* pairs, not breadth.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal


if TYPE_CHECKING:
    from collections.abc import Sequence


Primitive = Literal["idor", "bfla", "ssrf", "xxe", "race", "business_logic"]
GapClass = Literal["small", "large"]
# Which deterministic disposer confirms the pair (mirrors report.state EvidenceClass, minus "none").
DisposerEvidence = Literal["diff", "callback", "reachability", "race_result"]


@dataclass(frozen=True)
class BV2PPair:
    """One vuln/patch pair. ``vuln_endpoint`` is the ground-truth label (an element of ``V``).

    Two ORTHOGONAL provenance axes — never collapse them:

    * ``is_real_cve`` — vulnerability provenance. ``True`` iff this pair reproduces the behavior
      of the genuine, independently-published CVE in ``cve`` *in that same software/class*
      (PM-verified against NVD, see ``corpus-cve-verification.md``). ``False`` pairs are synthetic
      fixtures MODELED ON a real-world pattern; their ``cve`` field carries a ``pattern:CVE-X``
      prefix and does NOT claim to reproduce that CVE. 5 real / 8 synthetic-pattern.
    * ``synthesized_patch`` — fix provenance. ``True`` iff the patched side uses a synthesized
      minimal-diff rather than the actual upstream patch. 9 synthesized / 4 real patches.

    These axes cross: a real CVE can ship a synthesized patch (e.g. openwebui-idor-memories has
    no clean single-commit upstream fix). ``is_real_cve`` is about the VULN; ``synthesized_patch``
    is about the FIX.
    """

    pair_id: str
    primitive: Primitive
    cve: str
    is_real_cve: bool
    title: str
    vuln_endpoint: str
    disposer_evidence: DisposerEvidence
    gap_class: GapClass
    minimal_diff: bool
    synthesized_patch: bool
    fixture_dir: str
    notes: str


# M0 seeds (Spec F-9): the discriminator (IDOR, synthesized minimal patch) and the H1/OOB
# showcase (SSRF). Both are genuine public CVEs (is_real_cve=True). Race/business-logic pairs are
# soft-edged behind Phases 4/5 and are added as the corpus grows.
# M2 expansion: 8 additional small-gap pairs added to reach n>=10 for E2 statistical power. These 8
# are SYNTHETIC fixtures modeled on real patterns (is_real_cve=False); their cve field is
# prefixed `pattern:` and they do NOT reproduce the referenced CVE. Honest composition:
# 5 real CVEs / 8 synthetic-pattern; orthogonally 4 real patches / 9 synthesized patches.
# See corpus-cve-verification.md (PM NVD verification).
BV2P_CORPUS: tuple[BV2PPair, ...] = (
    BV2PPair(
        pair_id="openwebui-idor-memories",
        primitive="idor",
        cve="CVE-2024-7041",
        is_real_cve=True,
        title="open-webui memories IDOR (missing ownership check)",
        vuln_endpoint="POST /api/v1/memories/{id}/update",
        disposer_evidence="diff",
        gap_class="small",
        minimal_diff=True,
        synthesized_patch=True,
        fixture_dir="idor_memories",
        notes=(
            "No clean public single-commit fix exists; the patch synthesizes the one-line "
            "ownership check (memory.user_id == caller). M0 discriminator."
        ),
    ),
    BV2PPair(
        pair_id="flowise-ssrf-http-node",
        primitive="ssrf",
        cve="CVE-2026-31829",
        is_real_cve=True,
        title="Flowise HTTP-node SSRF (unvalidated URL fetch)",
        vuln_endpoint="POST /api/v1/node/http",
        disposer_evidence="callback",
        gap_class="small",
        minimal_diff=True,
        synthesized_patch=False,
        fixture_dir="ssrf_fetch",
        notes=(
            "Real fix (<=3.0.12 -> 3.0.13). Patched mode blocks internal/metadata targets via the "
            "P0 net classifier (sagaward.core.net.is_internal_target). H1/OOB-callback showcase."
        ),
    ),
    # --- M2 expansion pairs (E2 corpus build-out) ---
    BV2PPair(
        pair_id="bfla-invoices",
        primitive="bfla",
        cve="pattern:CVE-2023-49070",
        is_real_cve=False,
        title="Invoice BFLA (missing org membership check)",
        vuln_endpoint="GET /api/v1/invoices/{invoice_id}",
        disposer_evidence="diff",
        gap_class="small",
        minimal_diff=True,
        synthesized_patch=True,
        fixture_dir="bfla_invoices",
        notes=(
            "Synthetic fixture modeled on a BFLA pattern. Does NOT reproduce CVE-2023-49070 "
            "(Apache OFBiz pre-auth RCE — unrelated product and class). Authenticated user can "
            "fetch any org's invoice; patch adds one-line org membership check (user.org_id == invoice.org_id)."
        ),
    ),
    BV2PPair(
        pair_id="idor-files-download",
        primitive="idor",
        cve="pattern:CVE-2024-0204",
        is_real_cve=False,
        title="File Download IDOR (missing file ownership check)",
        vuln_endpoint="GET /api/v1/files/{file_id}/download",
        disposer_evidence="diff",
        gap_class="small",
        minimal_diff=True,
        synthesized_patch=True,
        fixture_dir="idor_files",
        notes=(
            "Synthetic fixture modeled on an IDOR pattern. Does NOT reproduce CVE-2024-0204 "
            "(Fortra GoAnywhere MFT auth bypass — unrelated product and class). Any authenticated user "
            "can download any file by UUID; patch adds one-line ownership check (file.owner == caller)."
        ),
    ),
    BV2PPair(
        pair_id="ssrf-webhook-registration",
        primitive="ssrf",
        cve="pattern:CVE-2024-21672",
        is_real_cve=False,
        title="Webhook SSRF (unvalidated URL registration)",
        vuln_endpoint="POST /api/v1/webhooks",
        disposer_evidence="callback",
        gap_class="small",
        minimal_diff=True,
        synthesized_patch=True,
        fixture_dir="ssrf_webhook",
        notes=(
            "Synthetic fixture modeled on an SSRF pattern. Does NOT reproduce CVE-2024-21672 "
            "(Atlassian Confluence RCE — unrelated product and class). Webhook URL accepted without "
            "validation; patch adds is_internal_target check (P0 classifier). OOB-callback harness."
        ),
    ),
    BV2PPair(
        pair_id="ssrf-open-redirect",
        primitive="ssrf",
        cve="pattern:CVE-2023-36827",
        is_real_cve=False,
        title="Image Proxy SSRF via Open Redirect",
        vuln_endpoint="POST /api/v1/proxy/fetch",
        disposer_evidence="reachability",
        gap_class="small",
        minimal_diff=True,
        synthesized_patch=True,
        fixture_dir="ssrf_redirect",
        notes=(
            "Synthetic fixture modeled on an open-redirect/SSRF pattern. Does NOT reproduce "
            "CVE-2023-36827 (Fides/Ethyca path traversal — unrelated product and class). Image proxy "
            "follows redirects without destination validation; patch checks final URL via is_internal_target (P0)."
        ),
    ),
    BV2PPair(
        pair_id="auth-bypass-admin-panel",
        primitive="bfla",
        cve="pattern:CVE-2024-41667",
        is_real_cve=False,
        title="Admin Panel Auth Bypass (missing role check)",
        vuln_endpoint="GET /api/admin/config",
        disposer_evidence="diff",
        gap_class="small",
        minimal_diff=True,
        synthesized_patch=True,
        fixture_dir="auth_bypass_admin",
        notes=(
            "Synthetic fixture modeled on a broken-function-level-authorization pattern. Does NOT "
            "reproduce CVE-2024-41667 (OpenAM FreeMarker template injection/RCE — unrelated product "
            "and class). Endpoint checks auth but not role; patch adds one-line is_admin check."
        ),
    ),
    BV2PPair(
        pair_id="auth-bypass-password-reset",
        primitive="bfla",
        cve="pattern:CVE-2023-45158",
        is_real_cve=False,
        title="Password Reset Token Takeover (token not bound to username)",
        vuln_endpoint="POST /api/v1/auth/reset-password",
        disposer_evidence="diff",
        gap_class="small",
        minimal_diff=True,
        synthesized_patch=True,
        fixture_dir="auth_bypass_reset",
        notes=(
            "Synthetic fixture modeled on a password-reset-token-binding pattern. Does NOT reproduce "
            "CVE-2023-45158 (web2py OS command injection — unrelated product and class). Any valid "
            "reset token can reset any account; patch adds one-line token-binding check (token maps to username)."
        ),
    ),
    BV2PPair(
        pair_id="mass-assign-profile",
        primitive="business_logic",
        cve="pattern:CVE-2024-5489",
        is_real_cve=False,
        title="User Profile Mass Assignment (unfiltered field update)",
        vuln_endpoint="PATCH /api/v1/users/{username}/profile",
        disposer_evidence="diff",
        gap_class="small",
        minimal_diff=True,
        synthesized_patch=True,
        fixture_dir="mass_assign_profile",
        notes=(
            "Synthetic fixture modeled on a mass-assignment pattern. Does NOT reproduce CVE-2024-5489 "
            "(WordPress 'Custom Font Uploader' missing-authz — unrelated product and class). is_admin "
            "field updated via profile PATCH; patch adds allowlist filter stripping privileged fields before write."
        ),
    ),
    BV2PPair(
        pair_id="sqli-product-search",
        primitive="business_logic",
        cve="pattern:CVE-2023-46604",
        is_real_cve=False,
        title="Product Search SQL Injection (string interpolation)",
        vuln_endpoint="GET /api/v1/products/search",
        disposer_evidence="diff",
        gap_class="small",
        minimal_diff=True,
        synthesized_patch=True,
        fixture_dir="sqli_search",
        notes=(
            "Synthetic fixture modeled on a SQL-injection pattern. Does NOT reproduce CVE-2023-46604 "
            "(Apache ActiveMQ OpenWire deserialization RCE, CISA-KEV — unrelated product and class). "
            "UNION injection returns privileged rows; patch parameterises query — injected metacharacters yield empty results."
        ),
    ),
    # ── Real CVE pairs added 2026-07-25 ──────────────────────────────────────────
    BV2PPair(
        pair_id="openwebui-bfla-arena-model",
        primitive="bfla",
        cve="CVE-2026-59225",
        is_real_cve=True,
        title="Open WebUI Arena BFLA — model access control bypass via bypass_filter",
        vuln_endpoint="POST /api/v1/arena/complete",
        disposer_evidence="diff",
        gap_class="small",
        minimal_diff=False,
        synthesized_patch=False,
        fixture_dir="bfla_arena_model",
        notes=(
            "Real CVE. GHSA-m3qf-58wf-w979. Arena fallback dispatch called bypass_filter=True "
            "which skipped the per-model access check. Fix: 6-line access check inserted before "
            "bypass_filter dispatch. Probe: bob (no gpt-4o access) via bypass_filter=True. "
            "Vuln: 200. Patched: 403."
        ),
    ),
    BV2PPair(
        pair_id="openwebui-bfla-kb-upload",
        primitive="bfla",
        cve="CVE-2026-59217",
        is_real_cve=True,
        title="Open WebUI KB Upload BFLA — write-access bypass via metadata.knowledge_id",
        vuln_endpoint="POST /api/v1/files/",
        disposer_evidence="diff",
        gap_class="small",
        minimal_diff=False,
        synthesized_patch=False,
        fixture_dir="bfla_kb_upload",
        notes=(
            "Real CVE. GHSA-7r7x-gjvr-448g. File upload accepted client-supplied metadata.knowledge_id "
            "and auto-linked without checking write access. Fix: AccessGrants write check before link. "
            "Probe: bob uploads to kb-restricted (admin-only). Vuln: 200. Patched: 403."
        ),
    ),
    BV2PPair(
        pair_id="openwebui-path-traversal-proxy",
        primitive="ssrf",
        cve="CVE-2026-59221",
        is_real_cve=True,
        title="Open WebUI Proxy Path Traversal — decode-cap bypass via 9x encoded traversal",
        vuln_endpoint="GET /proxy/static/{path}",
        disposer_evidence="diff",
        gap_class="small",
        minimal_diff=False,
        synthesized_patch=False,
        fixture_dir="path_traversal_proxy",
        notes=(
            "Real CVE. GHSA-frvj-c5qp-xj4w. URL-decode loop capped at N rounds but did not "
            "check if path was still encoded after the cap — over-encoded traversal sequences bypassed "
            "the guard. Fix: fail-closed check (unquote(path) != path → return None). "
            "Probe: double-encoded traversal %252e%252e%252fetc%252fpasswd. Vuln: 200. Patched: 400/403."
        ),
    ),
)


def ground_truth_labels(pairs: Sequence[BV2PPair] = BV2P_CORPUS) -> set[str]:
    """The labeled vulnerable-endpoint set ``V`` (recall-over-known; unknown-unknown caveat)."""
    return {pair.vuln_endpoint for pair in pairs}


def small_gap_pairs(pairs: Sequence[BV2PPair] = BV2P_CORPUS) -> tuple[BV2PPair, ...]:
    return tuple(pair for pair in pairs if pair.gap_class == "small")


@dataclass(frozen=True)
class PowerCheck:
    """Corpus-level power readout for the gap-stratified paired McNemar (E2 primary).

    ``small_gap_count`` is the available small-gap pairs — the *ceiling* on discordant pairs; the
    actual discordant count is an experimental outcome observed at run time. ``sufficient`` is the
    honest gate against ``required_discordant``: with a tiny seed corpus it is expected to be
    False, and no tight effect size may be reported until it holds.
    """

    small_gap_count: int
    required_discordant: int
    sufficient: bool


def power_check(required_discordant: int, pairs: Sequence[BV2PPair] = BV2P_CORPUS) -> PowerCheck:
    count = len(small_gap_pairs(pairs))
    return PowerCheck(
        small_gap_count=count,
        required_discordant=required_discordant,
        sufficient=count >= required_discordant,
    )
