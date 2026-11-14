"""Model-authored write recording.

The action gate denies ``EXECUTE`` on any resolved path it has no envelope for
(``R3 PROVENANCE_MISS``). That is the correct fail-closed posture, and it means
the agent's own scripts must be *positively* recorded or the engine cannot run
at all.

The sandbox SDK's only file-creation surface is ``apply_patch``: a raw patch
document whose headers name the files it touches. Paths in that document are
relative to the workspace root and never absolute (the SDK enforces this), so
resolution happens here against one declared root.

Nothing in this module touches the filesystem. It parses a patch document and
records what the model asked to write.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from sagaward.core.provenance.content import engagement_envelope
from sagaward.core.provenance.ledger import label_for_suffix
from sagaward.core.provenance.model import ProvenanceEnvelope, Source
from sagaward.core.provenance.paths import is_quarantine_path


if TYPE_CHECKING:
    from sagaward.core.provenance.ledger import ProvenanceLedger


WORKSPACE_ROOT = Path("/workspace")

ADD_FILE = "*** Add File: "
UPDATE_FILE = "*** Update File: "
MOVE_TO = "*** Move to: "
DELETE_FILE = "*** Delete File: "

_WRITE_OPERATIONS = (ADD_FILE, UPDATE_FILE, MOVE_TO, DELETE_FILE)


def model_authored_envelope(path: str | Path) -> ProvenanceEnvelope:
    """Envelope for content the model wrote itself."""
    return ProvenanceEnvelope.of(Source.MODEL_AUTHORED, label_for_suffix(path))


def resolve_workspace_path(raw: str) -> Path | None:
    """Resolve a patch path against the workspace root, or ``None`` if it escapes.

    The SDK documents relative-only references; absolute ones are rejected here
    too rather than trusted, because a path outside the workspace is not the
    model's to declare clean.
    """
    candidate = raw.strip()
    if not candidate or candidate.startswith(("/", "~")):
        return None
    resolved = (WORKSPACE_ROOT / candidate).resolve()
    if not resolved.is_relative_to(WORKSPACE_ROOT):
        return None
    return resolved


def paths_in_patch(raw_input: str) -> tuple[Path, ...]:
    """Every workspace path a patch document creates, updates, moves or deletes.

    Pure string work: no filesystem access, no shell parsing. Unknown lines are
    ignored, which is safe because the caller only ever *adds* clean envelopes
    and a missed path simply stays a miss (and a miss is a DENY).
    """
    seen: dict[Path, None] = {}
    for line in raw_input.splitlines():
        for marker in _WRITE_OPERATIONS:
            if line.startswith(marker):
                resolved = resolve_workspace_path(line[len(marker) :])
                if resolved is not None:
                    seen.setdefault(resolved, None)
                break
    return tuple(seen)


ADD_FILE_BLOCK = "*** Add File: "
UPDATE_FILE_BLOCK = "*** Update File: "
MOVE_TO_BLOCK = "*** Move to: "
DELETE_FILE_BLOCK = "*** Delete File: "

_TOUCHED = (ADD_FILE_BLOCK, UPDATE_FILE_BLOCK, MOVE_TO_BLOCK, DELETE_FILE_BLOCK)


def touched_paths(raw_input: str) -> tuple[Path, ...]:
    """Every workspace path a patch document touches, across all four operations."""
    seen: dict[Path, None] = {}
    for line in raw_input.splitlines():
        for marker in _TOUCHED:
            if line.startswith(marker):
                resolved = resolve_workspace_path(line[len(marker) :])
                if resolved is not None:
                    seen.setdefault(resolved, None)
                break
    return tuple(seen)


def added_file_contents(raw_input: str) -> dict[Path, str]:
    """Reconstruct the content of every ``*** Add File:`` block, exactly as authored.

    The patch grammar prefixes each added line with ``+``; stripping exactly one
    leaves the bytes the file will hold. No other normalization.
    """
    contents: dict[Path, str] = {}
    current: Path | None = None
    lines: list[str] = []

    def _flush() -> None:
        if current is not None:
            # Patch-added lines are terminated; a written file ends with a newline.
            contents.setdefault(current, "\n".join(lines) + "\n" if lines else "")

    for line in raw_input.splitlines():
        if line.startswith(ADD_FILE_BLOCK):
            _flush()
            current = resolve_workspace_path(line[len(ADD_FILE_BLOCK) :])
            lines = []
            continue
        if line.startswith("***"):
            _flush()
            current = None
            lines = []
            continue
        if current is not None and line.startswith("+"):
            lines.append(line[1:])
    _flush()
    return contents


def record_model_authored(ledger: ProvenanceLedger, paths: tuple[Path, ...] | list[Path]) -> int:
    """Record each path as model-authored. Returns how many were recorded."""
    recorded = 0
    for path in paths:
        ledger.record_key(path, model_authored_envelope(path))
        recorded += 1
    return recorded


def record_written_files(ledger: ProvenanceLedger, raw_input: str) -> int:
    """Record patch writes, tainting any whose bytes were surfaced from the target.

    A verbatim paste of fetched content is a model-authored write on the path
    side and an engagement byte-pipe on the content side. The content verdict
    wins: the index can only add engagement.
    """
    contents = added_file_contents(raw_input)
    recorded = 0
    for path, text in contents.items():
        if is_quarantine_path(path):
            continue
        envelope = model_authored_envelope(path)
        if isinstance(ledger.content_lookup(text), ProvenanceEnvelope):
            envelope = envelope.merged_with(engagement_envelope())
        ledger.record_key(path, envelope)
        recorded += 1
    return recorded
