"""Isolation unit — charter 0.2.2 implementation cells (C1/C2 + the four mechanisms).

The pure policy is testable without a daemon; the bring-up assertions run
through the argv-form channel and are exercised with a fake session that answers
the probe scripts. Docker-side mount/cap wiring is asserted through the same
pure functions the client calls, so a drift in either side fails a cell here.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from strix.core.isolation import (
    CapabilityProfile,
    capabilities_for,
    declared_epoch_zero,
    epoch_zero_baseline,
    extra_hosts_for,
    is_baseline_member,
    path_assertion_mismatches,
    quarantine_mount,
    validate_mount_options,
)
from strix.core.provenance import LedgerMiss, ProvenanceEnvelope, ProvenanceLedger
from strix.core.provenance.reconcile import record_scratch_artifacts
from strix.runtime.isolation_bringup import (
    IsolationBringupError,
    assert_bringup_paths,
    scratch_baseline,
)


class _Result:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", code: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = code

    def ok(self) -> bool:
        return self.exit_code == 0


class _Session:
    """Answers the realpath/walk probes the way the container would."""

    def __init__(
        self, *, alias: str | None = None, scratch: list[str] | None = None, raises: bool = False
    ) -> None:
        self._alias = alias
        self._scratch = scratch or []
        self._raises = raises
        self.calls: list[tuple[str, ...]] = []

    async def exec(self, *args: str, **_kwargs: object) -> _Result:
        argv = tuple(str(item) for item in args)
        self.calls.append(argv)
        if self._raises:
            raise RuntimeError("exec unavailable")
        joined = "\n".join(argv)
        if "os.path.realpath" in joined:
            separator = argv.index("--")
            pairs = []
            for spelling in argv[separator + 1 :]:
                resolved = (
                    self._alias
                    if (self._alias and spelling.endswith("/quarantine"))
                    else os.path.realpath(spelling)
                )
                pairs.append([spelling, resolved])
            return _Result(json.dumps(pairs).encode())
        if "os.walk" in joined:
            return _Result(json.dumps(self._scratch).encode())
        return _Result(b"")


class TestProfiles:
    def test_default_grants_nothing(self) -> None:
        assert capabilities_for(CapabilityProfile.DEFAULT) == ()
        assert extra_hosts_for(CapabilityProfile.DEFAULT) == {}

    def test_raw_sockets_grants_net_raw_only(self) -> None:
        assert capabilities_for("raw_sockets") == ("NET_RAW",)

    def test_net_admin_is_never_granted(self) -> None:
        for profile in CapabilityProfile:
            assert "NET_ADMIN" not in capabilities_for(profile)

    def test_an_unknown_profile_grants_nothing(self) -> None:
        assert capabilities_for("root") == ()
        assert extra_hosts_for("root") == {}


class TestQuarantineMount:
    def test_the_mount_is_noexec_nosuid_nodev(self) -> None:
        mount = quarantine_mount("scan1", "agent1")
        options = mount.as_kwargs()["driver_config"]["options"]  # type: ignore[index]
        assert mount.target == "/workspace/quarantine"
        assert mount.source == "strix-quarantine-scan1-agent1"
        for option in ("noexec", "nosuid", "nodev"):
            assert option in str(options["o"]).split(",")

    def test_the_daemon_required_options_are_present(self) -> None:
        """Round 1: the local driver rejects the mount without type/device."""
        mount = quarantine_mount("s", "a")
        options = mount.as_kwargs()["driver_config"]["options"]  # type: ignore[index]

        assert options["type"] == "tmpfs"
        assert options["device"] == "tmpfs"

    def test_a_mount_missing_an_option_is_refused(self) -> None:
        with pytest.raises(ValueError, match="noexec"):
            validate_mount_options("nosuid,nodev")

    def test_valid_mount_passes(self) -> None:
        validate_mount_options(quarantine_mount("s", "a").options)

    def test_the_size_cap_is_part_of_the_mount(self) -> None:
        """R3: tmpfs has no backing disk, so the cap is declared in the mount."""
        options = quarantine_mount("s", "a").options
        assert "size=512m" in options.split(",")

    def test_a_mount_without_a_size_contract_is_refused(self) -> None:
        with pytest.raises(ValueError, match="no size contract"):
            validate_mount_options("noexec,nosuid,nodev")

    @pytest.mark.parametrize("size", ["size=1m", "size=8g"])
    def test_a_size_outside_the_declared_bounds_is_refused(self, size: str) -> None:
        with pytest.raises(ValueError, match="outside"):
            validate_mount_options(f"noexec,nosuid,nodev,{size}")

    def test_an_operator_override_within_bounds_is_accepted(self) -> None:
        mount = quarantine_mount("s", "a", size_bytes=1024 * 1024 * 1024)
        assert "size=1024m" in mount.options.split(",")
        validate_mount_options(mount.options)


class TestPathAssertions:
    def test_identity_holds(self, tmp_path: Path) -> None:
        assert path_assertion_mismatches([(str(tmp_path), str(tmp_path))]) == ()

    def test_an_alias_fails(self, tmp_path: Path) -> None:
        alias = tmp_path / "link"
        alias.symlink_to(tmp_path)
        mismatches = path_assertion_mismatches([(str(alias), str(tmp_path))])
        assert len(mismatches) == 1


class TestEpochZero:
    def test_empty_scratch_declares_empty(self) -> None:
        declaration = declared_epoch_zero([])
        assert declaration == {"epoch_zero": True, "baseline_count": 0, "semantics": "empty"}

    def test_preexisting_content_declares_a_deny_baseline(self) -> None:
        baseline = epoch_zero_baseline(["/workspace/scratch/old.py"])
        declaration = declared_epoch_zero(["/workspace/scratch/old.py"])
        assert declaration["semantics"] == "deny-baseline"
        assert is_baseline_member("/workspace/scratch/old.py", baseline) is True
        assert is_baseline_member("/workspace/scratch/new.py", baseline) is False

    def test_the_reconciler_leaves_baseline_members_as_misses(self) -> None:
        ledger = ProvenanceLedger()
        old = Path("/workspace/scratch/old.py")
        new = Path("/workspace/scratch/new.py")

        recorded = record_scratch_artifacts(
            ledger,
            [(old, "a" * 64), (new, "b" * 64)],
            baseline={old},
        )

        assert recorded == 1
        assert ledger.lookup(old) is LedgerMiss.MISS
        assert isinstance(ledger.lookup(new), ProvenanceEnvelope)


class TestBringUpAssertions:
    def test_matching_paths_pass(self) -> None:
        asyncio.run(assert_bringup_paths(_Session()))

    def test_quarantine_inside_scratch_aborts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Round-1 fence-override: a realpath-clean config can still be exec-capable scratch."""
        from strix.core.provenance import paths as provenance_paths  # noqa: PLC0415

        monkeypatch.setattr(
            provenance_paths, "QUARANTINE_DIR", Path("/workspace/scratch/downloads")
        )
        with pytest.raises(IsolationBringupError, match=r"quarantine .* is inside scratch"):
            asyncio.run(assert_bringup_paths(_Session()))

    def test_scratch_inside_quarantine_aborts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from strix.core.provenance import paths as provenance_paths  # noqa: PLC0415

        monkeypatch.setattr(provenance_paths, "QUARANTINE_DIR", Path("/workspace"))
        with pytest.raises(IsolationBringupError, match=r"scratch .* is inside quarantine"):
            asyncio.run(assert_bringup_paths(_Session()))

    def test_an_aliased_quarantine_aborts(self, tmp_path: Path) -> None:
        alias = tmp_path / "quarantine-alias"
        alias.symlink_to(tmp_path) if not alias.exists() else None
        session = _Session(alias=str(alias))
        with pytest.raises(IsolationBringupError, match="bring-up path assertion failed"):
            asyncio.run(assert_bringup_paths(session))

    def test_an_unobservable_probe_aborts(self) -> None:
        with pytest.raises(IsolationBringupError, match="could not be observed"):
            asyncio.run(assert_bringup_paths(_Session(raises=True)))

    def test_an_empty_scratch_is_an_empty_baseline(self) -> None:
        assert asyncio.run(scratch_baseline(_Session(scratch=[]))) == frozenset()

    def test_preexisting_scratch_is_the_baseline(self) -> None:
        baseline = asyncio.run(scratch_baseline(_Session(scratch=["/workspace/scratch/old.py"])))
        assert baseline == frozenset({Path("/workspace/scratch/old.py")})

    def test_an_unusable_baseline_is_empty_not_clean(self) -> None:
        """A failed probe leaves the baseline empty, and the reconciler's
        content check still gates what gets recorded; nothing is blessed here."""

        class _Broken(_Session):
            async def exec(self, *_a: str, **_k: object) -> _Result:
                return _Result(b"not json")

        assert asyncio.run(scratch_baseline(_Broken())) == frozenset()


class TestPerAgentKeying:
    def test_two_agents_never_share_a_key(self) -> None:
        from strix.core.isolation import session_key  # noqa: PLC0415

        assert session_key("scan1", "a") != session_key("scan1", "b")
        assert session_key("scan1", None) == "scan1:root"
        assert session_key("scan1", "a") == "scan1:a"


class TestSourceInvariants:
    """Textual cells: the wiring lives in modules the SDK blocks us from importing."""

    def test_the_tool_user_is_pinned(self) -> None:
        source = Path("strix/agents/factory.py").read_text()
        assert 'run_as = "pentester"' in source
        assert 'run_as = "pentester" if' not in source

    def test_the_dev_image_grants_no_sudo(self) -> None:
        dockerfile = Path("containers/Dockerfile").read_text()
        assert "NOPASSWD" not in dockerfile
        assert "usermod -aG sudo" not in dockerfile

    def test_the_client_never_grants_net_admin(self) -> None:
        """The old unconditional loop granted both caps on every container."""
        source = Path("strix/runtime/docker_client.py").read_text()
        assert 'for cap in ("NET_ADMIN", "NET_RAW")' not in source
        assert "capabilities_for(" in source
