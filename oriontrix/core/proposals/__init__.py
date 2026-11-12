"""Propose-dispose instrumentation: funnel + proposal-context assembler."""

from __future__ import annotations

from oriontrix.core.proposals.assembler import assemble_proposal_context
from oriontrix.core.proposals.models import (
    C1C8Answer,
    C1C8Checklist,
    HarnessVerdict,
    InterventionFlags,
    ProposalContext,
    ProposalRecord,
)


__all__ = [
    "C1C8Answer",
    "C1C8Checklist",
    "HarnessVerdict",
    "InterventionFlags",
    "ProposalContext",
    "ProposalRecord",
    "assemble_proposal_context",
]
