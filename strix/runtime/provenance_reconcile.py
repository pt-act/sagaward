"""Run the scratch reconciliation against a live sandbox session.

One bounded ``find`` after a shell command returns, through the shell-free
observation channel (``provenance_exec``): argv-form with absolute binaries, so
the model's own ``sh`` is not the instrument's interpreter. A failure is not
hidden: the files stay unrecorded, they read as misses, and later executions of
them are denied — the safe direction. What must not happen is a *silent*
failure, so a missed reconciliation returns ``None`` and the caller counts it.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from strix.core.provenance.content import ABSENT
from strix.core.provenance.reconcile import (
    QUARANTINE_PROBE_SCRIPT,
    RECONCILE_COMMAND,
    RECONCILE_MAX_ENTRIES,
    artifacts_in_quarantine_listing,
    artifacts_in_scratch_listing,
    quarantine_command,
    record_quarantine_artifacts,
    record_scratch_artifacts,
)
from strix.runtime.provenance_exec import (
    ENV_BINARY,
    OBSERVATION_BINARIES,
    OBSERVATION_ENV,
    PYTHON_BINARY,
    SANITIZED_ENV,
    assert_observation_binaries_not_agent_writable,
    observation_exec,
)
from strix.runtime.provenance_install import (
    install_action_id,
    install_trigger,
    reconcile_install_prefixes,
)


logger = logging.getLogger(__name__)

RECONCILE_TIMEOUT_SECONDS = 30
ABSENT_MARKER = "ABSENT"
UNREADABLE_MARKER = "UNREADABLE"
SYMLINK_MARKER = "SYMLINK"
RECONCILE_ARGV: tuple[str, ...] = (*OBSERVATION_ENV, *RECONCILE_COMMAND)


QUARANTINE_MAX_PAGES = 50


async def _quarantine_page(
    session: Any,
    ledger: Any,
    cursor: str | None,
) -> tuple[int, tuple[tuple[Any, str], ...]] | None:
    """Record one page and return ``(recorded, entries)``; ``None`` = unobserved."""
    argv = (
        *OBSERVATION_ENV,
        PYTHON_BINARY,
        "-c",
        QUARANTINE_PROBE_SCRIPT,
        "--",
        *quarantine_command(cursor, RECONCILE_MAX_ENTRIES),
    )
    observation = await observation_exec(session, argv, timeout=RECONCILE_TIMEOUT_SECONDS)
    if observation is None or not observation.ok:
        return None
    parsed = artifacts_in_quarantine_listing(observation.stdout)
    if parsed is None:
        return None
    return record_quarantine_artifacts(ledger, parsed), parsed


async def reconcile_quarantine(session: Any, ledger: Any) -> int | None:
    """Sweep quarantine and record everything there as engagement-tainted.

    Runs **before** the scratch walk so a same-command `cp` out of quarantine
    matches an already-indexed digest (checkpoint-1b R2 / N2). Pages by a
    lexicographic path cursor past the entry cap — the probe sorts globally
    before slicing, so a page boundary cannot skip a file — and stops when a page
    is short or the page bound is reached (round-16 residual: a 20,001-file
    quarantine truncated at 20k and the payload's digest went unindexed).
    """
    cursor: str | None = None
    total = 0
    for _page in range(QUARANTINE_MAX_PAGES):
        result = await _quarantine_page(session, ledger, cursor)
        if result is None:
            logger.warning(
                "Provenance quarantine sweep returned no usable page; quarantine contents "
                "stay unrecorded and copies out of it will read as model-authored",
            )
            return None
        recorded, entries = result
        total += recorded
        if len(entries) < RECONCILE_MAX_ENTRIES:
            return total
        # The probe's page is globally sorted, so its last path is the cursor.
        cursor = str(entries[-1][0])
    logger.warning(
        "Provenance quarantine sweep hit its page bound (%d pages); files beyond it stay "
        "unindexed until the next sweep",
        QUARANTINE_MAX_PAGES,
    )
    return total


async def reconcile_scratch(session: Any, ledger: Any) -> int | None:
    """Observe scratch and record new artifacts. ``None`` means the observation failed."""
    observation = await observation_exec(
        session,
        RECONCILE_ARGV,
        timeout=RECONCILE_TIMEOUT_SECONDS,
    )
    if observation is None or not observation.ok:
        logger.warning(
            "Provenance scratch reconciliation returned %s (stderr=%r); "
            "newly written files will read as PROVENANCE_MISS",
            "no reading" if observation is None else "a non-zero exit",
            "" if observation is None else observation.stderr,
        )
        return None

    return record_scratch_artifacts(
        ledger,
        artifacts_in_scratch_listing(observation.stdout),
        baseline=getattr(ledger, "scratch_baseline", frozenset()),
    )


RECONCILE_FAILURE_LIMIT = 3


def _reconcile_state(context: dict[str, Any]) -> dict[str, Any]:
    state = context.get("provenance_reconcile")
    if not isinstance(state, dict):
        state = {"consecutive_failures": 0, "recorded": 0}
        context["provenance_reconcile"] = state
    return state


def _emit_reconcile_audit(*, ok: bool, recorded: int, consecutive_failures: int) -> None:
    """One audit vocabulary with the harness funnel. Unconfirmed rows are no-ops there,
    so the durable trail for a failure is the warning log plus the escalation."""
    try:
        from strix.report.state import get_global_report_state  # noqa: PLC0415

        report_state = get_global_report_state()
        if report_state is not None:
            report_state.record_harness_run(
                harness_name="apf_provenance",
                verdict="unconfirmed",
                evidence_class="none",
            )
    except Exception:  # noqa: BLE001 - audit must never change a verdict
        logger.debug("apf_provenance audit emit failed", exc_info=True)
    if ok:
        logger.debug("Provenance reconciliation recorded %d scratch artifact(s)", recorded)
        return
    logger.warning(
        "Provenance reconciliation failed (%d consecutive); newly written scratch files "
        "read as PROVENANCE_MISS until the next successful observation",
        consecutive_failures,
    )


async def reconcile_after_exec(
    ctx: Any,
    *,
    command: str | None = None,
    started_ns: int | None = None,
    trigger: str | None = None,
    install_snapshot: dict[Any, str] | None = None,
) -> None:
    """Observe scratch — and install prefixes, after an install — then record.

    A failed observation leaves files unrecorded, which is the safe direction.
    Three consecutive failures escalate to the refusing posture: a silently
    broken reconciler would strangle the engine while looking healthy. The
    install walk shares that counter: a broken install reconciler strangles
    installed tools exactly as a broken scratch reconciler strangles scripts.
    """
    context = getattr(ctx, "context", None)
    if not isinstance(context, dict):
        return
    ledger = context.get("provenance")
    session = context.get("sandbox_session")
    if ledger is None or session is None:
        return

    quarantined = await reconcile_quarantine(session, ledger)
    recorded = await reconcile_scratch(session, ledger)
    if trigger is None and command is not None:
        trigger = install_trigger(command)
    install_like = trigger is not None and command is not None and started_ns is not None
    installed: int | None = 0
    if install_like and command is not None and started_ns is not None and trigger is not None:
        installed = await reconcile_install_prefixes(
            session,
            ledger,
            not_before_ns=started_ns,
            action_id=install_action_id(command),
            trigger=trigger,
            snapshot=install_snapshot,
        )

    failed = quarantined is None or recorded is None or (install_like and installed is None)
    state = _reconcile_state(context)
    if failed:
        state["consecutive_failures"] = int(state.get("consecutive_failures", 0)) + 1
        failures = state["consecutive_failures"]
        _emit_reconcile_audit(ok=False, recorded=0, consecutive_failures=failures)
        if failures >= RECONCILE_FAILURE_LIMIT:
            coordinator = context.get("coordinator")
            reason = (
                "apf-provenance: reconciliation failed "
                f"{failures} consecutive times; refusing to continue with an unobserved "
                "write surface"
            )
            logger.critical(reason)
            if coordinator is not None:
                await coordinator.kill_switch(reason)
        return

    total = (quarantined or 0) + (recorded or 0) + (installed or 0)
    state["consecutive_failures"] = 0
    state["recorded"] = int(state.get("recorded", 0)) + total
    _emit_reconcile_audit(ok=True, recorded=total, consecutive_failures=0)


PROBE_INTERPRETER = PYTHON_BINARY
PROBE_ENV_BINARY = ENV_BINARY
PROBE_ENV = (ENV_BINARY, *SANITIZED_ENV)
PROBE_BINARIES = OBSERVATION_BINARIES

PROBE_SCRIPT = r"""
import hashlib, os, stat, sys

CHUNK = 1 << 20

args = sys.argv[1:]
if args and args[0] == "--":
    args = args[1:]

for path in args:
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        print("ABSENT", 0, path, sep="  ")
        continue
    except OSError:
        # EACCES, ELOOP, ENOTDIR and friends: we cannot say the file is absent.
        print("UNREADABLE", 0, path, sep="  ")
        continue
    if stat.S_ISLNK(st.st_mode):
        # A link is not the file it names. lstat would give the link's mtime while
        # open() reads the target's bytes, so a link created between two probes
        # would attribute someone else's bytes to this path (round 12, R12-ATK).
        print("SYMLINK", st.st_mtime_ns, path, sep="  ")
        continue
    if not os.path.isfile(path):
        print("UNREADABLE", 0, path, sep="  ")
        continue
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(CHUNK), b""):
                digest.update(block)
    except OSError:
        print("UNREADABLE", 0, path, sep="  ")
        continue
    print(digest.hexdigest(), st.st_mtime_ns, path, sep="  ")
"""


def assert_probe_binaries_not_agent_writable() -> None:
    """Refuse to observe through a binary an agent could replace. See the channel module."""
    assert_observation_binaries_not_agent_writable()


async def hash_paths(
    session: Any,
    paths: tuple[Any, ...],
) -> dict[Any, tuple[str | None, int]] | None:
    """Observe each path as ``digest``, ``ABSENT`` (confirmed missing) or ``None`` (unknown).

    ``[ -e ]`` is not a valid existence test here: it is false for EACCES as well
    as ENOENT, so a file inside an unreadable directory would read as ABSENT and a
    no-op patch could bless it. The probe distinguishes the two in Python, emits
    exactly one line per requested path, and never exits non-zero for a per-path
    condition. A path whose ``lstat`` is a link is reported ``SYMLINK`` and folds
    into ``None``: the link's mtime and its target's bytes are different objects,
    and the two probes can straddle the moment a link appears.

    The result is usable as a baseline only if every requested path is accounted
    for; anything short of that is ``None`` (unobserved).
    """
    if not paths:
        return {}
    observation = await observation_exec(
        session,
        (
            *PROBE_ENV,
            PROBE_INTERPRETER,
            "-c",
            PROBE_SCRIPT,
            "--",
            *(str(path) for path in paths),
        ),
        timeout=RECONCILE_TIMEOUT_SECONDS,
    )
    if observation is None or not observation.ok:
        logger.warning(
            "Written-path verification returned %s; paths stay unobserved",
            "no reading" if observation is None else f"exit status (stderr={observation.stderr!r})",
        )
        return None

    observed: dict[Any, tuple[str | None, int]] = {}
    lines = 0
    for line in observation.stdout.splitlines():
        parts = line.split("  ", maxsplit=2)
        if len(parts) != 3:
            continue
        marker, raw_mtime, raw_path = parts
        lines += 1
        path = Path(raw_path)
        try:
            mtime = int(raw_mtime)
        except ValueError:
            continue
        if marker == ABSENT_MARKER:
            observed[path] = (ABSENT, 0)
        elif marker in (UNREADABLE_MARKER, SYMLINK_MARKER):
            # A link is never a write observation: lstat reports the link while
            # open() reports its target, and the two probes can straddle the
            # moment the link appears (round 12, R12-ATK).
            observed[path] = (None, mtime)
        elif len(marker) == 64:
            observed[path] = (marker, mtime)
    requested = [Path(str(path)) for path in paths]
    if (
        lines != len(requested)
        or len(observed) != len(requested)
        or any(path not in observed for path in requested)
    ):
        # Shortfall or duplicate collapse: the observation is not a complete baseline.
        return None
    return observed


async def verify_patch_writes(
    ctx: Any,
    paths: tuple[Any, ...],
) -> dict[Any, tuple[str | None, int]] | None:
    """Observe each touched path. ``None`` = the observation itself failed."""
    context = getattr(ctx, "context", None)
    if not isinstance(context, dict):
        return None
    session = context.get("sandbox_session")
    if session is None:
        return None
    return await hash_paths(session, paths)
