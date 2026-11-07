"""Seed image-owned provenance at sandbox bring-up.

Without this, every preinstalled tool is a ledger miss, and a miss is a DENY.
The gate's true-negative criteria (``nmap``, ``ffuf``, ``nuclei`` still run)
depend on the image's own content being recorded as image-sourced before any
agent action can reach the ledger.

The seed only ever records ``SANDBOX_IMAGE``. It cannot taint, and it cannot
clear taint: recording onto an existing key unions sources, so an
engagement-wired record made earlier still wins.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from strix.core.provenance.ledger import canonical_path, label_for_suffix
from strix.core.provenance.model import ProvenanceEnvelope, Source


if TYPE_CHECKING:
    from collections.abc import Iterable

    from strix.core.provenance.ledger import ProvenanceLedger


EXECUTABLE_BITS = 0o111
MAX_DEPTH = 3
MAX_PATHS = 20_000

_IMAGE_ENVELOPE_CACHE: dict[str, ProvenanceEnvelope] = {}


def _image_envelope(path: Path) -> ProvenanceEnvelope:
    label = label_for_suffix(path)
    key = label.value
    cached = _IMAGE_ENVELOPE_CACHE.get(key)
    if cached is None:
        cached = ProvenanceEnvelope.of(Source.SANDBOX_IMAGE, label)
        _IMAGE_ENVELOPE_CACHE[key] = cached
    return cached


def _is_executable_file(path: Path) -> bool:
    try:
        stat = path.stat()
    except OSError:
        return False
    return path.is_file() and bool(stat.st_mode & EXECUTABLE_BITS)


def _walk(root: Path, depth: int) -> Iterable[Path]:
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return
    for entry in entries:
        yield entry
        if depth < MAX_DEPTH and entry.is_dir():
            yield from _walk(entry, depth + 1)


def seed_image_inventory(ledger: ProvenanceLedger, roots: Iterable[str | Path]) -> int:
    """Record every executable under host ``roots`` as image-sourced. Returns the count.

    **Host-walk helper, not the live path.** The sandbox's ledger is seeded from an
    inventory enumerated *inside* the container and recorded through
    :func:`seed_paths` (``runtime/provenance_bringup.py``); a host walk here would
    record paths the container never had. This function is used by tests and
    deployment tooling that already know the roots are the target filesystem's.
    """
    seeded = 0
    seen: set[Path] = set()
    for raw_root in roots:
        root = canonical_path(raw_root)
        if root in seen:
            continue
        seen.add(root)
        for candidate in _walk(root, depth=0):
            if seeded >= MAX_PATHS:
                return seeded
            if not _is_executable_file(candidate):
                continue
            if is_agent_writable(candidate):
                continue
            ledger.record(canonical_path(candidate), _image_envelope(candidate))
            seeded += 1
    return seeded


# Root-owned standard prefixes only. An agent-writable root must never appear here:
# seeding it would declare content the agent can rewrite as image-owned, so a
# replaced binary would read clean (validator round 1, B3).
FIND_BINARY = "/usr/bin/find"
SHA256SUM_BINARY = "/usr/bin/sha256sum"

IMAGE_ROOTS: tuple[str, ...] = (
    "/usr/local/bin",
    "/usr/local/sbin",
    "/usr/bin",
    "/usr/sbin",
    "/bin",
    "/sbin",
    "/opt",
)

# Defence in depth: even if a roots list is wrong later, nothing under a prefix the
# agent can write is ever recorded as image-owned.
AGENT_WRITABLE_ROOTS: tuple[str, ...] = (
    "/home/pentester",
    "/workspace",
    "/tmp",  # noqa: S108 - a path prefix to exclude, not a temp file we create
    "/var/tmp",  # noqa: S108 - same
)


def is_agent_writable(path: str | Path) -> bool:
    """True when ``path`` sits under a prefix the agent user can write.

    Resolves first: a symlink under an image root pointing at an agent-writable
    target is agent-writable, and the lexical spelling hides that.
    """
    lexical = Path(path)
    resolved = lexical.resolve()
    resolved_roots = tuple(Path(root) for root in AGENT_WRITABLE_ROOTS)
    resolved_roots += tuple(root.resolve() for root in resolved_roots)
    for candidate in (lexical, resolved):
        if any(candidate == root or candidate.is_relative_to(root) for root in resolved_roots):
            return True
    return False


IMAGE_INVENTORY_COMMAND: tuple[str, ...] = (
    FIND_BINARY,
    *IMAGE_ROOTS,
    "-maxdepth",
    "3",
    "-type",
    "f",
    "-perm",
    "-u+x",
    "-print",
)


# The inventory probe: the same discovery `find` runs, then each line realpath'd
# *inside* the container, so the seed records the spelling the container's own
# filesystem resolves to. Kali is usrmerged: `/bin` is a symlink to `/usr/bin`, and
# a listing that records only the physical spelling leaves the gate's `/bin/ls`
# lookup on a different ledger key (the integration replay's alias defect).
INVENTORY_SCRIPT = r"""
# apf-image-inventory
import json, os, subprocess, sys

args = sys.argv[1:]
if args and args[0] == "--":
    args = args[1:]
find_binary, roots = args[0], args[1:]
proc = subprocess.run(
    # ``-L``: follow symlinked roots. Without it GNU/BSD find default to ``-P``,
    # so a usrmerged ``/bin`` (a symlink to ``/usr/bin``) is never traversed and
    # no alias-spelled path ever reaches the pairs — the dual-key recording then
    # never fires (third replay pass, measured: 317 pairs, zero /bin-spelled).
    [find_binary, "-L", *roots, "-maxdepth", "3", "-type", "f", "-perm", "-u+x", "-print"],
    capture_output=True,
    text=True,
)
pairs = []
for line in proc.stdout.splitlines():
    path = line.strip()
    if not path.startswith("/"):
        continue
    try:
        pairs.append([path, os.path.realpath(path)])
    except OSError:
        pairs.append([path, path])
print(json.dumps(pairs))
"""


def parse_inventory_pairs(stdout: str) -> tuple[tuple[str, str], ...] | None:
    """Parse the canonicalizing inventory probe. ``None`` when unusable.

    Each item is a ``[spelling, realpath]`` pair; anything else is dropped. A
    listing that parses to zero pairs is a failed seed, not an empty image, and
    the caller treats it that way.
    """
    try:
        raw = json.loads(stdout)
    except (ValueError, TypeError):
        return None
    if not isinstance(raw, list):
        return None
    pairs: list[tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, list) or len(item) != 2:
            continue
        spelling, canonical = item
        if not isinstance(spelling, str) or not spelling.startswith("/"):
            continue
        if not isinstance(canonical, str) or not canonical.startswith("/"):
            canonical = spelling
        pairs.append((spelling, canonical))
    return tuple(pairs)


def seed_inventory(ledger: ProvenanceLedger, pairs: Iterable[tuple[str, str]]) -> int:
    """Record each inventory pair as image-sourced under **canonical and alias keys**.

    The canonical key is what the container's own realpath resolves to; the alias
    key is the listing's spelling when it differs. The gate resolves a path on the
    host process, which cannot see a container symlink, so both keys must hit the
    same envelope — otherwise `/bin/ls` (the gate's spelling) and `/usr/bin/ls`
    (the inventory's) are two different files to the ledger (round-31 alias defect).
    """
    seeded = 0
    for spelling, canonical in pairs:
        if is_agent_writable(spelling) or is_agent_writable(canonical):
            continue
        canonical_key = Path(canonical)
        envelope = _image_envelope(canonical_key)
        ledger.record_key(canonical_key, envelope)
        if Path(spelling) != canonical_key:
            ledger.record_key(Path(spelling), envelope)
        seeded += 1
    return seeded


def parse_executable_listing(stdout: str) -> tuple[Path, ...]:
    """Turn a newline-separated `find` listing into artifact paths. Pure."""
    seen: dict[Path, None] = {}
    for line in stdout.splitlines():
        entry = line.strip()
        if not entry.startswith("/"):
            continue
        seen.setdefault(Path(entry), None)
    return tuple(seen)


def seed_paths(ledger: ProvenanceLedger, paths: Iterable[str | Path]) -> int:
    """Record an explicit path list as image-sourced. Returns the count.

    Paths under an agent-writable prefix are skipped: the image cannot vouch for
    content the agent can rewrite.
    """
    seeded = 0
    for raw in paths:
        if is_agent_writable(raw):
            continue
        ledger.record(Path(raw).resolve(), _image_envelope(Path(raw)))
        seeded += 1
    return seeded


def default_image_roots(path_env: str) -> tuple[Path, ...]:
    """The `PATH` directories, deduplicated and canonicalized."""
    seen: dict[Path, None] = {}
    for entry in path_env.split(":"):
        if not entry.strip():
            continue
        seen.setdefault(canonical_path(entry.strip()), None)
    return tuple(seen)
