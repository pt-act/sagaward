"""Property-based tests for the action gate's decision core (AG1-AG4, zero-tolerance)."""

from __future__ import annotations

from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from strix.core.provenance.artifact import ArtifactRef
from strix.core.provenance.gate import (
    Action,
    ActionDecision,
    ActionKind,
    ArtifactSource,
    Resolution,
    ResolvedTarget,
    SourceKind,
    SourceShape,
    decide_action,
)
from strix.core.provenance.ledger import ProvenanceLedger
from strix.core.provenance.model import ProvenanceEnvelope, Source


TXNS = settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])

CLEAN = ProvenanceEnvelope(sources=frozenset({Source.SANDBOX_IMAGE}))
TAINTED = ProvenanceEnvelope(sources=frozenset({Source.ENGAGEMENT_SURFACE}))
DECLARED = {k.value for k in ActionKind}

# Declared kinds sampled both as enum members and as raw strings: the spec examples
# write kind="execute", so the gate must treat both forms identically.
known_kinds = st.sampled_from([*ActionKind, *(k.value for k in ActionKind)])
# Including the empty string, case variants, and near-misses of real kinds.
unknown_kinds = st.text(max_size=20).filter(lambda s: s not in DECLARED)
paths = st.sampled_from(["/usr/bin/tool", "/workspace/scratch/x", "/workspace/quarantine/q"])
envelopes = st.sampled_from([CLEAN, TAINTED])


def _ref(raw: str, inode: tuple[int, int] | None) -> ArtifactRef:
    return ArtifactRef(raw=raw, path_key=raw, inode_key=inode)


@st.composite
def targets(draw: st.DrawFn) -> ResolvedTarget:
    if draw(st.booleans()):
        return ResolvedTarget(raw="payload", path=None, resolution=Resolution.UNRESOLVED, ref=None)
    raw = draw(paths)
    return ResolvedTarget(
        raw=raw,
        path=Path(raw),
        resolution=Resolution.PATH,
        ref=_ref(raw, (1, 2)),
    )


@st.composite
def ledger(draw: st.DrawFn, tgt: ResolvedTarget | None) -> ProvenanceLedger:
    ledger = ProvenanceLedger()
    if tgt is not None and tgt.ref is not None:
        ledger.record_key(Path(tgt.ref.path_key), draw(envelopes))
    return ledger


# AG1 — fail-closed kinds


@given(kind=unknown_kinds)
@TXNS
def test_ag1_unknown_kind_denies(kind: str) -> None:
    decision = decide_action(Action(kind=kind, command="x"), ProvenanceLedger())
    assert decision.verdict == "DENY"


# AG2 — quarantine soundness


@given(
    kind=known_kinds.filter(lambda k: ActionKind(k) in {ActionKind.EXECUTE, ActionKind.CHMOD_EXEC}),
    tgt=targets(),
    orphan=ledger(None),
)
@TXNS
def test_ag2_quarantine_reference_denies_exec_kinds(
    kind: ActionKind | str, tgt: ResolvedTarget, orphan: ProvenanceLedger
) -> None:
    decision = decide_action(
        Action(
            kind=kind,
            command="x",
            targets=(tgt,),
            references_quarantine=True,
            executes_quarantine=True,
        ),
        orphan,
    )
    assert decision.verdict == "DENY"


# AG3 — miss soundness


@given(tgt=targets(), execute_kind=st.sampled_from([ActionKind.EXECUTE, "execute"]))
@TXNS
def test_ag3_resolved_execute_miss_denies(
    tgt: ResolvedTarget, execute_kind: ActionKind | str
) -> None:
    decision = decide_action(
        Action(kind=execute_kind, command="x", targets=(tgt,)), ProvenanceLedger()
    )
    if tgt.resolution is Resolution.PATH:
        assert decision.verdict == "DENY"
        assert decision.reason.value == "provenance_miss"
    else:
        assert decision.verdict == "ALLOW"


# AG4 — purity / determinism


@given(
    kind=known_kinds,
    tgt=targets(),
    references_quarantine=st.booleans(),
    executes_quarantine=st.booleans(),
    operator_approved=st.booleans(),
    scripts_disabled=st.booleans(),
)
@TXNS
def test_ag4_two_calls_equal(
    kind: ActionKind | str,
    tgt: ResolvedTarget,
    references_quarantine: bool,
    executes_quarantine: bool,
    operator_approved: bool,
    scripts_disabled: bool,
) -> None:
    src = ArtifactSource(
        raw="pkg", kind=SourceKind.OFFICIAL_INDEX, shape=SourceShape.WHEEL, target=None
    )
    act = Action(
        kind=kind,
        command="x",
        targets=(tgt,),
        artifact_sources=(src,),
        references_quarantine=references_quarantine,
        executes_quarantine=executes_quarantine,
        operator_approved=operator_approved,
        scripts_disabled=scripts_disabled,
    )
    led = ProvenanceLedger()
    first = decide_action(act, led)
    second = decide_action(act, led)
    assert isinstance(first, ActionDecision)
    assert first == second
