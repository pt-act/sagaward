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
import re
import shlex
from pathlib import Path
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
from strix.runtime.provenance_exec import OBSERVATION_ENV, PYTHON_BINARY, observation_exec


if TYPE_CHECKING:
    from strix.core.provenance.ledger import ProvenanceLedger


logger = logging.getLogger(__name__)

INSTALL_TIMEOUT_SECONDS = 120

# Declared (program, verb) pair -> trigger key. The trigger key names its roots
# in core's TRIGGER_PREFIXES; the pair is only the parseable spelling. A manager
# that installs outside this table is not reconciled; its files stay misses until
# the table is extended (a spec revision, not a code commit).
_INSTALL_PAIRS: dict[tuple[str, str], str] = {
    ("uv", "pip"): "uv-pip",
    ("poetry", "add"): "poetry-add",
    ("npm", "install"): "npm-install",
    ("npm", "i"): "npm-install",
    ("npm", "ci"): "npm-ci",
    ("yarn", "add"): "yarn-add",
    ("yarn", "install"): "yarn-add",
    ("pnpm", "add"): "pnpm-add",
    ("pnpm", "install"): "pnpm-add",
    ("gem", "install"): "gem-install",
    ("cargo", "install"): "cargo-install",
    ("go", "install"): "go-install",
    ("apt-get", "install"): "apt-get-install",
    ("apt", "install"): "apt-install",
    ("dpkg", "-i"): "dpkg-install",
    ("conda", "install"): "conda-install",
    ("micromamba", "install"): "micromamba-install",
    ("apk", "add"): "apk-add",
    ("brew", "install"): "brew-install",
}

_PIP_NAME = re.compile(r"pip3?(?:\.\d+)?$")
_PYTHON_NAME = re.compile(r"(?:python|pypy)\d*(?:\.\d+)?$")


def install_action_id(command: str) -> str:
    """Stable id for the install action while the gate owns no action ids yet."""
    return hashlib.sha256(command.encode("utf-8", errors="replace")).hexdigest()[:16]


def _is_assignment(token: str) -> bool:
    name, sep, _value = token.partition("=")
    if not sep or not name or token.startswith("-"):
        return False
    return name.replace("_", "").isalnum()


def command_tokens(command: str) -> tuple[str, ...]:
    """Tokenise the command, dropping leading ``VAR=value`` assignments.

    A command that will not lex is not guessed at: no tokens means no trigger,
    which leaves installed files as misses rather than reconciling on a guess.
    """
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return ()
    start = 0
    while start < len(tokens) and _is_assignment(tokens[start]):
        start += 1
    return tuple(tokens[start:])


def _verb_index(tokens: tuple[str, ...]) -> int | None:
    """Index of the first token that is not an option.

    Options *before* the verb are skipped when they are pure flags (`-q`,
    `--quiet`) or carry their value inline (`--prefix=/opt/x`). An option whose
    value is a separate token (`npm --prefix /opt/app install`) makes that value
    look like a verb, so the shape misses the trigger — a miss (deny), named in
    the spec rather than guessed at.
    """
    for index, item in enumerate(tokens):
        if item == "--":
            continue
        if not item.startswith("-"):
            return index
    return None


def install_trigger(command: str) -> str | None:
    """The declared trigger key for this command, or None. A trigger, never a verdict."""
    tokens = command_tokens(command)
    if len(tokens) < 2:
        return None
    head = Path(tokens[0]).name
    rest = tokens[1:]
    if _PIP_NAME.match(head):
        verb = _verb_index(rest)
        return "pip" if verb is not None and rest[verb] == "install" else None
    if _PYTHON_NAME.match(head):
        if len(tokens) >= 4 and tokens[1] == "-m" and tokens[2] == "pip":
            return "pip" if "install" in tokens[3:] else None
        return None
    # The verb is normally the first non-option token, but option-verbs exist
    # (`dpkg -i`), so the literal second token is tried too.
    candidates: list[str] = []
    verb = _verb_index(rest)
    if verb is not None:
        candidates.append(rest[verb])
    candidates.append(rest[0])
    for candidate in candidates:
        trigger = _INSTALL_PAIRS.get((head, candidate))
        if trigger is not None:
            return trigger
    return None


def looks_like_install(command: str) -> bool:
    """True for the declared install-command shapes."""
    return install_trigger(command) is not None


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
