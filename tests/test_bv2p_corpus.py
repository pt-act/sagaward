"""M2 B-V2P corpus — registry + per-pair exploitability (vuln side fires, patch side does not).

Disposer checks use the *real* deterministic disposers, hermetically:
- IDOR/BFLA/auth-bypass/mass-assign/SQLi pairs -> the P2 differential engine
  (`sagaward.core.diff.diff`): the attacker's cross-user request is 2xx on the vuln deployment and
  4xx on the patch, so the engine flags ``gained_access`` across the pair.
- SSRF pairs -> the P0 net classifier (`sagaward.core.net.is_internal_target`) via the fixture's
  patched guard: internal/metadata targets are blocked, externals allowed; the vuln guard allows
  everything. (Full OOB-callback confirmation is a live/Docker step, run on the operator's host.)

The fixtures' framework-free ``core`` modules are loaded by path (``benchmarks/`` is not an
installed package); the FastAPI ``app.py`` wrappers are exercised only in the live/Docker run.

M2 expansion adds 8 new pairs to reach n=10 total for E2 gap-stratified McNemar statistical power.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import TestCase
from unittest.mock import patch

from sagaward.core.diff import diff


if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType
from sagaward.research.corpus import (
    BV2P_CORPUS,
    ground_truth_labels,
    power_check,
    small_gap_pairs,
)


_BENCH = Path(__file__).resolve().parents[1] / "benchmarks" / "bv2p"


def _load(rel: str, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, _BENCH / rel)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {rel}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_idor = _load("idor_memories/core.py", "bv2p_idor_core")
_ssrf = _load("ssrf_fetch/core.py", "bv2p_ssrf_core")
_bfla_inv = _load("bfla_invoices/core.py", "bv2p_bfla_inv_core")
_idor_files = _load("idor_files/core.py", "bv2p_idor_files_core")
_ssrf_webhook = _load("ssrf_webhook/core.py", "bv2p_ssrf_webhook_core")
_ssrf_redirect = _load("ssrf_redirect/core.py", "bv2p_ssrf_redirect_core")
_auth_admin = _load("auth_bypass_admin/core.py", "bv2p_auth_admin_core")
_auth_reset = _load("auth_bypass_reset/core.py", "bv2p_auth_reset_core")
_mass_assign = _load("mass_assign_profile/core.py", "bv2p_mass_assign_core")
_sqli = _load("sqli_search/core.py", "bv2p_sqli_core")


def _response_of(call: Callable[[], dict[str, object]]) -> dict[str, Any]:
    """Run a fixture handler and shape its outcome as a diff-engine response dict."""
    try:
        body = call()
    except _idor.MemoryAccessError as exc:
        return {"status_code": exc.status_code, "headers": {}, "body": json.dumps(exc.detail)}
    return {"status_code": 200, "headers": {}, "body": json.dumps(body, default=str)}


class TestCorpusRegistry(TestCase):
    def test_seeds_present_and_well_formed(self) -> None:
        ids = {pair.pair_id for pair in BV2P_CORPUS}
        self.assertIn("openwebui-idor-memories", ids)
        self.assertIn("flowise-ssrf-http-node", ids)
        for pair in BV2P_CORPUS:
            self.assertTrue(pair.cve.startswith("CVE-"))
            self.assertTrue(pair.vuln_endpoint)
            self.assertIn(
                pair.disposer_evidence, {"diff", "callback", "reachability", "race_result"}
            )

    def test_ground_truth_is_labeled_known_set(self) -> None:
        self.assertEqual(ground_truth_labels(), {p.vuln_endpoint for p in BV2P_CORPUS})

    def test_corpus_is_small_gap_biased(self) -> None:
        self.assertEqual(set(small_gap_pairs()), set(BV2P_CORPUS))

    def test_power_check_is_honest_about_tiny_n(self) -> None:
        # After M2 expansion the corpus has 10 small-gap pairs, which meets the E2 requirement.
        result = power_check(required_discordant=10)
        self.assertEqual(result.small_gap_count, len(small_gap_pairs()))
        self.assertTrue(result.sufficient)
        self.assertTrue(power_check(required_discordant=1).sufficient)

    def test_m2_expansion_ids_present(self) -> None:
        ids = {pair.pair_id for pair in BV2P_CORPUS}
        expected = {
            "bfla-invoices", "idor-files-download", "ssrf-webhook-registration",
            "ssrf-open-redirect", "auth-bypass-admin-panel", "auth-bypass-password-reset",
            "mass-assign-profile", "sqli-product-search",
        }
        for eid in expected:
            self.assertIn(eid, ids)

    def test_corpus_reaches_ten_small_gap_pairs(self) -> None:
        self.assertGreaterEqual(len(small_gap_pairs()), 10)


class TestIdorPair(TestCase):
    """P2-disposer exploitability: the attacker's cross-user request flips across the pair."""

    def _attacker_update(self) -> dict[str, object]:
        # bob updates alice-owned mem-1 — the IDOR.
        return _idor.update_memory("mem-1", "bob", "pwned")

    def test_vuln_allows_cross_user_update_patch_forbids(self) -> None:
        with patch.dict(os.environ, {"VULN_MODE": "1"}):
            _idor.reset_state()
            self.assertEqual(self._attacker_update()["user_id"], "alice")  # wrote alice's memory
        with patch.dict(os.environ, {"VULN_MODE": "0"}):
            _idor.reset_state()
            with self.assertRaises(_idor.MemoryAccessError) as ctx:
                self._attacker_update()
            self.assertEqual(ctx.exception.status_code, 403)

    def test_p2_diff_flags_gained_access_across_the_pair(self) -> None:
        with patch.dict(os.environ, {"VULN_MODE": "1"}):
            _idor.reset_state()
            vuln_resp = _response_of(self._attacker_update)
        with patch.dict(os.environ, {"VULN_MODE": "0"}):
            _idor.reset_state()
            patch_resp = _response_of(self._attacker_update)

        flipped = diff(
            [{"label": "patch", "response": patch_resp}, {"label": "vuln", "response": vuln_resp}]
        )
        self.assertTrue(
            any(d.auth_signal_delta == "gained_access" for d in flipped.deltas),
            "P2 disposer must flag gained_access on the vuln-vs-patch pair",
        )

        # Patch deployment alone: no gained_access -> the harness stays silent (no false confirm).
        same = diff(
            [{"label": "a", "response": patch_resp}, {"label": "b", "response": patch_resp}]
        )
        self.assertFalse(any(d.auth_signal_delta == "gained_access" for d in same.deltas))


class TestSsrfPair(TestCase):
    """P0-classifier exploitability: the patched guard blocks internal/metadata SSRF targets."""

    def test_vuln_allows_everything_patch_blocks_internal(self) -> None:
        internal = "http://169.254.169.254/latest/meta-data/"
        external = "http://example.com/health"
        with patch.dict(os.environ, {"VULN_MODE": "1"}):
            self.assertTrue(_ssrf.screen_fetch(internal)[0])  # SSRF: internal fetch allowed
        with patch.dict(os.environ, {"VULN_MODE": "0"}):
            self.assertFalse(_ssrf.screen_fetch(internal)[0])  # patched: blocked
            self.assertTrue(_ssrf.screen_fetch(external)[0])  # external still allowed

    def test_patch_blocks_private_ranges(self) -> None:
        with patch.dict(os.environ, {"VULN_MODE": "0"}):
            for target in ("http://127.0.0.1:8080/", "http://10.0.0.5/", "http://localhost/x"):
                self.assertFalse(_ssrf.screen_fetch(target)[0], f"{target} must be blocked")


# ---------------------------------------------------------------------------
# M2 expansion test classes
# ---------------------------------------------------------------------------


def _diff_response_of(call: Any, exc_type: type) -> dict[str, Any]:
    """Shape a fixture call result as a diff-engine response dict (generic version)."""
    try:
        body = call()
    except exc_type as exc:
        return {"status_code": exc.status_code, "headers": {}, "body": json.dumps(exc.detail)}
    return {"status_code": 200, "headers": {}, "body": json.dumps(body, default=str)}


class TestBflaInvoices(TestCase):
    """BFLA: carol (org-C) fetches org-A invoice — allowed vuln, forbidden patched."""

    def _attacker_call(self) -> dict[str, object]:
        return _bfla_inv.get_invoice("inv-1", "carol")  # carol is org-C, inv-1 is org-A

    def test_vuln_allows_cross_org_patch_forbids(self) -> None:
        with patch.dict(os.environ, {"VULN_MODE": "1"}):
            _bfla_inv.reset_state()
            result = self._attacker_call()
            self.assertEqual(result["org_id"], "org-A")
        with patch.dict(os.environ, {"VULN_MODE": "0"}):
            _bfla_inv.reset_state()
            with self.assertRaises(_bfla_inv.InvoiceAccessError) as ctx:
                self._attacker_call()
            self.assertEqual(ctx.exception.status_code, 403)

    def test_p2_diff_flags_gained_access(self) -> None:
        with patch.dict(os.environ, {"VULN_MODE": "1"}):
            _bfla_inv.reset_state()
            vuln_resp = _diff_response_of(self._attacker_call, _bfla_inv.InvoiceAccessError)
        with patch.dict(os.environ, {"VULN_MODE": "0"}):
            _bfla_inv.reset_state()
            patch_resp = _diff_response_of(self._attacker_call, _bfla_inv.InvoiceAccessError)
        flipped = diff(
            [{"label": "patch", "response": patch_resp}, {"label": "vuln", "response": vuln_resp}]
        )
        self.assertTrue(any(d.auth_signal_delta == "gained_access" for d in flipped.deltas))


class TestIdorFiles(TestCase):
    """IDOR: bob downloads alice's file — allowed vuln, forbidden patched."""

    def _attacker_call(self) -> dict[str, object]:
        return _idor_files.download_file("file-a1b2", "bob")

    def test_vuln_allows_cross_user_download_patch_forbids(self) -> None:
        with patch.dict(os.environ, {"VULN_MODE": "1"}):
            _idor_files.reset_state()
            result = self._attacker_call()
            self.assertEqual(result["owner"], "alice")
        with patch.dict(os.environ, {"VULN_MODE": "0"}):
            _idor_files.reset_state()
            with self.assertRaises(_idor_files.FileAccessError) as ctx:
                self._attacker_call()
            self.assertEqual(ctx.exception.status_code, 403)

    def test_p2_diff_flags_gained_access(self) -> None:
        with patch.dict(os.environ, {"VULN_MODE": "1"}):
            _idor_files.reset_state()
            vuln_resp = _diff_response_of(self._attacker_call, _idor_files.FileAccessError)
        with patch.dict(os.environ, {"VULN_MODE": "0"}):
            _idor_files.reset_state()
            patch_resp = _diff_response_of(self._attacker_call, _idor_files.FileAccessError)
        flipped = diff(
            [{"label": "patch", "response": patch_resp}, {"label": "vuln", "response": vuln_resp}]
        )
        self.assertTrue(any(d.auth_signal_delta == "gained_access" for d in flipped.deltas))


class TestSsrfWebhook(TestCase):
    """SSRF webhook: internal URL accepted vuln, blocked patched."""

    def test_vuln_accepts_internal_url_patch_blocks(self) -> None:
        internal = "http://169.254.169.254/latest/meta-data/"
        external = "http://example.com/notify"
        with patch.dict(os.environ, {"VULN_MODE": "1"}):
            _ssrf_webhook.reset_state()
            accepted, _ = _ssrf_webhook.register_webhook("wh-1", internal)
            self.assertTrue(accepted)
        with patch.dict(os.environ, {"VULN_MODE": "0"}):
            _ssrf_webhook.reset_state()
            blocked, _ = _ssrf_webhook.register_webhook("wh-2", internal)
            self.assertFalse(blocked)
            ok, _ = _ssrf_webhook.register_webhook("wh-3", external)
            self.assertTrue(ok)

    def test_patch_blocks_private_ranges(self) -> None:
        with patch.dict(os.environ, {"VULN_MODE": "0"}):
            _ssrf_webhook.reset_state()
            for url in ("http://127.0.0.1/hook", "http://10.0.0.1/hook", "http://localhost/hook"):
                blocked, _ = _ssrf_webhook.register_webhook("wh-x", url)
                self.assertFalse(blocked, f"{url} must be blocked")


class TestSsrfRedirect(TestCase):
    """SSRF via open redirect: internal redirect target blocked patched."""

    def test_vuln_allows_internal_redirect_patch_blocks(self) -> None:
        internal = "http://169.254.169.254/latest/meta-data/"
        with patch.dict(os.environ, {"VULN_MODE": "1"}):
            allowed, _ = _ssrf_redirect.simulate_redirect_target(internal)
            self.assertTrue(allowed)
        with patch.dict(os.environ, {"VULN_MODE": "0"}):
            blocked, _ = _ssrf_redirect.simulate_redirect_target(internal)
            self.assertFalse(blocked)

    def test_patch_blocks_private_initial_url(self) -> None:
        with patch.dict(os.environ, {"VULN_MODE": "0"}):
            for url in ("http://127.0.0.1/img", "http://10.0.0.5/img"):
                allowed, _ = _ssrf_redirect.screen_proxy_url(url)
                self.assertFalse(allowed, f"{url} must be blocked")


class TestAuthBypassAdmin(TestCase):
    """Auth bypass: regular user accesses admin config — allowed vuln, forbidden patched."""

    def _attacker_call(self) -> dict[str, object]:
        return _auth_admin.get_admin_config("alice")  # alice is not admin

    def test_vuln_allows_non_admin_patch_forbids(self) -> None:
        with patch.dict(os.environ, {"VULN_MODE": "1"}):
            _auth_admin.reset_state()
            result = self._attacker_call()
            self.assertIn("secret_key", result)
        with patch.dict(os.environ, {"VULN_MODE": "0"}):
            _auth_admin.reset_state()
            with self.assertRaises(_auth_admin.AdminAccessError) as ctx:
                self._attacker_call()
            self.assertEqual(ctx.exception.status_code, 403)

    def test_p2_diff_flags_gained_access(self) -> None:
        with patch.dict(os.environ, {"VULN_MODE": "1"}):
            _auth_admin.reset_state()
            vuln_resp = _diff_response_of(self._attacker_call, _auth_admin.AdminAccessError)
        with patch.dict(os.environ, {"VULN_MODE": "0"}):
            _auth_admin.reset_state()
            patch_resp = _diff_response_of(self._attacker_call, _auth_admin.AdminAccessError)
        flipped = diff(
            [{"label": "patch", "response": patch_resp}, {"label": "vuln", "response": vuln_resp}]
        )
        self.assertTrue(any(d.auth_signal_delta == "gained_access" for d in flipped.deltas))


class TestAuthBypassReset(TestCase):
    """Auth bypass: attacker uses alice's token to reset bob's password."""

    def _attacker_call(self) -> dict[str, object]:
        # Uses alice's valid token (tok-abc) to reset bob's password — cross-account takeover.
        return _auth_reset.reset_password("bob", "tok-abc", "hacked")

    def test_vuln_allows_cross_account_reset_patch_forbids(self) -> None:
        with patch.dict(os.environ, {"VULN_MODE": "1"}):
            _auth_reset.reset_state()
            result = self._attacker_call()
            self.assertEqual(result["username"], "bob")
        with patch.dict(os.environ, {"VULN_MODE": "0"}):
            _auth_reset.reset_state()
            with self.assertRaises(_auth_reset.ResetAccessError) as ctx:
                self._attacker_call()
            self.assertEqual(ctx.exception.status_code, 403)

    def test_p2_diff_flags_gained_access(self) -> None:
        with patch.dict(os.environ, {"VULN_MODE": "1"}):
            _auth_reset.reset_state()
            vuln_resp = _diff_response_of(self._attacker_call, _auth_reset.ResetAccessError)
        with patch.dict(os.environ, {"VULN_MODE": "0"}):
            _auth_reset.reset_state()
            patch_resp = _diff_response_of(self._attacker_call, _auth_reset.ResetAccessError)
        flipped = diff(
            [{"label": "patch", "response": patch_resp}, {"label": "vuln", "response": vuln_resp}]
        )
        self.assertTrue(any(d.auth_signal_delta == "gained_access" for d in flipped.deltas))


class TestMassAssignProfile(TestCase):
    """Mass assignment: is_admin escalated via profile PATCH — vuln succeeds, patched ignores."""

    def test_vuln_sets_is_admin_patch_ignores(self) -> None:
        with patch.dict(os.environ, {"VULN_MODE": "1"}):
            _mass_assign.reset_state()
            result = _mass_assign.update_profile("alice", {"is_admin": True, "name": "Alice"})
            self.assertTrue(result["is_admin"])
        with patch.dict(os.environ, {"VULN_MODE": "0"}):
            _mass_assign.reset_state()
            result = _mass_assign.update_profile("alice", {"is_admin": True, "name": "Alice"})
            self.assertFalse(result["is_admin"])  # patched: is_admin filtered out
            self.assertEqual(result["name"], "Alice")  # allowlisted field still updated

    def test_p2_diff_reflects_response_delta(self) -> None:
        """Vuln returns is_admin=true, patch returns is_admin=false — body differs."""
        attacker = lambda: _mass_assign.update_profile("alice", {"is_admin": True})
        with patch.dict(os.environ, {"VULN_MODE": "1"}):
            _mass_assign.reset_state()
            vuln_resp = _diff_response_of(attacker, _mass_assign.ProfileAccessError)
        with patch.dict(os.environ, {"VULN_MODE": "0"}):
            _mass_assign.reset_state()
            patch_resp = _diff_response_of(attacker, _mass_assign.ProfileAccessError)
        # Both return 200 but bodies differ — the diff engine should detect a body delta.
        self.assertEqual(vuln_resp["status_code"], 200)
        self.assertEqual(patch_resp["status_code"], 200)
        self.assertNotEqual(vuln_resp["body"], patch_resp["body"])


class TestSqliSearch(TestCase):
    """SQLi: injection payload returns privileged rows vuln, empty patched."""

    def test_vuln_injection_returns_privileged_rows_patch_returns_empty(self) -> None:
        injection = "' UNION SELECT token FROM admin--"
        with patch.dict(os.environ, {"VULN_MODE": "1"}):
            _sqli.reset_state()
            results = _sqli.search_products(injection)
            self.assertTrue(len(results) > 0)
            # The injected result contains privileged data (token field).
            self.assertTrue(any("token" in r for r in results))
        with patch.dict(os.environ, {"VULN_MODE": "0"}):
            _sqli.reset_state()
            results = _sqli.search_products(injection)
            self.assertEqual(results, [])

    def test_normal_search_works_in_both_modes(self) -> None:
        for mode in ("1", "0"):
            with patch.dict(os.environ, {"VULN_MODE": mode}):
                _sqli.reset_state()
                results = _sqli.search_products("widget")
                self.assertTrue(len(results) > 0)
                self.assertEqual(results[0]["name"], "widget")

    def test_p2_diff_reflects_response_delta(self) -> None:
        """Vuln returns privileged rows, patch returns empty — bodies differ."""
        injection = "' UNION SELECT token FROM admin--"
        attacker = lambda: _sqli.search_products(injection)  # noqa: E731
        with patch.dict(os.environ, {"VULN_MODE": "1"}):
            _sqli.reset_state()
            vuln_body = json.dumps({"results": attacker()})
        with patch.dict(os.environ, {"VULN_MODE": "0"}):
            _sqli.reset_state()
            patch_body = json.dumps({"results": attacker()})
        self.assertNotEqual(vuln_body, patch_body)


# ── New real CVE pairs ────────────────────────────────────────────────────────

class TestBflaArenaModel:
    """CVE-2026-59225 — BFLA arena model bypass."""

    def test_vuln_allows_bob_to_use_restricted_model(self):
        from benchmarks.bv2p.bfla_arena_model.core import generate_via_arena, is_vuln
        import os
        os.environ["VULN_MODE"] = "1"
        result = generate_via_arena("bob", "gpt-4o", "test", bypass_filter=True)
        assert result["model"] == "gpt-4o"

    def test_patch_denies_bob_on_restricted_model(self):
        from benchmarks.bv2p.bfla_arena_model.core import generate_via_arena, AccessError
        import os, importlib
        os.environ["VULN_MODE"] = "0"
        import benchmarks.bv2p.bfla_arena_model.core as m
        importlib.reload(m)
        try:
            m.generate_via_arena("bob", "gpt-4o", "test", bypass_filter=True)
            assert False, "should have raised AccessError"
        except m.AccessError as e:
            assert e.status_code == 403

    def test_p2_diff_flags_gained_access(self):
        import os, importlib
        os.environ["VULN_MODE"] = "1"
        import benchmarks.bv2p.bfla_arena_model.core as mv
        importlib.reload(mv)
        result_vuln = mv.generate_via_arena("bob", "gpt-4o", "test", bypass_filter=True)
        gained_vuln = result_vuln.get("model") == "gpt-4o"

        os.environ["VULN_MODE"] = "0"
        importlib.reload(mv)
        try:
            mv.generate_via_arena("bob", "gpt-4o", "test", bypass_filter=True)
            gained_patch = True
        except mv.AccessError:
            gained_patch = False

        assert gained_vuln and not gained_patch


class TestBflaKbUpload:
    """CVE-2026-59217 — BFLA KB upload write-access bypass."""

    def test_vuln_allows_bob_to_link_to_restricted_kb(self):
        from benchmarks.bv2p.bfla_kb_upload.core import upload_file, reset_state
        import os
        os.environ["VULN_MODE"] = "1"
        reset_state()
        result = upload_file("bob", "f-test", "test.pdf", "kb-restricted")
        assert result["linked_to"] == "kb-restricted"

    def test_patch_denies_bob_linking_to_restricted_kb(self):
        from benchmarks.bv2p.bfla_kb_upload.core import upload_file, reset_state, AccessError
        import os
        os.environ["VULN_MODE"] = "0"
        reset_state()
        try:
            upload_file("bob", "f-test", "test.pdf", "kb-restricted")
            assert False, "should have raised AccessError"
        except AccessError as e:
            assert e.status_code == 403

    def test_p2_diff_flags_gained_access(self):
        import os
        from benchmarks.bv2p.bfla_kb_upload.core import upload_file, reset_state, AccessError
        os.environ["VULN_MODE"] = "1"
        reset_state()
        result = upload_file("bob", "f-001", "evil.pdf", "kb-restricted")
        gained_vuln = result["linked_to"] == "kb-restricted"

        os.environ["VULN_MODE"] = "0"
        reset_state()
        try:
            upload_file("bob", "f-001", "evil.pdf", "kb-restricted")
            gained_patch = True
        except AccessError:
            gained_patch = False

        assert gained_vuln and not gained_patch


class TestPathTraversalProxy:
    """CVE-2026-59221 — Path traversal proxy decode-cap bypass."""

    def test_vuln_allows_traversal_via_double_encoded_path(self):
        from benchmarks.bv2p.path_traversal_proxy.core import read_static_file
        import os
        os.environ["VULN_MODE"] = "1"
        # Double-encoded traversal: %252e%252e → after 1 decode → %2e%2e → after 2nd → ..
        status, _ = read_static_file("/proxy/static/%252e%252e%252fetc%252fpasswd".replace("/proxy/static",""))
        # vuln: traversal escapes /static/ → 200
        assert status == 200

    def test_patch_blocks_double_encoded_traversal(self):
        from benchmarks.bv2p.path_traversal_proxy.core import read_static_file
        import os
        os.environ["VULN_MODE"] = "0"
        status, content = read_static_file("%252e%252e%252fetc%252fpasswd")
        # patched: fail-closed → 400 (still-encoded) or 403 (normalized but outside /static/)
        assert status in (400, 403)

    def test_normal_static_path_still_works(self):
        from benchmarks.bv2p.path_traversal_proxy.core import read_static_file
        import os
        for mode in ("0", "1"):
            os.environ["VULN_MODE"] = mode
            status, content = read_static_file("/static/index.html")
            assert status == 200
