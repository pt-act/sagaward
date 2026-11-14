"""Pure provenance primitives for the action fence.

No Docker, network, SDK, or engine imports: this package is unit-testable
without a container and cannot influence a propose-dispose verdict.
"""

from __future__ import annotations

from sagaward.core.provenance.artifact import ArtifactRef
from sagaward.core.provenance.content import digest, engagement_envelope
from sagaward.core.provenance.ledger import (
    INFERRED_UNKNOWN,
    Declassification,
    DeclassifyForbidden,
    LedgerMiss,
    Principal,
    ProvenanceLedger,
    canonical_path,
    inode_key,
    label_for_suffix,
)
from sagaward.core.provenance.model import Label, ProvenanceEnvelope, Source
from sagaward.core.provenance.paths import DEFAULT_QUARANTINE_DIR, QUARANTINE_DIR, QUARANTINE_DIR_ENV
from sagaward.core.provenance.reconcile import (
    RECONCILE_COMMAND,
    RECONCILE_MAX_DEPTH,
    RECONCILE_MAX_ENTRIES,
    SCRATCH_ROOT,
    is_within_scratch,
    paths_in_scratch_listing,
    record_scratch_artifacts,
)
from sagaward.core.provenance.seed import (
    IMAGE_INVENTORY_COMMAND,
    IMAGE_ROOTS,
    default_image_roots,
    parse_executable_listing,
    parse_inventory_pairs,
    seed_image_inventory,
    seed_inventory,
    seed_paths,
)
from sagaward.core.provenance.writes import (
    WORKSPACE_ROOT,
    model_authored_envelope,
    paths_in_patch,
    record_model_authored,
    resolve_workspace_path,
)


__all__ = [
    "DEFAULT_QUARANTINE_DIR",
    "IMAGE_INVENTORY_COMMAND",
    "IMAGE_ROOTS",
    "INFERRED_UNKNOWN",
    "QUARANTINE_DIR",
    "QUARANTINE_DIR_ENV",
    "RECONCILE_COMMAND",
    "RECONCILE_MAX_DEPTH",
    "RECONCILE_MAX_ENTRIES",
    "SCRATCH_ROOT",
    "WORKSPACE_ROOT",
    "ArtifactRef",
    "Declassification",
    "DeclassifyForbidden",
    "Label",
    "LedgerMiss",
    "Principal",
    "ProvenanceEnvelope",
    "ProvenanceLedger",
    "Source",
    "canonical_path",
    "default_image_roots",
    "digest",
    "engagement_envelope",
    "inode_key",
    "is_within_scratch",
    "label_for_suffix",
    "model_authored_envelope",
    "parse_executable_listing",
    "paths_in_patch",
    "paths_in_scratch_listing",
    "record_model_authored",
    "record_scratch_artifacts",
    "resolve_workspace_path",
    "parse_inventory_pairs",
    "seed_image_inventory",
    "seed_inventory",
    "seed_paths",
]
