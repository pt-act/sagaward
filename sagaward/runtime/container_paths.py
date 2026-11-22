"""In-container path resolution for the classifier (S-5).

The gate's subject is the container, so the container's view of a path is the
one the decision must read. The host process cannot answer it: the same spelling
resolves to a different inode (or to nothing) on the host. This module asks the
container through the observation channel — one argv-form ``observation_exec``
per classification pass — and returns the frozen probes the host-side classifier
decides over.

The probe is a module constant, never model input: ``/usr/bin/python3 -c`` with
the request list as one argv element. The channel's closed-set assertion covers
the binaries; the script is ours.

**The honest limitation.** This verifies what the container's filesystem
*spells* — the resolved path and its inode — not what its *bytes* contain. A
path can resolve to the container's inode and still hold bytes the ledger never
saw. The gap-ledger row for content verification stands; this fix closes the
resolution gap, not the content gap.

A probe that cannot be made returns ``None``. ``None`` is never a clean reading:
the caller installs the refusing resolver, and every path becomes ``UNRESOLVED``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sagaward.core.provenance.artifact import ArtifactRef
from sagaward.core.provenance.classify import (
    PathProbe,
    PathRequest,
    ResolvedPathResolver,
    _unresolved,
)
from sagaward.core.provenance.gate import Resolution, ResolvedTarget
from sagaward.runtime.provenance_exec import OBSERVATION_ENV, PYTHON_BINARY, observation_exec


if TYPE_CHECKING:
    from collections.abc import Sequence


logger = logging.getLogger(__name__)

RESOLVE_TIMEOUT_SECONDS = 30.0

# One line of JSON per request, in request order. ``realpath`` is the container's
# canonical spelling; ``stat`` is the container's inode. A path that does not
# resolve is ``unresolved``; one that resolves but is absent carries no inode.
CONTAINER_PROBE_SCRIPT = r"""
import json, os, shutil, stat, sys

requests = json.loads(sys.argv[1])
out = []
for index, request in enumerate(requests):
    kind = request.get("kind", "path")
    raw = request.get("raw", "")
    if kind == "which":
        found = shutil.which(raw)
        if not found:
            out.append({"index": index, "kind": kind, "raw": raw, "found": False})
            continue
        target = found
    else:
        target = raw
        cwd = request.get("cwd")
        if not os.path.isabs(target):
            target = os.path.join(cwd or os.getcwd(), target)
    try:
        resolved = os.path.realpath(target)
    except OSError:
        out.append({"index": index, "kind": kind, "raw": raw, "resolution": "unresolved"})
        continue
    try:
        status = os.stat(resolved)
    except OSError:
        out.append(
            {"index": index, "kind": kind, "raw": raw, "path": resolved, "exists": False}
        )
        continue
    out.append(
        {
            "index": index,
            "kind": kind,
            "raw": raw,
            "path": resolved,
            "exists": True,
            "executable": bool(status.st_mode & 0o111),
            "is_dir": stat.S_ISDIR(status.st_mode),
            "is_file": stat.S_ISREG(status.st_mode),
            "dev": status.st_dev,
            "ino": status.st_ino,
        }
    )
print(json.dumps(out))
"""


def _probe_from_row(row: dict[str, Any], request: PathRequest) -> PathProbe | None:
    """One container answer as the classifier's frozen probe.

    ``None`` means the container did not find a bare command word (``which``);
    every other shape is a probe, with the refusing shape for an unresolvable
    path.
    """
    if request.kind == "which" and row.get("found") is False:
        return None
    if row.get("resolution") == "unresolved":
        return PathProbe(_unresolved(request.raw), exists=False, executable=False)
    path_text = row.get("path")
    if not isinstance(path_text, str) or not path_text:
        return PathProbe(_unresolved(request.raw), exists=False, executable=False)
    path = Path(path_text)
    exists = bool(row.get("exists"))
    inode: tuple[int, int] | None = None
    if exists:
        dev, ino = row.get("dev"), row.get("ino")
        if isinstance(dev, int) and isinstance(ino, int):
            inode = (dev, ino)
    # A bare word resolves to the path the container found; a path request keeps
    # the spelling the agent wrote (the raw the audit reports).
    raw = path_text if request.kind == "which" else request.raw
    ref = ArtifactRef(raw=raw, path_key=str(path), inode_key=inode)
    return PathProbe(
        ResolvedTarget(raw=raw, path=path, resolution=Resolution.PATH, ref=ref),
        exists=exists,
        executable=bool(row.get("executable")),
        is_dir=bool(row.get("is_dir")),
        is_file=bool(row.get("is_file")),
    )


async def resolve_paths_in_container(
    session: Any,
    requests: Sequence[PathRequest],
    *,
    timeout: float | None = RESOLVE_TIMEOUT_SECONDS,
) -> dict[tuple[str, str | None, str], PathProbe] | None:
    """Resolve every request inside the container; ``None`` when unobservable.

    One observation per pass. An empty request set is a valid empty answer (the
    classifier asked about no paths); a failed or unparseable probe is ``None``,
    which the caller turns into the refusing resolver.
    """
    if not requests:
        return {}
    payload = json.dumps(
        [{"kind": request.kind, "raw": request.raw, "cwd": request.cwd} for request in requests]
    )
    observation = await observation_exec(
        session,
        (*OBSERVATION_ENV, PYTHON_BINARY, "-c", CONTAINER_PROBE_SCRIPT, payload),
        timeout=timeout,
    )
    if observation is None or not observation.ok:
        logger.warning("apf-provenance: in-container path resolution failed")
        return None
    try:
        rows = json.loads(observation.stdout)
    except (TypeError, ValueError):
        logger.warning("apf-provenance: in-container path resolution returned unparseable output")
        return None
    if not isinstance(rows, list):
        return None
    probes: dict[tuple[str, str | None, str], PathProbe] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        index = row.get("index")
        if not isinstance(index, int) or not 0 <= index < len(requests):
            continue
        request = requests[index]
        probe = _probe_from_row(row, request)
        if probe is not None:
            probes[(request.raw, request.cwd, request.kind)] = probe
    return probes


def container_path_resolver(
    probes: dict[tuple[str, str | None, str], PathProbe],
) -> ResolvedPathResolver:
    """The pass-2 resolver over the container's answers."""
    return ResolvedPathResolver(probes)


__all__ = [
    "CONTAINER_PROBE_SCRIPT",
    "RESOLVE_TIMEOUT_SECONDS",
    "container_path_resolver",
    "resolve_paths_in_container",
]
