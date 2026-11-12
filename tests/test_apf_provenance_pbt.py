"""Property-based tests for apf-provenance (PR1-PR3, zero-tolerance).

A single counterexample blocks release. These target the two invariants that
make the ledger safe to gate on: taint never decreases, and a miss never
becomes a clean envelope.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from oriontrix.core.provenance import (
    Label,
    LedgerMiss,
    Principal,
    ProvenanceEnvelope,
    ProvenanceLedger,
    Source,
)


BASE = Path(tempfile.gettempdir()) / "apf-pbt"
TXNS = settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])

indices = st.integers(min_value=0, max_value=4)
labels = st.frozensets(st.sampled_from(list(Label)))
non_empty_sources = st.frozensets(
    st.sampled_from(list(Source)),
    min_size=1,
    max_size=len(Source),
)
envelopes = st.builds(ProvenanceEnvelope, sources=non_empty_sources, labels=labels)


def _path(index: int) -> Path:
    return BASE / f"artifact-{index}"


def _new_ledger() -> ProvenanceLedger:
    return ProvenanceLedger()


@given(chain=st.lists(indices, min_size=1, max_size=5), labels=labels)
@TXNS
def test_pr1_monotonicity_through_derivation(chain: list[int], labels: frozenset[Label]) -> None:
    """PR1 — a derivation chain of length 1..5 preserves taint at the leaf."""
    ledger = _new_ledger()
    origin = _path(chain[0])
    ledger.record(
        origin,
        ProvenanceEnvelope(sources=frozenset({Source.ENGAGEMENT_SURFACE}), labels=labels),
    )

    previous = origin
    for index in chain[1:]:
        current = _path(index)
        ledger.mark_derived(current, previous)
        previous = current

    leaf = ledger.lookup(previous)
    assert isinstance(leaf, ProvenanceEnvelope)
    assert leaf.is_tainted() is True


@given(
    sequence=st.lists(
        st.tuples(st.sampled_from(["tainted", "image", "model", "derive"]), indices),
        max_size=12,
    ),
)
@TXNS
def test_pr2_no_clear_through_public_api(sequence: list[tuple[str, int]]) -> None:
    """PR2 — no sequence of model-reachable calls turns taint off."""
    ledger = _new_ledger()
    ever_tainted: set[int] = set()

    for operation, index in sequence:
        target = _path(index)
        if operation == "tainted":
            ledger.record(target, ProvenanceEnvelope.of(Source.ENGAGEMENT_SURFACE))
            ever_tainted.add(index)
        elif operation == "image":
            ledger.record(target, ProvenanceEnvelope.of(Source.SANDBOX_IMAGE))
        elif operation == "model":
            ledger.record(target, ProvenanceEnvelope.of(Source.MODEL_AUTHORED))
        else:
            ledger.mark_derived(target, _path((index + 1) % 5))

    still_recorded = [
        index for index in ever_tainted if ledger.lookup(_path(index)) is not LedgerMiss.MISS
    ]
    for index in still_recorded:
        envelope = ledger.lookup(_path(index))
        assert isinstance(envelope, ProvenanceEnvelope)
        assert envelope.is_tainted() is True


@given(
    recorded=st.lists(indices, max_size=5),
    probe=indices,
)
@TXNS
def test_pr3_miss_is_never_an_envelope(recorded: list[int], probe: int) -> None:
    """PR3 — a path never recorded can never resolve to a clean envelope."""
    ledger = _new_ledger()
    for index in recorded:
        if index == probe:
            continue
        ledger.record(_path(index), ProvenanceEnvelope.of(Source.SANDBOX_IMAGE))

    result = ledger.lookup(_path(probe))

    assert result is LedgerMiss.MISS
    assert not isinstance(result, ProvenanceEnvelope)


@given(
    chain=st.lists(indices, min_size=1, max_size=4),
    principal=st.sampled_from([Principal.MODEL, Principal.SANDBOX, Principal.TOOL]),
)
@TXNS
def test_pr4_non_operator_can_never_clear(chain: list[int], principal: Principal) -> None:
    """PR4 — a non-operator principal cannot clear taint anywhere in a chain."""
    ledger = _new_ledger()
    origin = _path(chain[0])
    ledger.record(origin, ProvenanceEnvelope.of(Source.ENGAGEMENT_SURFACE))
    previous = origin
    for index in chain[1:]:
        current = _path(index)
        ledger.mark_derived(current, previous)
        previous = current

    with pytest.raises(PermissionError):
        ledger.declassify(previous, principal)

    envelope = ledger.lookup(previous)
    assert isinstance(envelope, ProvenanceEnvelope)
    assert envelope.is_tainted() is True
