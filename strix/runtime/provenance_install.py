"""Trigger and run the post-install reconciliation.

Only a command that installs something is worth a prefix walk; the walk is
bounded but not free. The trigger is a **declared command table**, and its scope
is stated where it is defined: it decides *whether to look*, never a verdict. A
missed trigger leaves installed files as ledger misses, which is the refusing
direction — the gate then denies the tool the install was for, loudly.

The walk itself runs through the argv-form observation channel, in-process in the
container, and returns JSON. The install action id (the command digest until the
gate supplies its own) is written into the reconciliation log line the same way
the scratch reconciler logs its counts.
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any

from strix.core.provenance.install import (
    INSTALL_MAX_DEPTH,
    INSTALL_MAX_ENTRIES,
    INSTALL_PROBE_SCRIPT,
    INSTALL_SNAPSHOT_SCRIPT,
    parse_install_listing,
    parse_snapshot_listing,
    prefixes_for_trigger,
    record_install_artifacts,
)
from strix.core.provenance.install_grammar import (  # one grammar; re-exported below
    _INSTALL_PAIRS,
    _PIP_NAME,
    _PYTHON_NAME,
    _verb_index,
    command_tokens,
    install_trigger,
    looks_like_install,
)
from strix.runtime.provenance_exec import OBSERVATION_ENV, PYTHON_BINARY, observation_exec


if TYPE_CHECKING:
    from pathlib import Path

    from strix.core.provenance.ledger import ProvenanceLedger


# Re-exports: the grammar moved to core (apf-action-gate G2a); existing
# importers of these names keep working.
__all__ = [
    "_INSTALL_PAIRS",
    "_PIP_NAME",
    "_PYTHON_NAME",
    "_verb_index",
    "command_tokens",
    "install_trigger",
    "looks_like_install",
]

logger = logging.getLogger(__name__)

INSTALL_TIMEOUT_SECONDS = 120


def install_action_id(command: str) -> str:
    """Stable id for the install action while the gate owns no action ids yet."""
    return hashlib.sha256(command.encode("utf-8", errors="replace")).hexdigest()[:16]


async def snapshot_install_prefixes(
    session: Any,
    trigger: str,
) -> dict[Path, str] | None:
    """Digest snapshot of the trigger's write roots, taken before the install runs.

    ``None`` means the truth path is unavailable; the caller logs it and the time
    path stands alone.
    """
    argv = (
        *OBSERVATION_ENV,
        PYTHON_BINARY,
        "-c",
        INSTALL_SNAPSHOT_SCRIPT,
        "--",
        str(INSTALL_MAX_DEPTH),
        str(INSTALL_MAX_ENTRIES),
        *prefixes_for_trigger(trigger),
    )
    observation = await observation_exec(session, argv, timeout=INSTALL_TIMEOUT_SECONDS)
    if observation is None or not observation.ok:
        logger.warning(
            "Install snapshot for trigger %s failed; the install walk will fall back to the "
            "mtime path for this action",
            trigger,
        )
        return None
    return parse_snapshot_listing(observation.stdout)


async def reconcile_install_prefixes(
    session: Any,
    ledger: ProvenanceLedger,
    *,
    not_before_ns: int,
    action_id: str,
    trigger: str,
    snapshot: dict[Path, str] | None = None,
) -> int | None:
    """Observe the declared prefixes and record what the install created.

    ``None`` means the observation failed; callers count it exactly like a failed
    scratch reconciliation, because the consequence is the same — installed files
    stay misses and the gate will deny them.
    """
    argv = (
        *OBSERVATION_ENV,
        PYTHON_BINARY,
        "-c",
        INSTALL_PROBE_SCRIPT,
        "--",
        str(not_before_ns),
        str(INSTALL_MAX_DEPTH),
        str(INSTALL_MAX_ENTRIES),
        *prefixes_for_trigger(trigger),
    )
    observation = await observation_exec(session, argv, timeout=INSTALL_TIMEOUT_SECONDS)
    if observation is None or not observation.ok:
        logger.warning(
            "Install-prefix reconciliation failed for action %s; installed files will "
            "read as PROVENANCE_MISS",
            action_id,
        )
        return None
    parsed = parse_install_listing(observation.stdout)
    if parsed is None:
        logger.warning(
            "Install-prefix listing was not usable for action %s; installed files stay misses",
            action_id,
        )
        return None
    if snapshot is None:
        logger.warning(
            "Install snapshot unavailable for action %s; attributing nothing (files stay misses)",
            action_id,
        )
        return 0
    recorded = record_install_artifacts(
        ledger,
        parsed,
        not_before_ns=not_before_ns,
        prefixes=prefixes_for_trigger(trigger),
        snapshot=snapshot,
    )
    logger.info(
        "Install-prefix reconciliation for action %s recorded %d file(s)",
        action_id,
        recorded,
    )
    return recorded
