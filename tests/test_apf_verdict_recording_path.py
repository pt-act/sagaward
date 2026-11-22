"""S-1's audit — the verdict's recording path.

The binding (S-1) makes ``evidence_class`` a function of the funnel's recorded verdicts. This
audit pins the path that records them — the agent's proposal, the harness's confirmation, the
verdict's recording, and the evidence class's binding — and the trust boundary between the
agent's control and the harness's determinism.

The cells:

1. the proposal stage carries no ``evidence_class`` and starts with zero verdicts;
2. the confirmation input is the harness's return, not the agent's arguments;
3. the emit wrapper reads only the return and passes it through unchanged;
4. the verdict's recording has exactly three call sites, none of them a tool;
5. the binding reads the funnel, not the claim;
6. end-to-end: the agent's control attempts do not change the verdict;
7. the report path is link-only — filing a report writes no verdict;
8. the confirmation predicates are pure (model-independent).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


# The agents SDK is not installed in the test venv; stub the two seams the report
# layer touches (same pattern as tests/test_apf_evidence_binding.py).
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

from sagaward.agents.funnel_emit import emit_harness_run, wrap_harness_tool  # noqa: E402
from sagaward.core.diff.engine import diff  # noqa: E402
from sagaward.core.proposals.models import ProposalRecord  # noqa: E402
from sagaward.core.race.verdict import verdict as race_verdict  # noqa: E402
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
_PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "sagaward"


class _Ctx:
    """The minimal run-context shape the report tool reads."""

    def __init__(self) -> None:
        self.context: dict[str, Any] = {}


class _FakeFunctionTool:
    """Minimal stand-in for an agents SDK FunctionTool (``name`` + ``on_invoke_tool``)."""

    def __init__(self, name: str, returns: Any) -> None:
        self.name = name
        self._returns = returns

    async def on_invoke_tool(self, _ctx: Any, _args_json: str) -> Any:
        return self._returns


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
    fresh = ReportState(run_name="test-verdict-recording-path")
    set_global_report_state(fresh)
    yield fresh
    set_global_report_state(previous)


def _propose(state: ReportState, *, endpoint_key: str = _ENDPOINT) -> str:
    """Stage 0: the agent's proposal, with the content the agent controls."""
    return state.funnel_log.start_proposal(
        engagement_id=state.run_id,
        endpoint_key=endpoint_key,
        param_name="src",
        cwe="CWE-918",
        harnesses_selected=["p3_oob_harness"],
    ).proposal_id


def _file(**overrides: Any) -> dict[str, Any]:
    return json.loads(
        asyncio.run(create_vulnerability_report(_Ctx(), **json.loads(_args(**overrides))))
    )


class TestThePathStages:
    def test_stage_0_the_proposal_carries_no_evidence_class(self, state: ReportState) -> None:
        """The proposal stage cannot express a disposition: no field, no verdict."""
        assert "evidence_class" not in ProposalRecord.model_fields
        proposal_id = _propose(state)
        record = state.funnel_log.get(proposal_id)
        assert record is not None
        assert record.verdicts == []
        assert record.report_id is None

    def test_stage_2_the_confirmation_input_is_the_harness_return(self, state: ReportState) -> None:
        """An ``evidence_class`` in the agent's tool arguments is ignored.

        The wrapper derives the verdict from the harness's return value only; the agent's
        arguments cannot name a confirmation.
        """
        proposal_id = _propose(state)
        emit_harness_run(
            "p3_oob_harness",
            {"verdict": "unconfirmed"},  # the harness observed no callback
            json.dumps(
                {
                    "endpoint": _ENDPOINT,
                    "proposal_id": proposal_id,
                    "evidence_class": "callback",  # the agent's attempt
                }
            ),
        )
        record = state.funnel_log.get(proposal_id)
        assert record is not None
        assert len(record.verdicts) == 1
        assert record.verdicts[0].verdict == "unconfirmed"
        assert record.verdicts[0].evidence_class == "none"

    def test_stage_3_the_wrapper_reads_only_the_return_and_passes_it_through(
        self, state: ReportState
    ) -> None:
        """The trust boundary: args in, return out, the return unchanged."""
        _propose(state)
        payload = {"verdict": "confirmed", "report": {"evidence_class": "callback"}}
        tool = _FakeFunctionTool("report_oob_confirmed_candidate", payload)
        wrapped = wrap_harness_tool(tool, default_harness="p3_oob_harness")
        args = json.dumps({"endpoint": _ENDPOINT})
        out = asyncio.run(wrapped.on_invoke_tool(None, args))
        assert out == payload  # behavior-identical
        record = state.funnel_log.list_records()[0]
        assert record.verdicts[0].verdict == "confirmed"
        assert record.verdicts[0].evidence_class == "callback"

    def test_stage_3_the_recording_has_three_call_sites_none_a_tool(self) -> None:
        """The verdict's recording is driven by the wrapper and two runtime hooks.

        No agent-callable tool writes a verdict: the call sites are the emit wrapper and the
        two runtime hooks, and both hooks emit ``unconfirmed``/``none`` only.
        """
        call_sites: set[str] = set()
        for path in _PACKAGE_ROOT.rglob("*.py"):
            for line in path.read_text(encoding="utf-8").splitlines():
                if "record_harness_run(" in line and "def record_harness_run" not in line:
                    call_sites.add(str(path.relative_to(_PACKAGE_ROOT)))
        assert call_sites == {
            "agents/funnel_emit.py",
            "runtime/exec_guard.py",
            "runtime/provenance_reconcile.py",
        }

        for hook in ("runtime/exec_guard.py", "runtime/provenance_reconcile.py"):
            source = (_PACKAGE_ROOT / hook).read_text(encoding="utf-8")
            start = source.index("record_harness_run(")
            block = source[start : start + 240]
            assert 'verdict="unconfirmed"' in block
            assert 'evidence_class="none"' in block

    def test_stage_4_the_binding_reads_the_funnel_not_the_claim(self, state: ReportState) -> None:
        proposal_id = _propose(state)
        state.funnel_log.record_harness_verdict(proposal_id, "p2_diff_harness", "confirmed", "diff")
        binding = state.resolve_evidence_class(
            "callback", endpoint=_ENDPOINT, proposal_id=proposal_id
        )
        assert binding.evidence_class == "diff"
        assert binding.note is not None and "callback" in binding.note
        assert binding.proposal_id == proposal_id

        binding = state.resolve_evidence_class(
            "callback", endpoint="GET /unrelated", proposal_id=None
        )
        assert binding.evidence_class == "none"
        assert binding.note is not None


class TestTheAgentCannotChangeTheVerdict:
    def test_end_to_end_the_verdict_changes_only_when_the_harness_records_one(
        self, state: ReportState
    ) -> None:
        """The agent's control attempts leave the verdict unchanged.

        The agent proposes (content it controls), then claims ``callback``. With no recorded
        verdict the claim is filed as ``none``/``info``. Only after a confirmed harness run is
        recorded does the same claim resolve to the harness's class.
        """
        proposal_id = _propose(state)

        forged = _file(evidence_class="callback", endpoint=_ENDPOINT)
        assert forged["success"] is True
        assert forged["evidence_class"] == "none"
        assert forged["severity"] == "info"
        assert "evidence_note" in forged
        assert state.vulnerability_reports[-1]["evidence_class"] == "none"

        # The harness confirms — the only event that can raise the class.
        emit_harness_run(
            "p2_diff_harness",
            {"verdict": "confirmed", "report": {"evidence_class": "diff"}},
            json.dumps({"endpoint": _ENDPOINT, "proposal_id": proposal_id}),
        )

        corroborated = _file(evidence_class="diff", endpoint=_ENDPOINT)
        assert corroborated["evidence_class"] == "diff"
        assert corroborated["severity"] == "high"
        assert "evidence_note" not in corroborated

        record = state.funnel_log.get(proposal_id)
        assert record is not None
        assert [(v.verdict, v.evidence_class) for v in record.verdicts] == [("confirmed", "diff")]

    def test_the_report_path_is_link_only(self, state: ReportState) -> None:
        """Filing a report writes no verdict — the report path only links the report id."""
        proposal_id = _propose(state)
        state.funnel_log.record_harness_verdict(proposal_id, "p2_diff_harness", "confirmed", "diff")
        before = [(v.verdict, v.evidence_class) for v in state.funnel_log.get(proposal_id).verdicts]  # type: ignore[union-attr]

        _file(evidence_class="diff", endpoint=_ENDPOINT)

        after = [(v.verdict, v.evidence_class) for v in state.funnel_log.get(proposal_id).verdicts]  # type: ignore[union-attr]
        assert after == before

    def test_the_binding_rejects_a_borrowed_match_key(self, state: ReportState) -> None:
        """Residual 1, fixed: the match key is verified, not trusted.

        A report citing another finding's ``proposal_id`` no longer borrows that finding's
        confirmed class: the cited proposal's ``endpoint_key`` must equal the report's
        endpoint. The mismatched citation resolves to ``none`` and the impact gate files
        the finding as ``info``.
        """
        confirmed = _propose(state, endpoint_key="POST /api/v1/other")
        state.funnel_log.record_harness_verdict(confirmed, "p2_diff_harness", "confirmed", "diff")
        result = _file(evidence_class="diff", endpoint=_ENDPOINT, proposal_id=confirmed)
        assert result["evidence_class"] == "none"
        assert result["severity"] == "info"
        assert "evidence_note" in result
        assert "proposal_id" not in state.vulnerability_reports[-1]


class TestThePredicatesArePure:
    def test_the_race_verdict_is_a_function_of_the_commit_count(self) -> None:
        assert race_verdict(None, 2) == "race"  # type: ignore[arg-type]
        assert race_verdict(None, 1) == "safe"  # type: ignore[arg-type]
        assert race_verdict(None, 0) == "inconclusive"  # type: ignore[arg-type]

    def test_the_diff_candidates_are_a_function_of_the_responses(self) -> None:
        responses = [
            {"label": "user", "response": {"status_code": 200, "headers": {}, "body": "{}"}},
            {"label": "admin", "response": {"status_code": 200, "headers": {}, "body": "{}"}},
        ]
        first = diff(responses)
        second = diff(responses)
        assert [c.model_dump() for c in first.candidates] == [
            c.model_dump() for c in second.candidates
        ]
        assert [c.evidence_class for c in first.candidates] == ["diff"]
