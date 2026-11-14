"""In-container bring-up assertions for the isolation unit (C1/C2).

Two facts must be true before any agent action, and neither can be checked from
the host: the paths the fence compares against must *be* the paths the container
sees, and the scratch tree must start empty (or declare the pre-existing
baseline it did not author).

The check runs through the same argv-form observation channel the provenance
unit uses — ``shell=False``, absolute registered binaries, no interpreter the
agent can shadow — because an assertion made through a shell the agent controls
is not an assertion.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from sagaward.core.isolation import (
    QUARANTINE_MOUNT_TARGET,
    SCRATCH_MOUNT_TARGET,
    declared_epoch_zero,
    fence_override_violations,
    path_assertion_mismatches,
)
from sagaward.core.provenance import paths as provenance_paths
from sagaward.core.provenance import reconcile as provenance_reconcile
from sagaward.core.provenance import writes as provenance_writes
from sagaward.runtime.provenance_exec import OBSERVATION_ENV, PYTHON_BINARY, observation_exec


logger = logging.getLogger(__name__)

BRINGUP_TIMEOUT_SECONDS = 30
SCRATCH_BASELINE_MAX_ENTRIES = 20_000

PATHS_PROBE = r"""
import json, os, sys

args = sys.argv[1:]
if args and args[0] == "--":
    args = args[1:]
print(json.dumps([[p, os.path.realpath(p)] for p in args]))
"""

SCRATCH_PROBE = r"""
import json, os, sys

args = sys.argv[1:]
if args and args[0] == "--":
    args = args[1:]
root = args[0]
max_entries = int(args[1])
found = []
for dirpath, _dirnames, filenames in os.walk(root):
    for name in filenames:
        if len(found) >= max_entries:
            break
        found.append(os.path.join(dirpath, name))
    if len(found) >= max_entries:
        break
print(json.dumps(found))
"""


class IsolationBringupError(RuntimeError):
    """A bring-up invariant failed; the sandbox must not be used."""


async def _run_probe(session: Any, script: str, args: tuple[str, ...]) -> str | None:
    observation = await observation_exec(
        session,
        (*OBSERVATION_ENV, PYTHON_BINARY, "-c", script, "--", *args),
        timeout=BRINGUP_TIMEOUT_SECONDS,
    )
    if observation is None or not observation.ok:
        return None
    return observation.stdout


def _configured_roots() -> tuple[tuple[str, str], ...]:
    """The configured spelling and the mount target it must resolve to.

    Read from the modules at call time, not captured at import, so a re-pointed
    constant is checked rather than the value this module happened to load.
    """
    return (
        (str(provenance_paths.QUARANTINE_DIR), QUARANTINE_MOUNT_TARGET),
        (str(provenance_reconcile.SCRATCH_ROOT), SCRATCH_MOUNT_TARGET),
        (str(provenance_writes.WORKSPACE_ROOT), str(provenance_writes.WORKSPACE_ROOT)),
    )


async def assert_bringup_paths(session: Any) -> None:
    """Refuse the sandbox when a configured path resolves to something else (C1)."""
    configured = [spelling for spelling, _target in _configured_roots()]
    stdout = await _run_probe(session, PATHS_PROBE, tuple(configured))
    if stdout is None:
        raise IsolationBringupError(
            "bring-up path assertion could not be observed (the observation channel returned "
            "no reading); refusing the sandbox rather than assuming the paths are right",
        )
    try:
        pairs = json.loads(stdout)
    except (ValueError, TypeError) as exc:
        raise IsolationBringupError(
            f"bring-up path assertion returned an unusable listing: {exc}"
        ) from exc
    if not isinstance(pairs, list):
        raise IsolationBringupError("bring-up path assertion returned an unusable listing")
    observed = [
        (str(item[0]), str(item[1])) for item in pairs if isinstance(item, list) and len(item) == 2
    ]
    mismatches = path_assertion_mismatches(observed)
    if mismatches:
        detail = ", ".join(
            f"{assertion.configured} -> {assertion.resolved}" for assertion in mismatches
        )
        raise IsolationBringupError(
            f"bring-up path assertion failed: {detail}. Host-side comparisons assume the "
            "configured spelling is the container's real path; an aliased root is a failed "
            "sandbox.",
        )
    violations = fence_override_violations(
        provenance_paths.QUARANTINE_DIR,
        provenance_reconcile.SCRATCH_ROOT,
    )
    if violations:
        raise IsolationBringupError(
            "bring-up configuration refused: " + "; ".join(violations) + ". A quarantine inside "
            "scratch is exec-capable and the reconciler would bless its downloads.",
        )
    logger.info("Bring-up path assertions hold for %d configured roots", len(configured))


async def scratch_baseline(session: Any) -> frozenset[Path]:
    """Declare the epoch-zero contract: the scratch contents before any agent action (C2).

    An empty result is the ordinary case. Anything else is recorded as a
    *deny-baseline*: those paths stay ledger misses, so the gate denies them
    instead of the reconciler attributing a previous epoch's files to this one.
    """
    stdout = await _run_probe(
        session,
        SCRATCH_PROBE,
        (str(provenance_reconcile.SCRATCH_ROOT), str(SCRATCH_BASELINE_MAX_ENTRIES)),
    )
    if stdout is None:
        logger.warning(
            "Epoch-zero probe returned no reading; declaring an EMPTY baseline is unsafe, so the "
            "scratch contents stay unrecorded and will read as PROVENANCE_MISS",
        )
        return frozenset()
    try:
        entries = json.loads(stdout)
    except (ValueError, TypeError):
        logger.warning("Epoch-zero probe returned an unusable listing; scratch stays unrecorded")
        return frozenset()
    if not isinstance(entries, list):
        return frozenset()
    baseline = frozenset(Path(str(entry)) for entry in entries if isinstance(entry, str))
    declaration = declared_epoch_zero(baseline)
    if declaration["epoch_zero"]:
        logger.info("Epoch-zero contract: scratch is empty")
    else:
        logger.warning(
            "Epoch-zero contract: scratch holds %d pre-existing entr(ies); they are declared a "
            "deny-baseline and will not be recorded as model-authored",
            declaration["baseline_count"],
        )
    return baseline
