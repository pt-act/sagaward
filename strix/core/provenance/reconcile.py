"""Post-exec observation of scratch, for files the patch hook never saw.

The system prompt's documented workflow writes scripts with shell redirection
("write reusable scripts under ``/workspace/scratch/`` and run them with
``python3``"). Those writes never produce an ``apply_patch`` document, so without
observation the files stay ledger misses and the action gate denies them —
a fence that greens its harness and stalls the engine on its own documented flow.

Observation is the only honest input here. Inferring from the command string
would trust a model-controlled string, which this program's "structural, not
advisory" rule forbids. So the reconciler asks the sandbox what is actually in
scratch, after the command returns.

Closed world: it records **nothing** outside ``/workspace/scratch``, under any
circumstance. Bounds mirror the image seed's (depth 3, 20k entries).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from strix.core.provenance import paths as provenance_paths
from strix.core.provenance.content import engagement_envelope
from strix.core.provenance.model import ProvenanceEnvelope
from strix.core.provenance.paths import is_quarantine_path, resolve_or_none
from strix.core.provenance.seed import FIND_BINARY, SHA256SUM_BINARY
from strix.core.provenance.writes import WORKSPACE_ROOT, model_authored_envelope


if TYPE_CHECKING:
    from collections.abc import Iterable

    from strix.core.provenance.ledger import ProvenanceLedger


SCRATCH_ROOT = WORKSPACE_ROOT / "scratch"
RECONCILE_MAX_DEPTH = 3
RECONCILE_MAX_ENTRIES = 20_000

RECONCILE_COMMAND: tuple[str, ...] = (
    FIND_BINARY,
    str(SCRATCH_ROOT),
    "-maxdepth",
    str(RECONCILE_MAX_DEPTH),
    "-type",
    "f",
    "-exec",
    SHA256SUM_BINARY,
    "{}",
    "+",
)


def is_within_scratch_resolved(resolved: Path) -> bool:
    """True only for an already-resolved path inside scratch and outside quarantine.

    The recorder resolves once and reuses that value, so the check and the
    record key cannot straddle a path swap (round 13, R13-ATK).
    """
    return resolved.is_relative_to(SCRATCH_ROOT.resolve()) and not is_quarantine_path(resolved)


def is_within_scratch(path: str | Path) -> bool:
    """True only for paths inside scratch and never inside quarantine.

    The quarantine exclusion is not decorative: ``STRIX_QUARANTINE_DIR`` can point
    inside the scratch tree, and that configuration is exactly the one where a
    containment-only rule would record quarantine content as authored. Round 7
    proved the branch load-bearing under that override, so it is back and tested.
    An unresolvable path is outside scratch — the refusing direction.
    """
    resolved = resolve_or_none(path)
    if resolved is None:
        return False
    return is_within_scratch_resolved(resolved)


def artifacts_in_scratch_listing(stdout: str) -> tuple[tuple[Path, str], ...]:
    """Parse ``sha256sum`` output into (path, digest) pairs, keeping only scratch.

    Pure. Lines that do not carry a 64-hex digest are dropped rather than guessed
    at: an unhashed file simply stays a miss, and a miss is a DENY.
    """
    seen: dict[Path, str] = {}
    for line in stdout.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) != 2:
            continue
        content_digest, raw_path = parts
        if len(content_digest) != 64:
            continue
        entry = raw_path.strip()
        if not entry.startswith("/"):
            continue
        if not is_within_scratch(entry):
            continue
        seen.setdefault(Path(entry).resolve(), content_digest)
        if len(seen) >= RECONCILE_MAX_ENTRIES:
            break
    return tuple(seen.items())


def paths_in_scratch_listing(stdout: str) -> tuple[Path, ...]:
    """Parse a ``find`` listing, keeping only resolved paths inside scratch.

    Pure: no filesystem access. Anything absolute-looking but outside scratch,
    and anything in quarantine, is dropped rather than trusted. Over-cap input is
    truncated — unrecorded files stay misses, which is the safe direction.
    """
    seen: dict[Path, None] = {}
    for line in stdout.splitlines():
        entry = line.strip()
        if not entry.startswith("/"):
            continue
        if not is_within_scratch(entry):
            continue
        seen.setdefault(Path(entry).resolve(), None)
        if len(seen) >= RECONCILE_MAX_ENTRIES:
            break
    return tuple(seen)


QUARANTINE_PROBE_SCRIPT = r"""
import hashlib, json, os, sys

args = sys.argv[1:]
if args and args[0] == "--":
    args = args[1:]
root = args[0]
start_after = args[1]
max_entries = int(args[2])
max_depth = int(args[3])

paths = []

def walk(directory, depth):
    if depth > max_depth:
        return
    try:
        with os.scandir(directory) as it:
            entries = sorted(it, key=lambda e: e.path)
    except OSError:
        return
    for entry in entries:
        try:
            if entry.is_symlink():
                continue
            if entry.is_dir(follow_symlinks=False):
                walk(entry.path, depth + 1)
                continue
            if not entry.is_file(follow_symlinks=False):
                continue
        except OSError:
            continue
        paths.append(entry.path)

walk(root, 0)
# Global sort before slicing: a depth-first page boundary is not a lexicographic
# boundary, and a cursor over unsorted pages can skip files.
paths.sort()

found = []
for path in paths:
    if len(found) >= max_entries:
        break
    if path <= start_after:
        continue
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
    except OSError:
        continue
    found.append([path, digest.hexdigest()])
sys.stdout.write(json.dumps(found))
"""


def quarantine_command(
    start_after: str | None = None,
    max_entries: int = RECONCILE_MAX_ENTRIES,
) -> tuple[str, ...]:
    """Arguments for one sweep page: root, cursor, cap, depth.

    The sweep pages by path cursor past the entry cap (round-16 verdict: a
    20,001-file quarantine truncated at 20k and the payload's digest went
    unindexed). A file moved between pages can be missed by the page that would
    have carried it and is not revisited until the next exec's sweep — the
    declared `mv`-between-sweeps residual.
    """
    return (
        str(provenance_paths.QUARANTINE_DIR),
        start_after or "",
        str(max_entries),
        str(RECONCILE_MAX_DEPTH),
    )


def artifacts_in_quarantine_listing(stdout: str) -> tuple[tuple[Path, str], ...] | None:
    """Parse one sweep page's JSON. ``None`` means the page is unusable.

    A malformed page is not partially trusted: recording half a page would leave
    the other half unindexed while making the sweep look successful.
    """
    try:
        raw = json.loads(stdout)
    except (ValueError, TypeError):
        return None
    if not isinstance(raw, list):
        return None
    seen: dict[Path, str] = {}
    for item in raw:
        if not isinstance(item, list) or len(item) != 2:
            continue
        raw_path, content_digest = item
        if not isinstance(raw_path, str) or not raw_path.startswith("/"):
            continue
        if not isinstance(content_digest, str) or len(content_digest) != 64:
            continue
        path = resolve_or_none(raw_path)
        if path is None or not is_quarantine_path(path):
            continue
        seen.setdefault(path, content_digest)
        if len(seen) >= RECONCILE_MAX_ENTRIES:
            break
    return tuple(seen.items())


def record_quarantine_artifacts(
    ledger: ProvenanceLedger,
    artifacts: Iterable[tuple[Path, str]],
) -> int:
    """Record quarantine contents as engagement-tainted and index their bytes."""
    recorded = 0
    for path, content_digest in artifacts:
        ledger.record_surfaced_digest(content_digest)
        ledger.record_key(path, engagement_envelope())
        recorded += 1
    return recorded


def record_scratch_artifacts(
    ledger: ProvenanceLedger,
    artifacts: Iterable[tuple[str | Path, str] | str | Path],
    *,
    baseline: Iterable[str | Path] = (),
) -> int:
    """Record in-scratch artifacts, tainting any whose bytes were surfaced from the target.

    A digest hit means these exact bytes came from the engagement surface, so the
    file is recorded as engagement-derived, not authored. This is where the
    straight byte-pipe (fetch → exec-capable scratch) is closed: the index can
    only add engagement, and the first exec decision sees the tainted envelope.
    """
    baseline_paths = {Path(entry) for entry in baseline}
    recorded = 0
    for item in artifacts:
        raw, content_digest = item if isinstance(item, tuple) else (item, None)
        path = resolve_or_none(raw)
        if path is None or not is_within_scratch_resolved(path):
            continue
        if path in baseline_paths:
            # Pre-existing at bring-up (epoch-zero baseline): not this epoch's
            # authored content, so it stays a miss and the gate denies it.
            continue
        envelope = model_authored_envelope(path)
        if content_digest is not None and isinstance(
            ledger.content_lookup_digest(content_digest),
            ProvenanceEnvelope,
        ):
            envelope = envelope.merged_with(engagement_envelope())
        ledger.record_key(path, envelope)
        recorded += 1
    return recorded
