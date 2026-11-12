"""The live enforcement point: every proposed execution passes the gate first.

``classify`` → ``decide_action`` run in the host process, before the container
execs. A DENY returns a **tool-surface refusal** naming the rule and nothing
reaches the container; an ALLOW proceeds exactly as before (exec, then the
provenance reconcilers). A gate failure refuses — the same fail-closed direction
as the observation channel — and repeated failures escalate.

The decision runs in the host process with no interpreter shared with the
subject: the same posture the observation channel carries, applied one layer up.

This module deliberately imports nothing from the agents SDK so the enforcement
sequence is testable without one; ``agents/factory.py`` is the thin adapter.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from oriontrix.core.provenance.classify import classify
from oriontrix.core.provenance.gate import (
    Action,
    ActionDecision,
    ActionKind,
    ReasonCode,
    decide_action,
)
from oriontrix.runtime.provenance_install import install_trigger, snapshot_install_prefixes
from oriontrix.runtime.provenance_reconcile import reconcile_after_exec


if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

GATE_FAILURE_LIMIT = 3
GATE_HARNESS = "apf_action_gate"

# The rule id a refusal names. ``ActionDecision`` carries the reason; the rule is
# a function of (reason, kind), because PROVENANCE_MISS is shared by R3/R4'/R5'/R6'.
_RULE_BY_REASON: dict[ReasonCode, str] = {
    ReasonCode.QUARANTINE_REFERENCE: "R1",
    ReasonCode.TAINTED_EXECUTABLE: "R2",
    ReasonCode.UNTREATED_INTERPRETER_INPUT: "R3.8",
    ReasonCode.UNRESOLVED_QUARANTINE_REF: "R3.5",
    ReasonCode.TAINTED_CHMOD: "R4",
    ReasonCode.TAINTED_PACKAGE_SOURCE: "R5",
    ReasonCode.UNSAFE_INSTALL_SOURCE: "R5\u2033",
    ReasonCode.UNSAFE_INSTALL_FLAGS: "R5\u2033\u2033",
    ReasonCode.TAINTED_HOST_WRITE: "R6",
    ReasonCode.UNKNOWN_ACTION_KIND: "R7",
}
_MISS_RULE_BY_KIND: dict[str, str] = {
    ActionKind.EXECUTE: "R3",
    ActionKind.CHMOD_EXEC: "R4'",
    ActionKind.PACKAGE_INSTALL: "R5'",
    ActionKind.WRITE_HOST_MOUNT: "R6'",
}


def command_or_skip(raw_input: str) -> tuple[str | None, str | None]:
    """``(command, None)`` or ``(None, skip_class)``.

    The skip classes are the payload shapes the gate cannot decide: non-JSON, a
    non-object, a missing ``command`` key, and a non-string ``command``. They are
    named so the audit line can say *which* shape passed undecided instead of
    silently proceeding (round 25's B3).
    """
    try:
        parsed = json.loads(raw_input)
    except json.JSONDecodeError:
        return None, "non_json"
    if not isinstance(parsed, dict):
        return None, "not_object"
    command = parsed.get("command")
    if command is None:
        return None, "missing_command"
    if not isinstance(command, str):
        return None, "non_string_command"
    return command, None


def exec_command_text(raw_input: str) -> str | None:
    """The command string from the tool call, or ``None`` when it cannot be read."""
    return command_or_skip(raw_input)[0]


def exec_workdir(raw_input: str) -> str | None:
    """The call's ``workdir``, when it names one (the base for relative operands)."""
    try:
        parsed = json.loads(raw_input)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    workdir = parsed.get("workdir")
    return workdir if isinstance(workdir, str) and workdir else None


def rule_id(action: Action, decision: ActionDecision) -> str:
    """The rule row this decision came from (the refusal names it)."""
    if decision.reason is ReasonCode.PROVENANCE_MISS:
        return _MISS_RULE_BY_KIND.get(str(action.kind), "R3")
    if decision.reason is ReasonCode.ALLOWED:
        return "R8" if decision.degraded else "R9"
    return _RULE_BY_REASON.get(decision.reason, "R7")


def target_spellings(action: Action) -> list[str]:
    """The A7 detail: every target's raw spelling and its resolved path.

    A degraded record that carried only a count would hide the construct; the
    contract is that the trace shows the command text and the spellings it
    resolved (or failed to resolve) to.
    """
    seen: list[str] = []
    stack = [action]
    while stack:
        node = stack.pop(0)
        for target in (*node.targets, *node.interpreter_input):
            raw = str(target.raw)
            resolved = str(target.path) if target.path is not None else "UNRESOLVED"
            entry = f"{raw} => {resolved}"
            if entry not in seen:
                seen.append(entry)
        stack.extend(node.members)
    return seen


def _emit_funnel() -> None:
    """The emit-only funnel record; it can never change a verdict."""
    try:
        from oriontrix.report.state import get_global_report_state  # noqa: PLC0415

        report_state = get_global_report_state()
        if report_state is not None:
            report_state.record_harness_run(
                harness_name=GATE_HARNESS,
                verdict="unconfirmed",
                evidence_class="none",
            )
    except Exception:  # noqa: BLE001 - audit must never change a verdict
        logger.debug("apf_gate audit emit failed", exc_info=True)


def _emit_gate_audit(action: Action, decision: ActionDecision, *, rule: str) -> None:
    """One audit line with the A7 detail, plus the emit-only funnel record."""
    detail = {
        "command": action.command,
        "targets": target_spellings(action),
        "degraded": decision.degraded,
        "reason": decision.reason.value,
    }
    if decision.verdict == "DENY":
        logger.warning(
            "apf_gate DENY %s (%s) detail=%s",
            rule,
            decision.reason.value,
            json.dumps(detail),
        )
    else:
        logger.info(
            "apf_gate ALLOW %s degraded=%s detail=%s",
            rule,
            decision.degraded,
            json.dumps(detail),
        )
    _emit_funnel()


def _emit_skip_audit(skip: str, raw_input: str) -> None:
    """A payload the gate could not read still leaves a trace of the pass (B3).

    The decision is *skipped*, not refused: refusing a payload the SDK may
    legitimately shape would be over-reach measured in guesses. What must not
    happen is silence, so the A7 record names the skip class and the payload
    prefix.
    """
    detail = {"command": None, "skip": skip, "payload_prefix": raw_input[:200]}
    logger.warning(
        "apf_gate SKIP %s (payload passed undecided) detail=%s", skip, json.dumps(detail)
    )
    _emit_funnel()


@dataclass(frozen=True, slots=True)
class GateOutcome:
    """What the enforcement point decided for one proposed execution."""

    allowed: bool
    rule: str
    reason: ReasonCode | None
    degraded: bool = False
    refusal: str | None = None


def _refusal(rule: str, detail: str) -> str:
    return f"apf-action-gate: DENY {rule} — the command was not executed. {detail}"


def _gate_state(context: dict[str, Any]) -> dict[str, Any]:
    state = context.get("apf_gate")
    if not isinstance(state, dict):
        state = {"consecutive_failures": 0, "allowed": 0, "denied": 0}
        context["apf_gate"] = state
    return state


async def authorize(ctx: Any, command: str, cwd: str | None = None) -> GateOutcome:
    """Decide one command. Never raises: a failure of the gate is a refusal."""
    context = getattr(ctx, "context", None)
    if not isinstance(context, dict):
        return GateOutcome(
            allowed=False,
            rule="gate_unavailable",
            reason=None,
            refusal=_refusal("gate_unavailable", "the run context is not a mapping."),
        )
    ledger = context.get("provenance")
    state = _gate_state(context)
    if ledger is None:
        failures = int(state.get("consecutive_failures", 0)) + 1
        state["consecutive_failures"] = failures
        await _escalate(context, failures)
        return GateOutcome(
            allowed=False,
            rule="gate_unavailable",
            reason=None,
            refusal=_refusal(
                "gate_unavailable",
                "no provenance ledger is attached to this run; refusing rather than "
                "executing undecided.",
            ),
        )
    try:
        action = classify(command, Path(cwd) if cwd else None)
        decision = decide_action(action, ledger)
    except Exception as exc:  # noqa: BLE001 - gate failure must refuse, not raise
        failures = int(state.get("consecutive_failures", 0)) + 1
        state["consecutive_failures"] = failures
        logger.critical("apf_gate decision failed (%d consecutive): %s", failures, exc)
        await _escalate(context, failures)
        return GateOutcome(
            allowed=False,
            rule="gate_unavailable",
            reason=None,
            refusal=_refusal(
                "gate_unavailable",
                "the decision layer failed; refusing rather than executing undecided.",
            ),
        )
    rule = rule_id(action, decision)
    _emit_gate_audit(action, decision, rule=rule)
    if decision.verdict == "DENY":
        state["consecutive_failures"] = 0
        state["denied"] = int(state.get("denied", 0)) + 1
        return GateOutcome(
            allowed=False,
            rule=rule,
            reason=decision.reason,
            degraded=decision.degraded,
            refusal=_refusal(rule, f"reason={decision.reason.value}."),
        )
    state["consecutive_failures"] = 0
    state["allowed"] = int(state.get("allowed", 0)) + 1
    return GateOutcome(allowed=True, rule=rule, reason=decision.reason, degraded=decision.degraded)


async def _escalate(context: dict[str, Any], failures: int) -> None:
    if failures < GATE_FAILURE_LIMIT:
        return
    coordinator = context.get("coordinator")
    reason = (
        "apf-action-gate: the decision layer failed "
        f"{failures} consecutive times; refusing to continue undecided"
    )
    logger.critical(reason)
    if coordinator is None:
        return
    try:
        await coordinator.kill_switch(reason)
    except Exception:  # noqa: BLE001 - escalation must never raise into the tool
        logger.debug("apf_gate escalation failed", exc_info=True)


async def guarded_invoke(
    ctx: Any,
    raw_input: str,
    invoke: Callable[[], Awaitable[Any]],
    *,
    tool_name: str = "exec_command",
) -> Any:
    """Authorize, exec, then reconcile — in that order.

    A denied action returns the refusal **before** any observation traffic: no
    install snapshot, no reconcile, no container exec. An allowed action runs the
    existing sequence unchanged.
    """
    command, skip = command_or_skip(raw_input)
    if command is not None:
        outcome = await authorize(ctx, command, exec_workdir(raw_input))
        if not outcome.allowed:
            logger.info("%s refused by %s", tool_name, outcome.rule)
            return outcome.refusal
    elif skip is not None:
        # Undecidable payload: the pass is recorded, not silent (round 25, B3).
        _emit_skip_audit(skip, raw_input)

    started_ns = time.time_ns()
    trigger = install_trigger(command) if command is not None else None
    snapshot = None
    if trigger is not None:
        context = getattr(ctx, "context", None)
        session = context.get("sandbox_session") if isinstance(context, dict) else None
        if session is not None:
            snapshot = await snapshot_install_prefixes(session, trigger)
    result = await invoke()
    await reconcile_after_exec(
        ctx,
        command=command,
        started_ns=started_ns,
        trigger=trigger,
        install_snapshot=snapshot,
        observed_at_ns=time.time_ns(),
    )
    return result


__all__ = [
    "GATE_FAILURE_LIMIT",
    "GateOutcome",
    "authorize",
    "exec_command_text",
    "exec_workdir",
    "guarded_invoke",
    "rule_id",
    "target_spellings",
]
