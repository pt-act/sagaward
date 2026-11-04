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
    """Record every executable under ``roots`` as image-sourced. Returns the count."""
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
