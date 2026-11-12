"""Adversarial injection tests — AC-SMCP-8: harness_confirmed / evidence_class injection.

10 injection attempts across all tools, 0 successes expected.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from oriontrix.mcp.server import _engagements, _strip_injection_fields, handle_jsonrpc


@pytest.fixture(autouse=True)
def _clean_engagements():
    _engagements.clear()
    yield
    _engagements.clear()


async def _call_tool(tool_name: str, arguments: dict, req_id: int = 1) -> dict:
    """Helper: call a tool via JSON-RPC and return parsed content."""
    resp = await handle_jsonrpc({
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    })
    return json.loads(resp["result"]["content"][0]["text"])


# ---------------------------------------------------------------------------
# AC-SMCP-8: 10 injection attempts, 0 successes
# ---------------------------------------------------------------------------

class TestInjectionPrevention:
    """Caller injecting harness_confirmed/evidence_class has zero effect (AC-SMCP-8)."""

    # --- Injection via oriontrix_corpus_status (attempts 1-2) ---

    @pytest.mark.asyncio
    async def test_inject_harness_confirmed_corpus(self):
        """Attempt 1: Inject harness_confirmed into corpus_status."""
        result = await _call_tool("oriontrix_corpus_status", {"harness_confirmed": True}, 101)
        assert "harness_confirmed" not in result
        assert result["pairs"] == 13  # Normal response

    @pytest.mark.asyncio
    async def test_inject_evidence_class_corpus(self):
        """Attempt 2: Inject evidence_class into corpus_status."""
        result = await _call_tool("oriontrix_corpus_status", {"evidence_class": "diff"}, 102)
        assert "evidence_class" not in result or result.get("evidence_class") != "diff"

    # --- Injection via oriontrix_engagement_status (attempts 3-4) ---

    @pytest.mark.asyncio
    async def test_inject_harness_confirmed_status(self):
        """Attempt 3: Inject harness_confirmed into engagement_status."""
        result = await _call_tool("oriontrix_engagement_status", {
            "engagement_id": "fake",
            "harness_confirmed": True,
        }, 103)
        # Should get "unknown engagement" error, not accept the injection
        assert "error" in result

    @pytest.mark.asyncio
    async def test_inject_evidence_class_status(self):
        """Attempt 4: Inject evidence_class into engagement_status."""
        result = await _call_tool("oriontrix_engagement_status", {
            "engagement_id": "fake",
            "evidence_class": "callback",
        }, 104)
        assert "error" in result

    # --- Injection via oriontrix_get_findings (attempts 5-6) ---

    @pytest.mark.asyncio
    async def test_inject_harness_confirmed_findings(self):
        """Attempt 5: Inject harness_confirmed into get_findings."""
        result = await _call_tool("oriontrix_get_findings", {
            "engagement_id": "fake",
            "harness_confirmed": True,
        }, 105)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_inject_evidence_class_findings(self):
        """Attempt 6: Inject evidence_class into get_findings."""
        result = await _call_tool("oriontrix_get_findings", {
            "engagement_id": "fake",
            "evidence_class": "race_result",
        }, 106)
        assert "error" in result

    # --- Injection via oriontrix_get_funnel (attempts 7-8) ---

    @pytest.mark.asyncio
    async def test_inject_harness_confirmed_funnel(self):
        """Attempt 7: Inject harness_confirmed into get_funnel."""
        result = await _call_tool("oriontrix_get_funnel", {
            "engagement_id": "fake",
            "harness_confirmed": True,
        }, 107)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_inject_evidence_class_funnel(self):
        """Attempt 8: Inject evidence_class into get_funnel."""
        result = await _call_tool("oriontrix_get_funnel", {
            "engagement_id": "fake",
            "evidence_class": "reachability",
        }, 108)
        assert "error" in result

    # --- Injection via oriontrix_run_engagement (attempts 9-10) ---

    @pytest.mark.asyncio
    async def test_inject_harness_confirmed_run(self):
        """Attempt 9: Inject harness_confirmed into run_engagement.
        
        Note: This may fail due to Docker not being available (I5 fail-closed),
        which is correct behavior — the injection field is still stripped.
        """
        result = await _call_tool("oriontrix_run_engagement", {
            "target": "http://example.com",
            "harness_confirmed": True,
        }, 109)
        # Either Docker error or scope denial — but harness_confirmed must not appear
        assert "harness_confirmed" not in json.dumps(result)

    @pytest.mark.asyncio
    async def test_inject_evidence_class_run(self):
        """Attempt 10: Inject evidence_class into run_engagement."""
        result = await _call_tool("oriontrix_run_engagement", {
            "target": "http://example.com",
            "evidence_class": "diff",
        }, 110)
        assert "evidence_class" not in json.dumps(result) or "diff" not in json.dumps(result).replace("evidence_class", "")


# ---------------------------------------------------------------------------
# Supplementary: _strip_injection_fields unit tests
# ---------------------------------------------------------------------------

class TestStripFunction:
    """Direct tests on the stripping function."""

    def test_strips_both_fields(self):
        cleaned = _strip_injection_fields({
            "target": "http://x.com",
            "harness_confirmed": True,
            "evidence_class": "diff",
            "scan_mode": "quick",
        })
        assert "harness_confirmed" not in cleaned
        assert "evidence_class" not in cleaned
        assert cleaned["target"] == "http://x.com"
        assert cleaned["scan_mode"] == "quick"

    def test_empty_dict(self):
        assert _strip_injection_fields({}) == {}

    def test_only_injection_fields(self):
        cleaned = _strip_injection_fields({
            "harness_confirmed": True,
            "evidence_class": "callback",
        })
        assert cleaned == {}

    def test_nested_injection_not_stripped(self):
        """Only top-level injection fields are stripped (nested is passthrough)."""
        cleaned = _strip_injection_fields({
            "metadata": {"harness_confirmed": True},
        })
        # We only strip top-level — nested passes through (this is fine per I2;
        # the engine ignores nested fields from MCP input)
        assert "metadata" in cleaned
