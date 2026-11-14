"""Post-install reconciliation of the declared install prefixes.

An allowed ``PACKAGE_INSTALL`` writes files the seed never saw: a console script
under ``/usr/local/bin``, modules under ``site-packages``. Without recording
them, every installed tool is a permanent ``PROVENANCE_MISS`` and the gate
strangles the action it just allowed (checkpoint-1 F5a). Recording them by any
*textual* rule would launder a binary fetched into the same prefix, so the
recording obeys the same two conditions as every other model-authored record:
the file must be **newer than the install action** (attribution by time) and
must not match surfaced content in the index (attribution by bytes).

The walk runs inside the container through the argv-form observation channel and
emits JSON, not lines: a path containing a newline or a space is representable,
so the install listing has no newline contract to defend.

Bounded like the scratch reconciler: per-prefix depth cap and a total entry cap,
both as constants and both tested. Over-cap files stay misses, which is the
refusing direction.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

from sagaward.core.provenance.content import engagement_envelope
from sagaward.core.provenance.model import ProvenanceEnvelope
from sagaward.core.provenance.paths import is_quarantine_path, resolve_or_none
from sagaward.core.provenance.writes import model_authored_envelope


if TYPE_CHECKING:
    from collections.abc import Iterable

    from sagaward.core.provenance.ledger import ProvenanceLedger


# Per-manager write roots. A manager installs where *it* installs; a shared list
# was the round-15 finding (R15-TRIGPREF): six declared triggers wrote outside
# every declared prefix, so their walk recorded nothing and the gate then denied
# the tool the install delivered. Every key here is a declared trigger.
MANAGER_PREFIXES: dict[str, tuple[str, ...]] = {
    "pip": ("/usr/local/bin", "/usr/local/lib", "/app/.venv", "/home/pentester/.local"),
    "uv": ("/usr/local/bin", "/usr/local/lib", "/app/.venv", "/home/pentester/.local"),
    "poetry": ("/usr/local/bin", "/app/.venv", "/home/pentester/.local"),
    "conda": ("/opt/conda", "/usr/local/bin", "/home/pentester/.local"),
    "micromamba": ("/opt/conda", "/usr/local/bin", "/home/pentester/.local"),
    "npm": (
        "/usr/local/lib/node_modules",
        "/usr/local/bin",
        "/usr/lib/node_modules",
        "/home/pentester/.npm-global",
        "/home/pentester/.npm",
    ),
    "yarn": (
        "/usr/local/lib/node_modules",
        "/usr/local/bin",
        "/home/pentester/.yarn",
        "/home/pentester/.npm-global",
    ),
    "pnpm": ("/usr/local/lib/node_modules", "/usr/local/bin", "/home/pentester/.local/share/pnpm"),
    "gem": (
        "/usr/local/lib/ruby",
        "/usr/local/bin",
        "/var/lib/gems",
        "/home/pentester/.local/share/gem",
    ),
    "cargo": ("/home/pentester/.cargo/bin", "/usr/local/cargo/bin"),
    "go": ("/home/pentester/go/bin", "/root/go/bin", "/usr/local/go/bin"),
    "apt": ("/usr/bin", "/usr/sbin", "/usr/lib", "/bin", "/sbin"),
    "apt-get": ("/usr/bin", "/usr/sbin", "/usr/lib", "/bin", "/sbin"),
    "dpkg": ("/usr/bin", "/usr/sbin", "/usr/lib", "/bin", "/sbin"),
    "apk": ("/usr/bin", "/usr/sbin", "/usr/lib", "/bin", "/sbin"),
    "brew": ("/usr/local/Cellar", "/usr/local/bin"),
}

# The union, for callers that pass no manager (direct recorder tests, documentation).
INSTALL_PREFIXES: tuple[str, ...] = tuple(
    dict.fromkeys(prefix for prefixes in MANAGER_PREFIXES.values() for prefix in prefixes),
)

# Per-trigger roots: the trigger is the unit of the table, not the manager. A
# trigger names its roots directly, so a new trigger cannot inherit a manager's
# roots by accident and a trigger whose manager writes elsewhere can point
# elsewhere. The values below are the manager defaults the triggers share today.
TRIGGER_PREFIXES: dict[str, tuple[str, ...]] = {
    "pip": MANAGER_PREFIXES["pip"],
    "uv-pip": MANAGER_PREFIXES["uv"],
    "poetry-add": MANAGER_PREFIXES["poetry"],
    "conda-install": MANAGER_PREFIXES["conda"],
    "micromamba-install": MANAGER_PREFIXES["micromamba"],
    "npm-install": MANAGER_PREFIXES["npm"],
    "npm-ci": MANAGER_PREFIXES["npm"],
    "yarn-add": MANAGER_PREFIXES["yarn"],
    "pnpm-add": MANAGER_PREFIXES["pnpm"],
    "gem-install": MANAGER_PREFIXES["gem"],
    "cargo-install": MANAGER_PREFIXES["cargo"],
    "go-install": MANAGER_PREFIXES["go"],
    "apt-install": MANAGER_PREFIXES["apt"],
    "apt-get-install": MANAGER_PREFIXES["apt-get"],
    "dpkg-install": MANAGER_PREFIXES["dpkg"],
    "apk-add": MANAGER_PREFIXES["apk"],
    "brew-install": MANAGER_PREFIXES["brew"],
}


def prefixes_for_trigger(trigger: str) -> tuple[str, ...]:
    """The write roots of one declared trigger; an unknown trigger has none.

    No fallback to the union: a trigger that does not name roots cannot record,
    which is a miss (deny) rather than a walk over a guess.
    """
    return TRIGGER_PREFIXES.get(trigger, ())


def prefixes_for_manager(manager: str) -> tuple[str, ...]:
    """The roots of a manager key, for direct callers that name a manager."""
    return MANAGER_PREFIXES.get(manager, ())


INSTALL_MAX_DEPTH = 5
INSTALL_MAX_ENTRIES = 5_000

# An mtime this far ahead of observation is not clock skew, it is a forged
# timestamp (`touch -d '+1 day'`). Container/host skew is seconds; the tolerance
# is minutes so a legitimate install never trips it (checkpoint-1c 1c-3).
MTIME_FUTURE_TOLERANCE_NS = 300 * 10**9

INSTALL_PROBE_SCRIPT = r"""
import hashlib, json, os, sys

args = sys.argv[1:]
if args and args[0] == "--":
    args = args[1:]
not_before = int(args[0])
max_depth = int(args[1])
max_entries = int(args[2])
roots = args[3:]

found = []

def walk(directory, depth):
    if len(found) >= max_entries:
        return
    try:
        with os.scandir(directory) as it:
            entries = sorted(it, key=lambda e: e.name)
    except OSError:
        return
    for entry in entries:
        if len(found) >= max_entries:
            return
        child = depth + 1
        if child > max_depth:
            continue
        try:
            if entry.is_symlink():
                continue
            if entry.is_dir(follow_symlinks=False):
                walk(entry.path, child)
                continue
            if not entry.is_file(follow_symlinks=False):
                continue
            st = entry.stat(follow_symlinks=False)
        except OSError:
            continue
        if st.st_mtime_ns < not_before:
            continue
        try:
            digest = hashlib.sha256()
            with open(entry.path, "rb") as handle:
                for block in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(block)
        except OSError:
            continue
        found.append([entry.path, digest.hexdigest(), st.st_mtime_ns])

for root in roots:
    walk(root, 0)
sys.stdout.write(json.dumps(found))
"""


INSTALL_SNAPSHOT_SCRIPT = r"""
import hashlib, json, os, sys

args = sys.argv[1:]
if args and args[0] == "--":
    args = args[1:]
max_depth = int(args[0])
max_entries = int(args[1])
roots = args[2:]

found = []

def walk(directory, depth):
    if len(found) >= max_entries:
        return
    try:
        with os.scandir(directory) as it:
            entries = sorted(it, key=lambda e: e.name)
    except OSError:
        return
    for entry in entries:
        if len(found) >= max_entries:
            return
        child = depth + 1
        if child > max_depth:
            continue
        try:
            if entry.is_symlink():
                continue
            if entry.is_dir(follow_symlinks=False):
                walk(entry.path, child)
                continue
            if not entry.is_file(follow_symlinks=False):
                continue
        except OSError:
            continue
        try:
            digest = hashlib.sha256()
            with open(entry.path, "rb") as handle:
                for block in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(block)
        except OSError:
            continue
        found.append([entry.path, digest.hexdigest()])

for root in roots:
    walk(root, 0)
sys.stdout.write(json.dumps(found))
"""


def parse_snapshot_listing(stdout: str) -> dict[Path, str] | None:
    """Parse the pre-install snapshot. ``None`` means the truth path is unavailable.

    **Fail-closed bound (checkpoint-1c C5):** a snapshot that reaches the entry cap
    is treated as truncated, not as complete. A truncated snapshot makes every
    pre-existing file beyond the cap look absent, and "absent from the snapshot"
    means "new" — the inversion that re-opens the forged-mtime door. At the cap
    the truth path is unavailable, and the caller attributes nothing.
    """
    try:
        raw = json.loads(stdout)
    except (ValueError, TypeError):
        return None
    if not isinstance(raw, list):
        return None
    if len(raw) >= INSTALL_MAX_ENTRIES:
        return None
    snapshot: dict[Path, str] = {}
    for item in raw:
        if not isinstance(item, list) or len(item) != 2:
            continue
        path, content_digest = item
        if not isinstance(path, str) or not path.startswith("/"):
            continue
        if not isinstance(content_digest, str) or len(content_digest) != 64:
            continue
        snapshot.setdefault(Path(path), content_digest)
    return snapshot


def parse_install_listing(stdout: str) -> tuple[tuple[Path, str, int], ...] | None:
    """Parse the walk's JSON. ``None`` means the listing is unusable.

    A malformed document is not partially trusted: recording half a listing would
    silently leave the other half as misses *and* make the walk look successful.
    """
    try:
        raw = json.loads(stdout)
    except (ValueError, TypeError):
        return None
    if not isinstance(raw, list):
        return None
    parsed: dict[Path, tuple[str, int]] = {}
    for item in raw:
        if not isinstance(item, list) or len(item) != 3:
            continue
        path, content_digest, mtime = item
        if not isinstance(path, str) or not path.startswith("/"):
            continue
        if not isinstance(content_digest, str) or len(content_digest) != 64:
            continue
        try:
            mtime_ns = int(mtime)
        except (TypeError, ValueError):
            continue
        parsed.setdefault(Path(path), (content_digest, mtime_ns))
        if len(parsed) >= INSTALL_MAX_ENTRIES:
            break
    return tuple((path, digest, mtime) for path, (digest, mtime) in parsed.items())


def under_install_prefix(
    path: str | Path,
    prefixes: Iterable[str | Path] | None = None,
) -> bool:
    """True only for a path inside the given prefixes (default: the union), outside quarantine."""
    candidate = Path(path)
    if is_quarantine_path(candidate):
        return False
    roots = INSTALL_PREFIXES if prefixes is None else tuple(prefixes)
    return any(candidate.is_relative_to(Path(prefix)) for prefix in roots)


def record_install_artifacts(
    ledger: ProvenanceLedger,
    artifacts: Iterable[tuple[Path, str, int]],
    *,
    not_before_ns: int,
    prefixes: Iterable[str | Path] | None = None,
    snapshot: dict[Path, str] | None = None,
    observed_at_ns: int | None = None,
    baseline: Iterable[Path] | None = None,
) -> int:
    """Record files an install created; surfaced bytes still taint.

    Attribution is the **pre/post delta**, decided by snapshot, baseline, time
    and bytes, and **only with a snapshot**. ``snapshot`` is the pre-install
    digest listing; ``baseline`` is the pre-install *path* listing — the files
    that existed before the command ran, whose digests may not be available. A
    path in the baseline is **never** attributed as *created*: the install did
    not make it, whatever its mtime says. A path the snapshot records with a
    changed digest is a **modification** and is recorded (the install wrote it).

    ``observed_at_ns`` anchors the 300 s forge window to the action's observation
    rather than to the reconciler's clock: a file modified more than 300 s after
    the observation is provably forged and records nothing. A file **older than
    the action** (``not_before_ns``) and absent from both pre-install listings is
    not new and records nothing.

    A digest that matches surfaced content unions engagement, so an install is not
    a laundering exit. **Without a snapshot nothing is recorded** (checkpoint-1c
    C5): a failed or truncated snapshot is not a licence to fall back to mtime,
    because that fallback is exactly the inversion the truth path exists to
    prevent. An unresolvable path is skipped, never raised into the tool surface.
    """
    now_ns = time.time_ns() if observed_at_ns is None else observed_at_ns
    preexisting = frozenset(baseline) if baseline is not None else frozenset()
    recorded = 0
    for raw, content_digest, mtime_ns in artifacts:
        if mtime_ns > now_ns + MTIME_FUTURE_TOLERANCE_NS:
            # Provably forged: a file cannot be modified after it was observed.
            continue
        path = resolve_or_none(raw)
        if path is None:
            # Unresolvable: there is no identity to attribute. Refuse — a raise
            # here would reach the tool surface through the reconciler.
            continue
        if not under_install_prefix(raw, prefixes) or not under_install_prefix(path, prefixes):
            continue
        if snapshot is None:
            # No truth path (failed or truncated snapshot): attribute nothing.
            # The time path alone would bless a pre-existing file whose mtime was
            # forged forward — the door C5 closed (round 13, R13-NONE family).
            continue
        prior = snapshot.get(path)
        if prior is not None:
            if prior == content_digest:
                # Unchanged content: this is the pre-existing file with a forged
                # or freshly touched mtime, not an install.
                continue
            # Changed digest: the install modified a pre-existing file. That is a
            # write and is recorded (the dual-snapshot delta's "both, differing").
        elif path in preexisting:
            # Present before the install but with no digest in the snapshot: the
            # baseline is authoritative about existence, so this is pre-existing,
            # not created. Without this clause a fresh mtime on a baseline file
            # would attribute it to the install (M35's cell).
            continue
        elif mtime_ns < not_before_ns:
            # Absent from both pre-install listings and older than the action:
            # not new.
            continue
        envelope = model_authored_envelope(path)
        if isinstance(ledger.content_lookup_digest(content_digest), ProvenanceEnvelope):
            envelope = envelope.merged_with(engagement_envelope())
        ledger.record_key(path, envelope)
        recorded += 1
    return recorded
