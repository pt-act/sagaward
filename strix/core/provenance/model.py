"""Where the bytes inside the sandbox came from.

An envelope records origin only. It never stores content and never judges
intent: deciding whether text is malicious is unbounded and adversarial, while
deciding whether an action may touch bytes of a known origin is enumerable.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Source(StrEnum):
    """Where content entered the sandbox."""

    ENGAGEMENT_SURFACE = "engagement_surface"
    SANDBOX_IMAGE = "sandbox_image"
    MODEL_AUTHORED = "model_authored"
    OPERATOR = "operator"


class Label(StrEnum):
    """What kind of artifact a path holds. Advisory for reporting, never for gating."""

    INSTRUCTION_BEARING = "instruction_bearing"
    BINARY = "binary"
    SCRIPT = "script"
    ARCHIVE = "archive"


class ProvenanceEnvelope(BaseModel):
    """Frozen origin record. ``is_tainted`` is a pure function of ``sources``."""

    model_config = ConfigDict(frozen=True)

    sources: frozenset[Source]
    labels: frozenset[Label] = Field(default_factory=frozenset)

    @field_validator("sources")
    @classmethod
    def _require_a_source(cls, value: frozenset[Source]) -> frozenset[Source]:
        if not value:
            raise ValueError("an envelope must carry at least one source")
        return value

    @classmethod
    def of(cls, source: Source, *labels: Label) -> ProvenanceEnvelope:
        """Build an envelope for a single origin, with optional labels."""
        return cls(sources=frozenset({source}), labels=frozenset(labels))

    def is_tainted(self) -> bool:
        """True when any part of the artifact came from the engagement surface."""
        return Source.ENGAGEMENT_SURFACE in self.sources

    def merged_with(self, other: ProvenanceEnvelope) -> ProvenanceEnvelope:
        """Union of origins and labels. Merging can only add, never remove."""
        return ProvenanceEnvelope(
            sources=self.sources | other.sources,
            labels=self.labels | other.labels,
        )
