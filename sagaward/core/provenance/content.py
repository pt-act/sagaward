"""Content-hash index: the half of provenance that never becomes a path.

A shell fetch is a straight byte pipe from the target to an exec-capable
directory. No tool boundary sees the model read those bytes, so path recording
alone cannot distinguish downloaded content from authored content. The index
closes that channel by remembering the bytes themselves.

**Taint-only invariant (spec 0.2.6, condition 2).** No branch of this module ever
confers cleanliness. It stores engagement envelopes and nothing else; a hit can
only union `ENGAGEMENT_SURFACE` onto a path. Clean envelopes come from
`MODEL_AUTHORED` recording or the image seed, never from here. The B2 lesson,
promoted from a bug fix to a structural rule.

**Zero normalization.** Digests are over exact bytes. Normalizing would
manufacture false positives (`#!/bin/sh` headers, shared boilerplate) and turn
the index into a taint amplifier that declassify has to clean up.

The false-positive class that remains — two files genuinely byte-identical,
one authored and one fetched — over-taints by design. The audited operator
`declassify` is the escape.
"""

from __future__ import annotations

import hashlib

from sagaward.core.provenance.model import ProvenanceEnvelope, Source


# Observation vocabulary: a path confirmed missing at observation time. Distinct
# from "unobserved" (None), which may never be treated as absence.
ABSENT = "<absent>"


def digest(content: str | bytes) -> str:
    """SHA-256 over exact bytes. No encoding games, no whitespace folding."""
    payload = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(payload).hexdigest()


def engagement_envelope() -> ProvenanceEnvelope:
    """The only envelope the index is allowed to hold."""
    return ProvenanceEnvelope.of(Source.ENGAGEMENT_SURFACE)
