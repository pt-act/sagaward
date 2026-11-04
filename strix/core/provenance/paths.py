"""Canonical sandbox paths shared by the action fence.

One definition per path. The quarantine mount in the sandbox and the gate's
``references_quarantine`` rule must compare against the same value, otherwise a
tainted binary and the check that forbids executing it are looking at different
directories.

The constant is **not** resolved at import: this module is imported by the host
process that drives the container, where the sandbox tree does not exist, so an
import-time ``resolve()`` would canonicalise against the wrong filesystem. The
value is compared **both ways** at the point of use instead — the spelling as
configured, and its host-visible resolution — and callers must treat an
unresolvable path as quarantine (refuse). ``STRIX_QUARANTINE_DIR`` is required
to name the canonical *in-container* path; a container-side symlink alias is not
detected here, and that limit is recorded in the gate's gap ledger.
"""

from __future__ import annotations

import os
from pathlib import Path


QUARANTINE_DIR_ENV = "STRIX_QUARANTINE_DIR"
DEFAULT_QUARANTINE_DIR = "/workspace/quarantine"

QUARANTINE_DIR: Path = Path(
    os.environ.get(QUARANTINE_DIR_ENV, "").strip() or DEFAULT_QUARANTINE_DIR,
)


def resolve_or_none(path: str | Path) -> Path | None:
    """``Path.resolve()``, or ``None`` when the filesystem will not answer."""
    try:
        return Path(path).resolve()
    except (OSError, RuntimeError):
        return None


def quarantine_roots() -> tuple[Path, ...]:
    """The quarantine directory as configured and as it resolves, deduplicated."""
    resolved = resolve_or_none(QUARANTINE_DIR)
    if resolved is None or resolved == QUARANTINE_DIR:
        return (QUARANTINE_DIR,)
    return (QUARANTINE_DIR, resolved)


def is_quarantine_path(path: str | Path) -> bool:
    """True when ``path`` is, or resolves to, the quarantine directory.

    Both the spelling and the host-visible resolution of the path are compared
    against both forms of the root, because either side may be the aliased one
    (round 13, R13-QALIAS: a resolved path compared against an unresolved
    constant stored a real quarantine key clean). An unresolvable path is
    treated as quarantine — the refusal direction is the safe one.
    """
    resolved = resolve_or_none(path)
    if resolved is None:
        return True
    candidates = {Path(path), resolved}
    roots = quarantine_roots()
    return any(candidate.is_relative_to(root) for candidate in candidates for root in roots)
