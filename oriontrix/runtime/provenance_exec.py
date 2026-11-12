"""The in-sandbox observation channel: argv-form exec, never a shell.

Every observation this program makes of the sandbox — the write probe, the
scratch walk, the image inventory — travels through here. The SDK's
``SandboxSession.exec`` defaults to ``shell=True`` and prepares
``["sh", "-lc", shlex.join(argv)]`` (openai-agents==0.14.6,
``session/base_sandbox_session.py:505-532``). On that default an agent-writable
``sh`` earlier on ``PATH`` receives the whole command line, so sanitizing the
payload inside the shell sanitizes the argument list of a process the agent
already controls. ``shell=False`` hands the argv to ``container.exec_run(cmd=[...])``
(``sandboxes/docker.py:417-436``), where the container engine execs the absolute
program directly: no interpreter to shadow, no PATH lookup, no word splitting.

One choke point, so a call site cannot forget the posture:

- argv-form only, never a shell interpreter as the program;
- absolute binaries only, from a closed set registered in ``OBSERVATION_BINARIES``,
  with a sanitized environment for every one of them;
- an agent-writable-prefix assertion over every binary in the chain (a constant
  drift guard: it checks the spellings we ship, not the container's inode);
- bytes decoded at this boundary, because the SDK returns ``bytes`` and a
  ``str``-shaped parse over bytes silently fails.

An observation that cannot be made returns ``None``. ``None`` is never a clean
reading — callers turn it into a miss, and a miss is a deny.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from oriontrix.core.provenance.seed import FIND_BINARY, SHA256SUM_BINARY, is_agent_writable


logger = logging.getLogger(__name__)

ENV_BINARY = "/usr/bin/env"
PYTHON_BINARY = "/usr/bin/python3"
SANITIZED_ENV: tuple[str, ...] = ("-i", "PATH=/usr/bin:/bin", "LC_ALL=C", "TZ=UTC")
OBSERVATION_ENV: tuple[str, ...] = (ENV_BINARY, *SANITIZED_ENV)

# Every binary any observation invokes. The guard below covers this whole set;
# adding a binary to a command without adding it here is the drift it exists for.
OBSERVATION_BINARIES: tuple[str, ...] = (
    ENV_BINARY,
    PYTHON_BINARY,
    FIND_BINARY,
    SHA256SUM_BINARY,
)

SHELL_NAMES: frozenset[str] = frozenset(
    {"sh", "bash", "dash", "zsh", "ksh", "csh", "tcsh", "fish", "busybox"},
)


@dataclass(frozen=True)
class Observation:
    """A completed observation. ``ok`` is the instrument's exit status."""

    stdout: str
    stderr: str
    ok: bool


def _text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def assert_observation_binaries_not_agent_writable() -> None:
    """Refuse to observe through a binary an agent could replace.

    Host-side check over the constants we invoke. It cannot see the container, so
    it is a guard against configuration drift, not proof; the container-side
    dependency is recorded in the spec note and in the manifest's consumes.
    """
    writable = [binary for binary in OBSERVATION_BINARIES if is_agent_writable(binary)]
    if writable:
        raise RuntimeError(
            "apf-provenance: observation binary under an agent-writable prefix: "
            f"{writable}. The probe must not be reachable through a path the subject controls.",
        )


def _programs_in(argv: tuple[str, ...]) -> tuple[str, ...]:
    """The programs an argv will exec: the head, plus the program behind ``env``."""
    head = argv[0]
    if Path(head).name != Path(ENV_BINARY).name:
        return (head,)
    for item in argv[1:]:
        if item == "-i" or item.startswith("-") or "=" in item:
            continue
        return (head, item)
    return (head,)


def assert_observation_argv(argv: tuple[str, ...]) -> None:
    """Refuse an argv a shell could interpret, PATH could resolve, or the set does not name.

    The channel is a closed set: every program must be one of ``OBSERVATION_BINARIES``,
    whose spellings are asserted not agent-writable. That covers the program behind
    ``env`` too, so ``env -S '/bin/sh -c id'`` is refused by the membership rule
    rather than by parsing ``env``'s option grammar. ``python3 -c`` is fine (the
    script is a module constant, not model input); ``sh -c`` is not, because the
    shell itself would be a PATH lookup.
    """
    if not argv:
        raise RuntimeError("apf-provenance: empty observation argv")
    assert_observation_binaries_not_agent_writable()
    for program in _programs_in(argv):
        if not program.startswith("/"):
            raise RuntimeError(
                "apf-provenance: observation program is not an absolute path: "
                f"{program!r} in {argv!r}. A PATH-resolved binary can be shadowed by the agent.",
            )
        if Path(program).name in SHELL_NAMES:
            raise RuntimeError(
                "apf-provenance: observation program is a shell: "
                f"{program!r}. Observations are argv-form and never share an interpreter "
                "with the subject.",
            )
        if program not in OBSERVATION_BINARIES:
            raise RuntimeError(
                "apf-provenance: observation program is not a registered observation binary: "
                f"{program!r} in {argv!r}. The channel is a closed set; a new binary is "
                "registered together with its writable-prefix assertion.",
            )


async def observation_exec(
    session: Any,
    argv: tuple[str, ...],
    *,
    timeout: float | None,
) -> Observation | None:
    """Run one observation argv-form. ``None`` means no trustworthy reading exists."""
    normalized = tuple(str(item) for item in argv)
    assert_observation_argv(normalized)
    logger.debug("apf-provenance observation argv (shell=False): %r", normalized)
    try:
        result = await session.exec(*normalized, shell=False, timeout=timeout)
    except Exception:  # noqa: BLE001 - an unobserved reading must stay unobserved
        logger.warning("Provenance observation failed to execute: %r", normalized[0], exc_info=True)
        return None

    ok_method = getattr(result, "ok", None)
    ok = bool(ok_method()) if callable(ok_method) else getattr(result, "exit_code", 1) == 0
    return Observation(
        stdout=_text(getattr(result, "stdout", None)),
        stderr=_text(getattr(result, "stderr", None)),
        ok=ok,
    )
