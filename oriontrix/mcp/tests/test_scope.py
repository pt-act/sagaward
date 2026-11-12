"""Scope validation tests for the MCP server — AC-SMCP-7a, AC-SMCP-7b."""

from __future__ import annotations

import pytest

from oriontrix.core.govern.scope import (
    ActionClass,
    Decision,
    EngagementCtx,
    ScopeRule,
    Target,
    Verdict,
    decide,
    load_scope,
)
from oriontrix.mcp.server import _build_scope_entries


# ---------------------------------------------------------------------------
# AC-SMCP-7a: decide() refuses login.pwn.intigriti.rocks when scope is
#              app.pwn.intigriti.rocks
# ---------------------------------------------------------------------------

class TestScopeRefusal:
    """Scope boundary enforcement tests (AC-SMCP-7a)."""

    def test_refuses_login_when_scope_is_app(self):
        """login.pwn.intigriti.rocks MUST be DENIED when scope is app.pwn.intigriti.rocks."""
        ctx = load_scope(["app.pwn.intigriti.rocks", "*.app.pwn.intigriti.rocks"])
        target = Target(host="login.pwn.intigriti.rocks", action_class=ActionClass.HTTP)
        decision = decide(target, ctx)
        assert decision.verdict == Verdict.DENY, (
            f"Expected DENY for login.pwn.intigriti.rocks but got {decision.verdict}: {decision.reason}"
        )

    def test_allows_app_when_scope_is_app(self):
        """app.pwn.intigriti.rocks MUST be ALLOWED when it's in scope."""
        ctx = load_scope(["app.pwn.intigriti.rocks", "*.app.pwn.intigriti.rocks"])
        target = Target(host="app.pwn.intigriti.rocks", action_class=ActionClass.HTTP)
        decision = decide(target, ctx)
        assert decision.verdict == Verdict.ALLOW

    def test_allows_subdomain_of_app(self):
        """sub.app.pwn.intigriti.rocks MUST be ALLOWED when *.app.pwn is in scope."""
        ctx = load_scope(["app.pwn.intigriti.rocks", "*.app.pwn.intigriti.rocks"])
        target = Target(host="sub.app.pwn.intigriti.rocks", action_class=ActionClass.HTTP)
        decision = decide(target, ctx)
        assert decision.verdict == Verdict.ALLOW

    def test_refuses_unrelated_host(self):
        """Entirely unrelated host MUST be DENIED."""
        ctx = load_scope(["app.pwn.intigriti.rocks"])
        target = Target(host="evil.com", action_class=ActionClass.HTTP)
        decision = decide(target, ctx)
        assert decision.verdict == Verdict.DENY

    def test_refuses_sibling_subdomain(self):
        """api.pwn.intigriti.rocks is a sibling, not a child — MUST be DENIED."""
        ctx = load_scope(["app.pwn.intigriti.rocks", "*.app.pwn.intigriti.rocks"])
        target = Target(host="api.pwn.intigriti.rocks", action_class=ActionClass.HTTP)
        decision = decide(target, ctx)
        assert decision.verdict == Verdict.DENY

    def test_refuses_parent_domain(self):
        """pwn.intigriti.rocks (parent) MUST be DENIED when only app.pwn is in scope."""
        ctx = load_scope(["app.pwn.intigriti.rocks"])
        target = Target(host="pwn.intigriti.rocks", action_class=ActionClass.HTTP)
        decision = decide(target, ctx)
        assert decision.verdict == Verdict.DENY


class TestScopeFromURL:
    """Test _build_scope_entries produces correct entries from target URLs."""

    def test_url_scope_entries(self):
        entries = _build_scope_entries("https://app.pwn.intigriti.rocks/login")
        assert "app.pwn.intigriti.rocks" in entries
        assert "*.app.pwn.intigriti.rocks" in entries
        assert len(entries) == 2

    def test_bare_host(self):
        entries = _build_scope_entries("example.com")
        assert "example.com" in entries
        assert "*.example.com" in entries


class TestFailClosed:
    """Fail-closed behavior (scope invariant)."""

    def test_no_rules_deny(self):
        """Empty scope → DENY everything."""
        ctx = EngagementCtx(rules=[])
        decision = decide(Target(host="anything.com", action_class=ActionClass.HTTP), ctx)
        assert decision.verdict == Verdict.DENY
        assert "no_rules" in decision.reason

    def test_expired_context_deny(self):
        """Expired context → DENY."""
        from datetime import datetime, timezone, timedelta

        expired = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        ctx = EngagementCtx(
            rules=[ScopeRule(pattern="example.com")],
            expires_at=expired,
        )
        decision = decide(Target(host="example.com", action_class=ActionClass.HTTP), ctx)
        assert decision.verdict == Verdict.DENY
        assert "expired" in decision.reason


# ---------------------------------------------------------------------------
# AC-SMCP-7b: Documented in COMPLETION_REPORT.md — external containment
#              is prerequisite, not claimed as structural
# ---------------------------------------------------------------------------
# AC-SMCP-7b is a documentation requirement, not a code test.
# The COMPLETION_REPORT.md explicitly states that external containment
# (network-level isolation, Docker network policies, egress proxy)
# is a prerequisite that the MCP wrapper does NOT provide.
