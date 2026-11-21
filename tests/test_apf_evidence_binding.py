"""S-1 — the report tool's ``evidence_class`` is bound to a recorded harness verdict.

The external review's S-1: ``create_vulnerability_report`` took ``evidence_class`` as a
free string, so an agent could name evidence it never produced. The binding makes the
effective class a function of the funnel's recorded verdicts: a claim with no
corroborating confirmed verdict is filed as ``"none"`` and the impact gate down-grades
the finding to ``info``.
"""

from __future__ import annotations

import asyncio
import json
import sys
from types import ModuleType
from typing import Any

import pytest


# The agents SDK is not installed in the test venv; stub the two seams the report
# layer touches (same pattern as tests/test_identity_tools.py).
_agents: Any = ModuleType("agents")
_agents_usage: Any = ModuleType("agents.usage")


class _Usage:
    pass


_agents_usage.Usage = _Usage
_agents_usage.serialize_usage = lambda _: {}
_agents_usage.deserialize_usage = lambda _: _Usage()


class _RunContextWrapper:
    def __init__(self, context: dict[str, Any] | None = None) -> None:
        self.context = context or {}


def _function_tool(*, timeout: int = 60, strict_mode: bool = False) -> Any:
    _ = timeout, strict_mode

    def decorator(func: Any) -> Any:
        return func

    return decorator


_agents.RunContextWrapper = _RunContextWrapper
_agents.function_tool = _function_tool
sys.modules["agents"] = _agents
sys.modules["agents.usage"] = _agents_usage

from sagaward.report.state import (  # noqa: E402
    ReportState,
    get_global_report_state,
    set_global_report_state,
)


# The report tool imports ``sagaward.report.dedupe`` lazily; stub it so the test does
# not pull the full agents model tree.
_dedupe: Any = ModuleType("sagaward.report.dedupe")


async def _check_duplicate(_candidate: Any, _existing: Any) -> dict[str, Any]:
    return {"is_duplicate": False}


_dedupe.check_duplicate = _check_duplicate
sys.modules["sagaward.report.dedupe"] = _dedupe


class _Ctx:
    """The minimal run-context shape the report tool reads."""

    def __init__(self) -> None:
        self.context: dict[str, Any] = {}


def _args(**overrides: Any) -> str:
    payload: dict[str, Any] = {
        "title": "SQL injection in /api/users",
        "description": "The login parameter is concatenated into the query.",
        "impact": "An attacker reads arbitrary rows.",
        "target": "https://example.test",
        "technical_analysis": "Unparameterised query at the handler.",
        "poc_description": "Send a quote in the login field.",
        "poc_script_code": "requests.post(url, data={'user': \"' OR 1=1--\"})",
        "remediation_steps": "Use a parameterised query.",
        "cvss_breakdown": {
            "attack_vector": "N",
            "attack_complexity": "L",
            "privileges_required": "N",
            "user_interaction": "N",
            "scope": "U",
            "confidentiality": "H",
            "integrity": "H",
            "availability": "H",
        },
    }
    payload.update(overrides)
    return json.dumps(payload)


@pytest.fixture
def state() -> ReportState:
    previous = get_global_report_state()
    fresh = ReportState(run_name="test-evidence-binding")
    set_global_report_state(fresh)
    yield fresh
    set_global_report_state(previous)


def _record_confirmed(state: ReportState, endpoint: str, evidence_class: str) -> str:
    record = state.funnel_log.start_proposal(
        engagement_id=state.run_id,
        endpoint_key=endpoint,
        harnesses_selected=["p2_diff_harness"],
    )
    state.funnel_log.record_harness_verdict(
        record.proposal_id,
        "p2_diff_harness",
        "confirmed",
        evidence_class,  # type: ignore[arg-type]
    )
    return record.proposal_id


class TestResolveEvidenceClass:
    def test_confirmed_verdict_corroborates_the_claim(self, state: ReportState) -> None:
        _record_confirmed(state, "https://example.test/api/users", "diff")
        effective, note = state.resolve_evidence_class(
            "diff", endpoint="https://example.test/api/users"
        )
        assert effective == "diff"
        assert note is None

    def test_claim_without_a_verdict_resolves_to_none(self, state: ReportState) -> None:
        effective, note = state.resolve_evidence_class(
            "diff", endpoint="https://example.test/api/users"
        )
        assert effective == "none"
        assert note is not None

    def test_claim_cannot_exceed_the_recorded_verdict(self, state: ReportState) -> None:
        _record_confirmed(state, "https://example.test/api/users", "diff")
        effective, note = state.resolve_evidence_class(
            "callback", endpoint="https://example.test/api/users"
        )
        assert effective == "diff"
        assert note is not None and "callback" in note

    def test_unconfirmed_verdict_does_not_corroborate(self, state: ReportState) -> None:
        record = state.funnel_log.start_proposal(
            engagement_id=state.run_id,
            endpoint_key="https://example.test/api/users",
        )
        state.funnel_log.record_harness_verdict(
            record.proposal_id, "p2_diff_harness", "unconfirmed", "none"
        )
        effective, note = state.resolve_evidence_class(
            "diff", endpoint="https://example.test/api/users"
        )
        assert effective == "none"
        assert note is not None

    def test_proposal_id_wins_over_endpoint(self, state: ReportState) -> None:
        proposal_id = _record_confirmed(state, "https://example.test/api/users", "diff")
        effective, note = state.resolve_evidence_class(
            "diff", endpoint="https://elsewhere.test", proposal_id=proposal_id
        )
        assert effective == "diff"
        assert note is None


class TestReportToolBinding:
    def test_forged_claim_is_filed_as_none(self, state: ReportState) -> None:
        from sagaward.tools.reporting.tool import create_vulnerability_report

        result = json.loads(
            asyncio.run(
                create_vulnerability_report(
                    _Ctx(),
                    **json.loads(
                        _args(evidence_class="diff", endpoint="https://example.test/api/users")
                    ),
                )
            )
        )
        assert result["success"] is True
        assert result["evidence_class"] == "none"
        assert result["severity"] == "info"
        assert "evidence_note" in result
        assert state.vulnerability_reports[-1]["evidence_class"] == "none"

    def test_recorded_verdict_backs_the_claim(self, state: ReportState) -> None:
        from sagaward.tools.reporting.tool import create_vulnerability_report

        _record_confirmed(state, "https://example.test/api/users", "diff")
        result = json.loads(
            asyncio.run(
                create_vulnerability_report(
                    _Ctx(),
                    **json.loads(
                        _args(evidence_class="diff", endpoint="https://example.test/api/users")
                    ),
                )
            )
        )
        assert result["success"] is True
        assert result["evidence_class"] == "diff"
        assert result["severity"] == "high"
        assert "evidence_note" not in result
