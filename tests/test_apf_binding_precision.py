"""S-1's residuals 1-3 — the binding's match key, the join's precision, the match's tightening.

Residual 1 (fixed): ``resolve_evidence_class`` trusted the agent-supplied
``proposal_id``/``endpoint``, so a report could borrow another finding's confirmed class.
The fix requires the cited proposal's ``endpoint_key`` to equal the report's endpoint and
records the matched ``proposal_id`` on the report.

Residual 2 (fixed): the emit wrapper correlated by an endpoint extracted from the harness's
arguments (``target_key``/``request_id``), which need not equal the proposal's
``endpoint_key``. The fix extracts only endpoint-key-shaped arguments, so the join matches
the proposal's key.

Residual 3 (fixed): the endpoint match was a loose substring test. The fix is the exact
match or a prefix match on a separator boundary.

Residual 4 (by design, named): the harness's own report path bypasses the binding — the
guarantee is "the agent cannot forge a verdict", not "every report is bound".
"""

from __future__ import annotations

import asyncio
import json
import sys
from types import ModuleType
from typing import Any

import pytest


# The agents SDK is not installed in the test venv; stub the two seams the report
# layer touches (same pattern as tests/test_apf_verdict_recording_path.py).
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

from sagaward.agents.funnel_emit import emit_harness_run  # noqa: E402
from sagaward.report.state import (  # noqa: E402
    ReportState,
    get_global_report_state,
    set_global_report_state,
)
from sagaward.tools.reporting.tool import create_vulnerability_report  # noqa: E402


# The report tool imports ``sagaward.report.dedupe`` lazily; stub it so the test does
# not pull the full agents model tree.
_dedupe: Any = ModuleType("sagaward.report.dedupe")


async def _check_duplicate(_candidate: Any, _existing: Any) -> dict[str, Any]:
    return {"is_duplicate": False}


_dedupe.check_duplicate = _check_duplicate
sys.modules["sagaward.report.dedupe"] = _dedupe


_ENDPOINT = "POST /api/v1/import"


class _Ctx:
    """The minimal run-context shape the report tool reads."""

    def __init__(self) -> None:
        self.context: dict[str, Any] = {}


def _args(**overrides: Any) -> str:
    payload: dict[str, Any] = {
        "title": "SSRF in the image importer",
        "description": "The importer fetches an attacker-controlled URL.",
        "impact": "An attacker reaches internal services.",
        "target": "https://example.test",
        "technical_analysis": "The URL is fetched without an allow-list.",
        "poc_description": "Submit an internal URL to the importer.",
        "poc_script_code": "requests.post(url, json={'src': 'http://169.254.169.254/'})",
        "remediation_steps": "Allow-list the fetch destinations.",
        "cvss_breakdown": {
            "attack_vector": "N",
            "attack_complexity": "L",
            "privileges_required": "N",
            "user_interaction": "N",
            "scope": "U",
            "confidentiality": "H",
            "integrity": "L",
            "availability": "N",
        },
    }
    payload.update(overrides)
    return json.dumps(payload)


@pytest.fixture
def state() -> ReportState:
    previous = get_global_report_state()
    fresh = ReportState(run_name="test-binding-precision")
    set_global_report_state(fresh)
    yield fresh
    set_global_report_state(previous)


def _propose(state: ReportState, *, endpoint_key: str = _ENDPOINT) -> str:
    return state.funnel_log.start_proposal(
        engagement_id=state.run_id,
        endpoint_key=endpoint_key,
        param_name="src",
        cwe="CWE-918",
        harnesses_selected=["p3_oob_harness"],
    ).proposal_id


def _confirm(state: ReportState, proposal_id: str, evidence_class: str = "diff") -> None:
    state.funnel_log.record_harness_verdict(
        proposal_id,
        "p2_diff_harness",
        "confirmed",
        evidence_class,  # type: ignore[arg-type]
    )


def _file(**overrides: Any) -> dict[str, Any]:
    return json.loads(
        asyncio.run(create_vulnerability_report(_Ctx(), **json.loads(_args(**overrides))))
    )


class TestTheMatchKeyIsVerified:
    """Residual 1: the cited proposal must be for the report's endpoint."""

    def test_a_borrowed_proposal_id_is_not_corroborated(self, state: ReportState) -> None:
        confirmed = _propose(state, endpoint_key="POST /api/v1/other")
        _confirm(state, confirmed)

        result = _file(evidence_class="diff", endpoint=_ENDPOINT, proposal_id=confirmed)

        assert result["evidence_class"] == "none"
        assert result["severity"] == "info"
        assert "evidence_note" in result
        assert "proposal_id" not in state.vulnerability_reports[-1]

    def test_the_matched_proposal_is_recorded_on_the_report(self, state: ReportState) -> None:
        proposal_id = _propose(state)
        _confirm(state, proposal_id)

        result = _file(evidence_class="diff", endpoint=_ENDPOINT, proposal_id=proposal_id)

        assert result["evidence_class"] == "diff"
        assert result["severity"] == "high"
        assert state.vulnerability_reports[-1]["proposal_id"] == proposal_id

    def test_a_report_without_an_endpoint_cannot_borrow(self, state: ReportState) -> None:
        proposal_id = _propose(state)
        _confirm(state, proposal_id)

        result = _file(evidence_class="diff", endpoint=None, proposal_id=proposal_id)

        assert result["evidence_class"] == "none"
        assert result["severity"] == "info"
        assert "evidence_note" in result
        assert "proposal_id" not in state.vulnerability_reports[-1]


class TestTheJoinIsPrecise:
    """Residual 2: the join extracts an endpoint key, not a host or a request id."""

    def test_a_host_argument_does_not_join_a_proposal(self, state: ReportState) -> None:
        proposal_id = _propose(state)

        emit_harness_run(
            "p2_diff_harness",
            {"verdict": "confirmed", "report": {"evidence_class": "diff"}},
            json.dumps({"target_key": "api.example.test"}),
        )

        record = state.funnel_log.get(proposal_id)
        assert record is not None
        assert record.verdicts == []
        # The confirmed run is still funnel-complete: it auto-registered a synthetic record.
        synthetic = [r for r in state.funnel_log.list_records() if r.proposal_id != proposal_id]
        assert len(synthetic) == 1
        assert synthetic[0].endpoint_key == "auto:p2_diff_harness"

    def test_a_request_id_argument_does_not_join_a_proposal(self, state: ReportState) -> None:
        proposal_id = _propose(state)

        emit_harness_run(
            "p2_diff_harness",
            {"verdict": "confirmed", "report": {"evidence_class": "diff"}},
            json.dumps({"request_id": "req-123", "target_key": "api.example.test"}),
        )

        record = state.funnel_log.get(proposal_id)
        assert record is not None
        assert record.verdicts == []

    def test_an_endpoint_key_argument_joins_exactly(self, state: ReportState) -> None:
        proposal_id = _propose(state)

        emit_harness_run(
            "p2_diff_harness",
            {"verdict": "confirmed", "report": {"evidence_class": "diff"}},
            json.dumps({"endpoint_key": _ENDPOINT}),
        )

        record = state.funnel_log.get(proposal_id)
        assert record is not None
        assert [(v.verdict, v.evidence_class) for v in record.verdicts] == [("confirmed", "diff")]
        assert len(state.funnel_log.list_records()) == 1


class TestTheMatchIsTightened:
    """Residual 3: exact, or a prefix on a separator boundary — never a bare substring."""

    def test_a_substring_is_not_a_match(self, state: ReportState) -> None:
        proposal_id = _propose(state)

        emit_harness_run(
            "p3_oob_harness",
            {"verdict": "unconfirmed"},
            json.dumps({"endpoint": "POST /api/v1/imports"}),
        )

        record = state.funnel_log.get(proposal_id)
        assert record is not None
        assert record.verdicts == []

    def test_a_bare_path_is_not_a_match(self, state: ReportState) -> None:
        proposal_id = _propose(state)

        emit_harness_run(
            "p3_oob_harness",
            {"verdict": "unconfirmed"},
            json.dumps({"endpoint": "/api/v1/import"}),
        )

        record = state.funnel_log.get(proposal_id)
        assert record is not None
        assert record.verdicts == []

    def test_a_separator_bounded_prefix_is_a_match(self, state: ReportState) -> None:
        proposal_id = _propose(state)

        emit_harness_run(
            "p3_oob_harness",
            {"verdict": "unconfirmed"},
            json.dumps({"endpoint": "POST /api/v1/import/123"}),
        )

        record = state.funnel_log.get(proposal_id)
        assert record is not None
        assert len(record.verdicts) == 1

    def test_the_link_uses_the_tightened_match(self, state: ReportState) -> None:
        proposal_id = _propose(state)

        # A substring of the key is not the key: no link.
        state.add_vulnerability_report(
            title="finding",
            severity="high",
            endpoint="POST /api/v1/imports",
            evidence_class="diff",
        )
        record = state.funnel_log.get(proposal_id)
        assert record is not None
        assert record.report_id is None

        # A separator-bounded prefix is the same endpoint: linked.
        report_id = state.add_vulnerability_report(
            title="finding",
            severity="high",
            endpoint="POST /api/v1/import/123",
            evidence_class="diff",
        )
        assert record.report_id == report_id
