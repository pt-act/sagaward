"""Business-logic state testing: agent-proposed models, deterministic tests, evidence gate."""

from __future__ import annotations

from oriontrix.core.logic.catalog import (
    describe_invariant,
    list_invariant_kinds,
    run_violation_test,
)
from oriontrix.core.logic.context import ExecutionContext, record_replay
from oriontrix.core.logic.gate import evaluate
from oriontrix.core.logic.models import (
    BusinessLogicModel,
    ConfirmedViolation,
    ExecutedSequence,
    ExecutedStep,
    FlowModel,
    InvariantKind,
    JourneyModel,
    LifecycleModel,
    MonetaryOperation,
    Step,
    Transition,
    TrustBoundary,
    UnconfirmedHypothesis,
    ViolationCandidate,
)
from oriontrix.core.logic.orchestrator import (
    BusinessLogicOrchestrator,
    RealExecutionContext,
)
from oriontrix.core.logic.store import BusinessLogicStore


__all__ = [
    "BusinessLogicModel",
    "BusinessLogicOrchestrator",
    "BusinessLogicStore",
    "ConfirmedViolation",
    "ExecutedSequence",
    "ExecutedStep",
    "ExecutionContext",
    "FlowModel",
    "InvariantKind",
    "JourneyModel",
    "LifecycleModel",
    "MonetaryOperation",
    "RealExecutionContext",
    "Step",
    "Transition",
    "TrustBoundary",
    "UnconfirmedHypothesis",
    "ViolationCandidate",
    "describe_invariant",
    "evaluate",
    "list_invariant_kinds",
    "record_replay",
    "run_violation_test",
]
