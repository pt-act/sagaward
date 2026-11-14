"""Monotone path -> origin ledger for artifacts inside the sandbox.

Two properties make this safe to gate on:

* **Monotone.** Sources only accumulate. No model-reachable method removes
  ``ENGAGEMENT_SURFACE``; the only clearing path is :meth:`ProvenanceLedger.declassify`,
  which requires the operator principal and is audited.
* **Miss is not clean.** An unknown path returns :attr:`LedgerMiss.MISS`. Callers
  must treat a miss as unverified, never as image provenance.

Derivation from an unrecorded ancestor is treated as engagement-derived and
flagged inferred. That over-taints on purpose: the ledger cannot prove where
those bytes came from, and the gate must fail closed. :meth:`is_inferred`
distinguishes the assumption from an observed origin.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from sagaward.core.provenance.content import digest, engagement_envelope
from sagaward.core.provenance.model import Label, ProvenanceEnvelope, Source


if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from sagaward.core.provenance.artifact import ArtifactRef


class LedgerMiss(StrEnum):
    """Returned by ``lookup`` for a path the ledger has never seen."""

    MISS = "miss"


class Principal(StrEnum):
    """Who is asking. Only ``OPERATOR`` may clear taint."""

    OPERATOR = "operator"
    MODEL = "model"
    SANDBOX = "sandbox"
    TOOL = "tool"


class DeclassifyForbidden(PermissionError):  # noqa: N818 - name fixed by apf-provenance spec
    """Raised when a non-operator principal attempts to declassify a path."""


@dataclass(frozen=True, slots=True)
class Declassification:
    """Audit record for an operator-cleared path."""

    path: Path
    at: datetime
    principal: Principal


# Assumption stamped on a leaf derived from an unrecorded ancestor. Not an
# observed origin; ``ProvenanceLedger.is_inferred`` marks those leaves.
INFERRED_UNKNOWN = ProvenanceEnvelope.of(Source.ENGAGEMENT_SURFACE)


def canonical_path(path: str | Path) -> Path:
    """Resolve symlinks and ``..`` so one artifact has one key."""
    return Path(path).resolve()


def inode_key(path: str | Path) -> tuple[int, int] | None:
    """Identity of an existing artifact, or ``None`` if it is not on disk yet.

    Two directory entries that share an inode are the same bytes. Path
    resolution cannot see that; the ledger keys on it so a hardlink cannot
    launder a tainted binary into an exec-capable directory.
    """
    try:
        stat = Path(path).stat()
    except OSError:
        return None
    return (stat.st_dev, stat.st_ino)


class ProvenanceLedger:
    """Per-sandbox origin ledger. Not thread-shared across scans by design."""

    def __init__(self) -> None:
        self._envelopes: dict[Path, ProvenanceEnvelope] = {}
        self._by_inode: dict[tuple[int, int], ProvenanceEnvelope] = {}
        self._by_content: dict[str, ProvenanceEnvelope] = {}
        self._edges: dict[Path, set[Path]] = {}
        self._inferred: set[Path] = set()
        self._inferred_inodes: set[tuple[int, int]] = set()
        self._declassifications: list[Declassification] = []
        self._lock = threading.RLock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._envelopes)

    def record(
        self,
        path: str | Path,
        envelope: ProvenanceEnvelope,
        derived_from: Iterable[str | Path] = (),
    ) -> ProvenanceEnvelope:
        """Record an origin for ``path``, merging with whatever is already known."""
        return self.record_key(canonical_path(path), envelope, derived_from)

    def record_key(
        self,
        path_key: str | Path,
        envelope: ProvenanceEnvelope,
        derived_from: Iterable[str | Path] = (),
    ) -> ProvenanceEnvelope:
        """Record under an already-resolved key; never canonicalize a second time.

        The caller owns resolution. A resolver invoked here would be a *second*
        resolution the caller cannot bind to the facts it checked: a link toggled
        between the caller's check and this store would select the link's target
        as the key (round 13, R13-ATK). The inode is still stat'ed, and only so
        that taint from an aliased inode unions in — a stat race can over-taint,
        never clear.
        """
        key = Path(path_key)
        inode = inode_key(key)
        ancestors = self._resolve_ancestors(derived_from)
        with self._lock:
            merged = self._merge(key, inode, envelope)
            inferred_here = False
            for ancestor_key, ancestor_envelope, inferred in ancestors:
                merged = merged.merged_with(ancestor_envelope)
                self._edges.setdefault(key, set()).add(ancestor_key)
                inferred_here = inferred_here or inferred
            self._store(key, inode, merged, inferred=inferred_here)
            return merged

    def mark_derived(self, path: str | Path, source: str | Path) -> ProvenanceEnvelope:
        """Declare that ``path`` was produced from ``source`` and inherit its origin."""
        key = canonical_path(path)
        inode = inode_key(key)
        ancestors = self._resolve_ancestors([source])
        ancestor_key, ancestor_envelope, inferred = ancestors[0]
        with self._lock:
            merged = self._merge(key, inode, ancestor_envelope)
            self._edges.setdefault(key, set()).add(ancestor_key)
            self._store(key, inode, merged, inferred=inferred)
            return merged

    def lookup(self, path: str | Path) -> ProvenanceEnvelope | LedgerMiss:
        """Return the envelope for ``path``, or ``LedgerMiss.MISS`` if unrecorded.

        Ergonomic entry point for non-gate callers: resolves the path and, on a
        path-key miss, stats it so a hardlink still finds its artifact. The gate
        must NOT use this — it consumes :meth:`lookup_keys` or
        :meth:`lookup_ref`, which never touch the filesystem.
        """
        key = canonical_path(path)
        inode = None if key in self._envelopes else inode_key(key)
        return self.lookup_keys(key, inode)

    def lookup_ref(self, ref: ArtifactRef) -> ProvenanceEnvelope | LedgerMiss:
        """Pure lookup over a resolution snapshot produced by ``classify``."""
        return self.lookup_keys(Path(ref.path_key), ref.inode_key)

    def lookup_keys(
        self,
        path_key: Path,
        inode_key_value: tuple[int, int] | None = None,
    ) -> ProvenanceEnvelope | LedgerMiss:
        """Pure key lookup: dict reads only, no filesystem access.

        ``LedgerMiss.MISS`` means *neither* index knows the artifact. Keys must
        come from :func:`canonical_path` / :func:`inode_key`; this method does
        not normalize them, because normalizing is I/O.
        """
        with self._lock:
            recorded = self._envelopes.get(path_key)
            if recorded is not None:
                return recorded
            if inode_key_value is not None:
                return self._by_inode.get(inode_key_value, LedgerMiss.MISS)
            return LedgerMiss.MISS

    def record_surfaced_content(self, content: str | bytes) -> None:
        """Remember bytes surfaced from the engagement. Index holds taint only."""
        self.record_surfaced_digest(digest(content))

    def record_surfaced_digest(self, content_digest: str) -> None:
        """Remember an already-hashed engagement digest. Index holds taint only.

        The digest form exists for the quarantine sweep: those bytes are hashed
        inside the container and never enter this process, and they are
        engagement-derived by construction (round 16, checkpoint-1b R2).
        """
        if len(content_digest) != 64:
            raise ValueError("content digest must be 64 hex characters")
        with self._lock:
            self._by_content[content_digest] = engagement_envelope()

    def content_lookup(self, content: str | bytes) -> ProvenanceEnvelope | LedgerMiss:
        """Pure digest lookup for exact bytes. Never returns a clean envelope."""
        return self.content_lookup_digest(digest(content))

    def content_lookup_digest(self, content_digest: str) -> ProvenanceEnvelope | LedgerMiss:
        """Pure digest lookup by hex digest, for callers that already hashed."""
        with self._lock:
            return self._by_content.get(content_digest, LedgerMiss.MISS)

    def indexed_content_count(self) -> int:
        with self._lock:
            return len(self._by_content)

    def is_inferred(self, path: str | Path) -> bool:
        """True when the path's taint is an assumption about unknown ancestry."""
        key = canonical_path(path)
        with self._lock:
            if key in self._inferred:
                return True
            inode = inode_key(key)
            return inode is not None and inode in self._inferred_inodes

    def operators(self) -> Mapping[Path, frozenset[Path]]:
        """Derivation edges: leaf -> the ancestors it was built from."""
        with self._lock:
            return {leaf: frozenset(parents) for leaf, parents in self._edges.items()}

    def declassifications(self) -> tuple[Declassification, ...]:
        """Append-only audit trail of operator declassifications."""
        with self._lock:
            return tuple(self._declassifications)

    def declassify(self, path: str | Path, principal: Principal) -> ProvenanceEnvelope:
        """Clear engagement taint. Operator only, and audited."""
        if principal is not Principal.OPERATOR:
            raise DeclassifyForbidden(
                f"{principal.value} may not declassify {path}; only the operator can",
            )
        key = canonical_path(path)
        with self._lock:
            current = self._envelopes.get(key)
            labels = current.labels if current is not None else frozenset()
            remaining = (current.sources if current is not None else frozenset()) - {
                Source.ENGAGEMENT_SURFACE,
            }
            cleared = ProvenanceEnvelope(
                sources=frozenset(remaining) or frozenset({Source.OPERATOR}),
                labels=labels,
            )
            self._envelopes[key] = cleared
            self._inferred.discard(key)
            inode = inode_key(key)
            if inode is not None:
                # Clean is asserted on the path only; an inode entry is a taint
                # propagation device and must not survive as a clean entry.
                self._by_inode.pop(inode, None)
                self._inferred_inodes.discard(inode)
            self._declassifications.append(
                Declassification(path=key, at=datetime.now(UTC), principal=principal),
            )
            return cleared

    def _merge(
        self,
        key: Path,
        inode: tuple[int, int] | None,
        incoming: ProvenanceEnvelope,
    ) -> ProvenanceEnvelope:
        existing = self._envelopes.get(key)
        if existing is None and inode is not None:
            existing = self._by_inode.get(inode)
        return incoming if existing is None else existing.merged_with(incoming)

    def _store(
        self,
        key: Path,
        inode: tuple[int, int] | None,
        envelope: ProvenanceEnvelope,
        *,
        inferred: bool,
    ) -> None:
        self._envelopes[key] = envelope
        if inode is not None and envelope.is_tainted():
            # The inode index exists to extend *taint* to aliases, never to extend
            # cleanliness. Recording a clean envelope under an inode would bless a
            # path the ledger never vouched for — e.g. a hardlink to an unrecorded
            # quarantine file would make that quarantine path read clean.
            self._by_inode[inode] = envelope
            if inferred:
                self._inferred_inodes.add(inode)
        if inferred:
            self._inferred.add(key)

    def _resolve_ancestors(
        self,
        paths: Iterable[str | Path],
    ) -> list[tuple[Path, ProvenanceEnvelope, bool]]:
        resolved: list[tuple[Path, ProvenanceEnvelope, bool]] = []
        with self._lock:
            for raw in paths:
                key = canonical_path(raw)
                known = self._envelopes.get(key)
                if known is None:
                    resolved.append((key, INFERRED_UNKNOWN, True))
                else:
                    resolved.append((key, known, key in self._inferred))
        return resolved


def label_for_suffix(path: str | Path) -> Label:
    """Best-effort artifact label from the file name. Advisory only."""
    suffix = Path(path).suffix.lower()
    if suffix in {".sh", ".py", ".pl", ".rb", ".js", ".ps1"}:
        return Label.SCRIPT
    if suffix in {".zip", ".tar", ".gz", ".tgz", ".7z", ".rar"}:
        return Label.ARCHIVE
    if suffix in {".txt", ".md", ".rst", ".pdf", ".doc", ".docx"}:
        return Label.INSTRUCTION_BEARING
    return Label.BINARY
