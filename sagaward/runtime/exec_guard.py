"""The live enforcement point: every proposed execution passes the gate first.

``classify`` → ``decide_action`` run in the host process, before the container
execs. A DENY returns a **tool-surface refusal** naming the rule and nothing
reaches the container; an ALLOW proceeds exactly as before (exec, then the
provenance reconcilers). A gate failure refuses — the same fail-closed direction
as the observation channel — and repeated failures escalate.

**Which filesystem the classifier reads (S-5).** The decision is made in the
host process, but the filesystem it reads is the *container's*. ``classify``
takes a path resolver; when the run carries a sandbox session, ``authorize``
runs the classification twice:

1. a collecting pass records every path spelling the classifier asks about;
2. the observation channel resolves that set **inside the container** (one
   argv-form ``observation_exec``, ``runtime/container_paths.py``);
3. the deciding pass runs over the container's answers.

So a path that exists only in the container resolves to the container's inode
and classifies correctly, and a path that exists on the host but not in the
container is ``UNRESOLVED`` — the refusing shape — rather than silently read
through the host's inode. When no session is attached (unit tests, no
container), the host view is the fallback and is named as such in the audit.

**The honest limitation.** The fence verifies what the container's filesystem
*spells* — the resolved path and its inode — not what its *bytes* contain. A
path can resolve to the container's inode and still hold bytes the ledger never
saw. The gap-ledger row for content verification stands; this fix closes the
resolution gap, not the content gap.

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

from sagaward.core.provenance.classify import (
    CollectingPathResolver,
    UnresolvedPathResolver,
    classify,
)
from sagaward.core.provenance.gate import (
    Action,
    ActionDecision,
    ActionKind,
    ReasonCode,
    decide_action,
)
from sagaward.runtime.container_paths import (
    container_path_resolver,
    resolve_paths_in_container,
)
from sagaward.runtime.provenance_install import install_trigger, snapshot_install_prefixes
from sagaward.runtime.provenance_reconcile import reconcile_after_exec


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


def stdin_command_text(raw_input: str) -> tuple[str | None, str | None]:
    """``(chars, None)`` or ``(None, skip_class)`` for a ``write_stdin`` payload.

    ``write_stdin`` feeds a string to a running shell's stdin; that string is a
    command in exactly the sense ``exec_command``'s ``command`` is. The payload
    shape differs (``chars``, not ``command``), so it gets its own reader but the
    same skip classes and the same authorize path (S-3).
    """
    try:
        parsed = json.loads(raw_input)
    except json.JSONDecodeError:
        return None, "non_json"
    if not isinstance(parsed, dict):
        return None, "not_object"
    chars = parsed.get("chars")
    if chars is None:
        return None, "missing_chars"
    if not isinstance(chars, str):
        return None, "non_string_chars"
    return chars, None


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
        from sagaward.report.state import get_global_report_state  # noqa: PLC0415

        report_state = get_global_report_state()
        if report_state is not None:
            report_state.record_harness_run(
                harness_name=GATE_HARNESS,
                verdict="unconfirmed",
                evidence_class="none",
            )
    except Exception:
        logger.debug("apf_gate audit emit failed", exc_info=True)


def _emit_gate_audit(
    action: Action, decision: ActionDecision, *, rule: str, resolver: str = "host"
) -> None:
    """One audit line with the A7 detail, plus the emit-only funnel record."""
    detail = {
        "command": action.command,
        "targets": target_spellings(action),
        "degraded": decision.degraded,
        "reason": decision.reason.value,
        # S-5: which filesystem the decision read. "container" is the subject's
        # view; "host" is the no-session fallback and is named, never implied.
        "resolver": resolver,
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


async def _classify_in_subject_view(
    context: dict[str, Any], command: str, cwd: str | None
) -> tuple[Action, str]:
    """Classify over the container's view when a session is attached (S-5).

    Two passes: the collecting pass records every path the classifier asks
    about, the observation channel resolves that set inside the container, and
    the deciding pass runs over the answers. Without a session there is no
    container to ask, so the host view is the fallback — returned as ``"host"``
    so the audit names it.
    """
    session = context.get("sandbox_session")
    workdir = Path(cwd) if cwd else None
    if session is None:
        return classify(command, workdir), "host"
    collector = CollectingPathResolver()
    classify(command, workdir, resolver=collector)
    probes = await resolve_paths_in_container(session, collector.requests)
    if probes is None:
        # The container could not be asked: every path is the refusing shape.
        return classify(command, workdir, resolver=UnresolvedPathResolver()), "container-unobserved"
    return classify(command, workdir, resolver=container_path_resolver(probes)), "container"


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
        action, resolver_mode = await _classify_in_subject_view(context, command, cwd)
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
    _emit_gate_audit(action, decision, rule=rule, resolver=resolver_mode)
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
    except Exception:
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


async def guarded_stdin_invoke(
    ctx: Any,
    raw_input: str,
    invoke: Callable[[], Awaitable[Any]],
    *,
    tool_name: str = "write_stdin",
) -> Any:
    """Authorize a stdin payload, then write it (S-3).

    The write_stdin payloads are commands: they are fed to a running shell's
    stdin. They pass through the same ``command_or_skip`` skip classes and the
    same ``authorize`` decision as the exec payloads, so a tainted command cannot
    reach the shell through the stdin door. A denied payload returns the refusal
    before anything is written.
    """
    chars, skip = stdin_command_text(raw_input)
    if chars is not None:
        outcome = await authorize(ctx, chars, exec_workdir(raw_input))
        if not outcome.allowed:
            logger.info("%s refused by %s", tool_name, outcome.rule)
            return outcome.refusal
    elif skip is not None:
        # Undecidable payload: the pass is recorded, not silent (round 25, B3).
        _emit_skip_audit(skip, raw_input)
    return await invoke()


__all__ = [
    "GATE_FAILURE_LIMIT",
    "GateOutcome",
    "authorize",
    "exec_command_text",
    "exec_workdir",
    "guarded_invoke",
    "guarded_stdin_invoke",
    "rule_id",
    "stdin_command_text",
    "target_spellings",
]
