"""Bring up the per-sandbox provenance ledger.

The ledger describes the sandbox, so its image inventory must be enumerated
*inside* the sandbox — a host-side walk of the local `PATH` would record paths
the container never had. One `find` at bring-up is enough: everything the image
ships is executable and already on disk before any agent action runs.

Failure is not fatal but it is loud: an unseeded ledger makes every preinstalled
tool a miss, and a miss is a DENY. That is the correct fail-closed posture, but
an operator needs to know why their scan is refusing to run `nmap`.
"""

from __future__ import annotations

import logging
from typing import Any

from strix.core.provenance.ledger import ProvenanceLedger
from strix.core.provenance.seed import (
    IMAGE_INVENTORY_COMMAND,
    IMAGE_ROOTS,
    parse_executable_listing,
    seed_paths,
)
from strix.runtime.isolation_bringup import assert_bringup_paths, scratch_baseline
from strix.runtime.provenance_exec import OBSERVATION_ENV, observation_exec


logger = logging.getLogger(__name__)

INVENTORY_TIMEOUT_SECONDS = 60
INVENTORY_ARGV: tuple[str, ...] = (*OBSERVATION_ENV, *IMAGE_INVENTORY_COMMAND)


async def bring_up_provenance(session: Any) -> ProvenanceLedger:
    """Create the ledger for one sandbox epoch and seed the image's executables.

    Isolation's bring-up assertions run **first** (C1/C2): a sandbox whose
    configured paths do not resolve to themselves, or whose scratch arrives with
    content from a previous epoch, is refused or baselined before the ledger is
    seeded.
    """
    ledger = ProvenanceLedger()
    await assert_bringup_paths(session)
    ledger.scratch_baseline = await scratch_baseline(session)  # type: ignore[attr-defined]
    observation = await observation_exec(
        session,
        INVENTORY_ARGV,
        timeout=INVENTORY_TIMEOUT_SECONDS,
    )
    if observation is None:
        logger.warning(
            "Provenance image inventory failed; the ledger is empty and every "
            "executable will read as unverified (deny-on-miss)",
        )
        return ledger

    if not observation.ok:
        logger.warning(
            "Provenance image inventory returned a non-zero exit; seeding what parsed (stderr=%r)",
            observation.stderr,
        )

    paths = parse_executable_listing(observation.stdout)
    if not paths:
        logger.warning(
            "Provenance image inventory listed zero executables under %s — treating this as a "
            "FAILED seed, not an empty image. Every executable will be a miss, and a miss is a "
            "DENY, so scans in this sandbox will refuse to run tools",
            ", ".join(IMAGE_ROOTS),
        )
        return ledger

    seeded = seed_paths(ledger, paths)
    logger.info("Provenance ledger seeded with %d image-owned executable(s)", seeded)
    return ledger
