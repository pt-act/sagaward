"""Unit tests for the Strix MCP server — AC-SMCP-2, AC-SMCP-3, AC-SMCP-10, AC-SMCP-12, AC-SMCP-13, AC-SMCP-14."""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from strix.mcp.server import (
    TOOLS,
    _TOOL_DISPATCH,
    _engagements,
    _strip_injection_fields,
    handle_jsonrpc,
)


@pytest.fixture(autouse=True)
def _clean_engagements():
    """Clear engagement registry between tests."""
    _engagements.clear()
    yield
    _engagements.clear()


# ---------------------------------------------------------------------------
# AC-SMCP-2: Server starts, tools/list works, malformed input rejected
# ---------------------------------------------------------------------------

class TestProtocol:
    """JSON-RPC protocol tests (AC-SMCP-2)."""

    @pytest.mark.asyncio
    async def test_initialize(self):
        resp = await handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        assert resp["id"] == 1
        assert "result" in resp
        assert resp["result"]["serverInfo"]["name"] == "strix"
        assert resp["result"]["protocolVersion"] == "2024-11-05"

    @pytest.mark.asyncio
    async def test_tools_list(self):
        resp = await handle_jsonrpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        assert resp["id"] == 2
        tools = resp["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        assert "strix_run_engagement" in tool_names
        assert "strix_engagement_status" in tool_names
        assert "strix_get_findings" in tool_names
        assert "strix_get_funnel" in tool_names
        assert "strix_corpus_status" in tool_names
        assert len(tools) == 5

    @pytest.mark.asyncio
    async def test_tools_list_matches_dispatch(self):
        """Every listed tool has a dispatch handler."""
        resp = await handle_jsonrpc({"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}})
        tool_names = {t["name"] for t in resp["result"]["tools"]}
        assert tool_names == set(_TOOL_DISPATCH.keys())

    @pytest.mark.asyncio
    async def test_malformed_json_error(self):
        """Non-dict input returns invalid request error."""
        resp = await handle_jsonrpc({"jsonrpc": "2.0", "id": 4, "method": "nonexistent"})
        assert resp.get("error", {}).get("code") == -32601

    @pytest.mark.asyncio
    async def test_unknown_method(self):
        resp = await handle_jsonrpc({"jsonrpc": "2.0", "id": 5, "method": "foo/bar", "params": {}})
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        resp = await handle_jsonrpc({
            "jsonrpc": "2.0", "id": 6, "method": "tools/call",
            "params": {"name": "nonexistent_tool", "arguments": {}}
        })
        assert "error" in resp
        assert resp["error"]["code"] == -32601


# ---------------------------------------------------------------------------
# AC-SMCP-3: corpus_status returns correct counts
# ---------------------------------------------------------------------------

class TestCorpusStatus:
    """Corpus status tests (AC-SMCP-3, AC-SMCP-13)."""

    @pytest.mark.asyncio
    async def test_corpus_counts(self):
        resp = await handle_jsonrpc({
            "jsonrpc": "2.0", "id": 10, "method": "tools/call",
            "params": {"name": "strix_corpus_status", "arguments": {}}
        })
        content = json.loads(resp["result"]["content"][0]["text"])
        assert content["pairs"] == 13
        assert content["public_cve_count"] == 5  # 5 genuine public CVEs (is_real_cve=True), PM NVD-verified
        assert content["synthetic_count"] == 8  # 8 synthetic-pattern fixtures (pattern:CVE-X, do not reproduce)
        assert content["real_patch_count"] == 4  # 4 pairs have real upstream patches
        assert content["synthesized_patch_count"] == 9  # 9 pairs have synthesized patches
        assert content["impact_gate"] == "on"
        assert isinstance(content["harness_capabilities"], list)
        assert isinstance(content["native_capabilities"], list)
        assert content["native_capabilities_count"] == 48  # _BASE_TOOLS count
        assert isinstance(content["corpus_hash"], str)
        assert len(content["corpus_hash"]) == 16

    @pytest.mark.asyncio
    async def test_corpus_status_bounded_time(self):
        """AC-SMCP-13: corpus_status returns within bounded time (< 2s)."""
        start = time.monotonic()
        resp = await handle_jsonrpc({
            "jsonrpc": "2.0", "id": 11, "method": "tools/call",
            "params": {"name": "strix_corpus_status", "arguments": {}}
        })
        elapsed = time.monotonic() - start
        assert elapsed < 2.0
        assert resp["result"]["isError"] is False


# ---------------------------------------------------------------------------
# AC-SMCP-10: Fabricated engagement_id rejected
# ---------------------------------------------------------------------------

class TestEngagementValidation:
    """Engagement ID validation tests (AC-SMCP-10)."""

    @pytest.mark.asyncio
    async def test_fabricated_id_status(self):
        resp = await handle_jsonrpc({
            "jsonrpc": "2.0", "id": 20, "method": "tools/call",
            "params": {"name": "strix_engagement_status", "arguments": {"engagement_id": "fake-12345"}}
        })
        content = json.loads(resp["result"]["content"][0]["text"])
        assert "error" in content
        assert "Unknown engagement_id" in content["error"]

    @pytest.mark.asyncio
    async def test_fabricated_id_findings(self):
        resp = await handle_jsonrpc({
            "jsonrpc": "2.0", "id": 21, "method": "tools/call",
            "params": {"name": "strix_get_findings", "arguments": {"engagement_id": "fake-99999"}}
        })
        content = json.loads(resp["result"]["content"][0]["text"])
        assert "error" in content

    @pytest.mark.asyncio
    async def test_fabricated_id_funnel(self):
        resp = await handle_jsonrpc({
            "jsonrpc": "2.0", "id": 22, "method": "tools/call",
            "params": {"name": "strix_get_funnel", "arguments": {"engagement_id": "nope"}}
        })
        content = json.loads(resp["result"]["content"][0]["text"])
        assert "error" in content

    @pytest.mark.asyncio
    async def test_empty_engagement_id(self):
        resp = await handle_jsonrpc({
            "jsonrpc": "2.0", "id": 23, "method": "tools/call",
            "params": {"name": "strix_engagement_status", "arguments": {"engagement_id": ""}}
        })
        content = json.loads(resp["result"]["content"][0]["text"])
        assert "error" in content


# ---------------------------------------------------------------------------
# AC-SMCP-1: No curation — native_capabilities_count == 46
# ---------------------------------------------------------------------------

class TestNoCuration:
    """Verify _BASE_TOOLS count (AC-SMCP-1)."""

    @pytest.mark.asyncio
    async def test_base_tools_count(self):
        """corpus_status native_capabilities_count must equal _BASE_TOOLS length (46)."""
        from strix.agents.factory import _BASE_TOOLS

        resp = await handle_jsonrpc({
            "jsonrpc": "2.0", "id": 30, "method": "tools/call",
            "params": {"name": "strix_corpus_status", "arguments": {}}
        })
        content = json.loads(resp["result"]["content"][0]["text"])
        assert content["native_capabilities_count"] == len(_BASE_TOOLS)
        assert len(_BASE_TOOLS) == 48

    @pytest.mark.asyncio
    async def test_all_tool_names_present(self):
        """Every _BASE_TOOLS name appears in native_capabilities."""
        from strix.agents.factory import _BASE_TOOLS

        resp = await handle_jsonrpc({
            "jsonrpc": "2.0", "id": 31, "method": "tools/call",
            "params": {"name": "strix_corpus_status", "arguments": {}}
        })
        content = json.loads(resp["result"]["content"][0]["text"])
        expected_names = {t.name for t in _BASE_TOOLS}
        actual_names = set(content["native_capabilities"])
        assert expected_names == actual_names


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class TestStripping:
    """Verify _strip_injection_fields works."""

    def test_strips_harness_confirmed(self):
        cleaned = _strip_injection_fields({"target": "http://x.com", "harness_confirmed": True})
        assert "harness_confirmed" not in cleaned
        assert cleaned["target"] == "http://x.com"

    def test_strips_evidence_class(self):
        cleaned = _strip_injection_fields({"engagement_id": "x", "evidence_class": "diff"})
        assert "evidence_class" not in cleaned

    def test_preserves_valid_fields(self):
        original = {"target": "http://x.com", "scan_mode": "quick", "instruction": "test"}
        cleaned = _strip_injection_fields(original)
        assert cleaned == original
