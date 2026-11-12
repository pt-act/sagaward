"""Sandbox isolation policy — pure decisions, no Docker and no SDK.

This unit's job is to make the sandbox a boundary the provenance channel can be
trusted inside: capability profiles instead of a constant grant, a quarantine
mount with ``noexec,nosuid,nodev`` instead of a directory in the agent's own
writable tree, bring-up path assertions instead of assumed spellings, and an
epoch-zero contract instead of blessing whatever a previous epoch left behind.

Everything here is a pure function over strings and small dataclasses so the
policy is testable without a daemon; the wiring lives in
``oriontrix/runtime/docker_client.py`` (mounts/caps), ``oriontrix/agents/factory.py``
(the tool user) and ``oriontrix/runtime/isolation_bringup.py`` (the in-container
assertions).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from collections.abc import Iterable


class CapabilityProfile(StrEnum):
    """The declared tool profiles. There is no other way to obtain a capability."""

    DEFAULT = "default"
    RAW_SOCKETS = "raw_sockets"


# The one capability each profile may add. Everything not listed is never added.
PROFILE_CAPABILITIES: dict[CapabilityProfile, tuple[str, ...]] = {
    CapabilityProfile.DEFAULT: (),
    CapabilityProfile.RAW_SOCKETS: ("NET_RAW",),
}

# host.docker.internal is a capability in practice: it reaches the host. Only the
# profile that explicitly needs a host-routed service gets it.
PROFILE_EXTRA_HOSTS: dict[CapabilityProfile, dict[str, str]] = {
    CapabilityProfile.DEFAULT: {},
    CapabilityProfile.RAW_SOCKETS: {},
}


def capabilities_for(profile: CapabilityProfile | str) -> tuple[str, ...]:
    """The cap_add entries for a profile; an unknown profile gets none."""
    try:
        key = CapabilityProfile(profile)
    except ValueError:
        return ()
    return PROFILE_CAPABILITIES[key]


def extra_hosts_for(profile: CapabilityProfile | str) -> dict[str, str]:
    """The extra_hosts entries for a profile; an unknown profile gets none."""
    try:
        key = CapabilityProfile(profile)
    except ValueError:
        return {}
    return dict(PROFILE_EXTRA_HOSTS[key])


# The quarantine mount, realized at the mount: noexec/nosuid/nodev on a tmpfs
# volume. A chmod can be undone by the agent; a mount option cannot.
#
# The local driver rejects an option set without ``device`` (round-1 verdict:
# the daemon answers "missing required option: device" at container creation).
# The measured valid form is a tmpfs-backed volume: type=tmpfs, device=tmpfs,
# o=noexec,nosuid,nodev — kernel-enforced regardless of UID.
QUARANTINE_MOUNT_OPTIONS: tuple[str, ...] = ("noexec", "nosuid", "nodev")
QUARANTINE_DRIVER_TYPE = "tmpfs"
QUARANTINE_DRIVER_DEVICE = "tmpfs"

# The sizing contract (R3). A tmpfs has no backing disk: an unbounded fetch fills
# it and the failure surfaces as a mysterious install error instead of a denial.
# The cap is declared, enforced by the mount, and fail-closed: a write past it
# fails (ENOSPC), the file never lands, and nothing is blessed. The operator may
# raise the cap deliberately; the bounds below keep a typo from turning the
# quarantine into host memory.
QUARANTINE_TMPFS_SIZE_BYTES = 512 * 1024 * 1024
QUARANTINE_TMPFS_MIN_BYTES = 64 * 1024 * 1024
QUARANTINE_TMPFS_MAX_BYTES = 4 * 1024 * 1024 * 1024


def _size_option(size_bytes: int) -> str:
    """The tmpfs ``size=`` option, in MiB (tmpfs accepts the suffix)."""
    return f"size={size_bytes // (1024 * 1024)}m"


def quarantine_options(size_bytes: int = QUARANTINE_TMPFS_SIZE_BYTES) -> str:
    """The complete option string the mount carries, sizing included."""
    parts = list(QUARANTINE_MOUNT_OPTIONS)
    parts.append(_size_option(size_bytes))
    return ",".join(parts)


QUARANTINE_MOUNT_TARGET = "/workspace/quarantine"
SCRATCH_MOUNT_TARGET = "/workspace/scratch"


@dataclass(frozen=True, slots=True)
class MountSpec:
    """A Docker volume mount, in the shape docker-py's ``Mount`` accepts."""

    target: str
    source: str
    type: str = "volume"
    driver: str = "local"

    size_bytes: int = QUARANTINE_TMPFS_SIZE_BYTES

    @property
    def options(self) -> str:
        """The comma-joined mount options, as the driver receives them."""
        return quarantine_options(self.size_bytes)

    def as_kwargs(self) -> dict[str, object]:
        """The ``docker.types.Mount`` keyword form.

        ``type``/``device`` are required by the local driver; without them the
        daemon refuses to create the container.
        """
        return {
            "target": self.target,
            "source": self.source,
            "type": self.type,
            "driver_config": {
                "name": self.driver,
                "options": {
                    "type": QUARANTINE_DRIVER_TYPE,
                    "device": QUARANTINE_DRIVER_DEVICE,
                    "o": self.options,
                },
            },
        }


def quarantine_mount(
    scan_id: str,
    agent_id: str,
    size_bytes: int = QUARANTINE_TMPFS_SIZE_BYTES,
) -> MountSpec:
    """One named volume per sandbox epoch, mounted noexec and size-capped.

    The volume is per agent, so a quarantined artifact cannot be read through a
    sibling agent's container, and it dies with the container. The size cap is
    part of the mount, so an oversized fetch fails at the filesystem — the
    refusing direction — instead of filling host memory or truncating silently.
    """
    return MountSpec(
        target=QUARANTINE_MOUNT_TARGET,
        source=f"oriontrix-quarantine-{scan_id}-{agent_id}",
        size_bytes=size_bytes,
    )


def _parse_size(options: str) -> int | None:
    """The declared tmpfs size in bytes, or ``None`` when absent/unparseable."""
    for option in options.split(","):
        key, separator, value = option.strip().partition("=")
        if key != "size" or not separator:
            continue
        match = value.strip().lower()
        multiplier = 1024 * 1024
        if match.endswith("m"):
            match = match[:-1]
        elif match.endswith("g"):
            match, multiplier = match[:-1], 1024 * 1024 * 1024
        try:
            return int(match) * multiplier
        except ValueError:
            return None
    return None


def validate_mount_options(options: str) -> None:
    """Refuse mount options missing a required one — checked on the string Docker gets.

    Also enforces the sizing contract: the cap must be present, at least the
    floor (a cap too small fails legitimate fetches) and at most the ceiling (a
    cap that can swallow host memory is not a cap).
    """
    present = {option.strip() for option in options.split(",") if option.strip()}
    missing = [option for option in QUARANTINE_MOUNT_OPTIONS if option not in present]
    if missing:
        raise ValueError(f"quarantine mount missing {missing}: {options}")
    size = _parse_size(options)
    if size is None:
        raise ValueError(f"quarantine mount has no size contract: {options}")
    if not QUARANTINE_TMPFS_MIN_BYTES <= size <= QUARANTINE_TMPFS_MAX_BYTES:
        raise ValueError(
            f"quarantine size {size} outside "
            f"[{QUARANTINE_TMPFS_MIN_BYTES}, {QUARANTINE_TMPFS_MAX_BYTES}]: {options}",
        )


def session_key(scan_id: str, agent_id: str | None) -> str:
    """The per-agent sandbox cache key: one container per (scan, agent).

    A shared container would let one agent's quarantine and scratch be another's;
    the key is the mechanism that makes "per-agent sandbox" true.
    """
    return f"{scan_id}:{agent_id or 'root'}"


# --- Bring-up path assertions (C1) -------------------------------------------


@dataclass(frozen=True, slots=True)
class PathAssertion:
    """One configured spelling and the container-visible resolution it must equal."""

    configured: str
    resolved: str

    @property
    def holds(self) -> bool:
        return Path(self.configured) == Path(self.resolved)


def fence_override_violations(quarantine: str | Path, scratch: str | Path) -> tuple[str, ...]:
    """Configuration relations C1 must refuse beyond aliasing (round-1 finding).

    ``ORIONTRIX_QUARANTINE_DIR=/workspace/scratch/downloads`` resolves to itself, so a
    realpath comparison is green — but the "quarantine" is then an exec-capable
    scratch subtree, downloads land there, the reconciler records them
    `MODEL_AUTHORED`, and the sweep's taint never applies. The mount target must
    stay outside the scratch tree, and scratch outside quarantine.
    """
    quarantine_path = Path(quarantine)
    scratch_path = Path(scratch)
    violations: list[str] = []
    if quarantine_path == scratch_path or quarantine_path.is_relative_to(scratch_path):
        violations.append(f"quarantine {quarantine_path} is inside scratch {scratch_path}")
    if scratch_path.is_relative_to(quarantine_path):
        violations.append(f"scratch {scratch_path} is inside quarantine {quarantine_path}")
    return tuple(violations)


def path_assertion_mismatches(observations: Iterable[tuple[str, str]]) -> tuple[PathAssertion, ...]:
    """Return the assertions that do not hold.

    ``observations`` is (configured, container-visible resolution) pairs read at
    bring-up. An empty result is the only pass: a mismatch aborts, because every
    host-side comparison in the fence assumes the configured spelling is real.
    """
    return tuple(
        assertion
        for assertion in (PathAssertion(*pair) for pair in observations)
        if not assertion.holds
    )


# --- Epoch-zero contract (C2) ------------------------------------------------


def epoch_zero_baseline(preexisting: Iterable[str | Path]) -> frozenset[Path]:
    """The set of paths that existed in scratch before any agent action.

    Those paths are *pre-existing* — not authored by this epoch — so the
    reconciler must leave them misses (deny) instead of recording them
    `MODEL_AUTHORED`. An empty scratch is an empty baseline and the normal case.
    """
    return frozenset(Path(entry) for entry in preexisting)


def is_baseline_member(path: str | Path, baseline: frozenset[Path]) -> bool:
    """True when a listed path belongs to the pre-existing epoch baseline."""
    return Path(path) in baseline


def declared_epoch_zero(preexisting: Iterable[str | Path]) -> dict[str, object]:
    """The declaration a persistent-volume deployment must log at bring-up."""
    baseline = epoch_zero_baseline(preexisting)
    return {
        "epoch_zero": len(baseline) == 0,
        "baseline_count": len(baseline),
        "semantics": "empty" if not baseline else "deny-baseline",
    }
