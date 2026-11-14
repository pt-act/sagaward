"""Wiring tests for apf-provenance (AC-10).

Covers the sandbox-epoch bring-up: the ledger is constructed per sandbox, seeded
from the container's own image inventory, and reachable through the run context.

The four tool-boundary entry points (proxy response, browser payload, engagement
mount read, shell fetch into quarantine) are tracked separately; this file grows
as each lands.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from sagaward.core.provenance import (
    LedgerMiss,
    ProvenanceEnvelope,
    ProvenanceLedger,
    Source,
    parse_executable_listing,
    seed_paths,
)
from sagaward.runtime.isolation_bringup import IsolationBringupError
from sagaward.runtime.provenance_bringup import bring_up_provenance


class _Result:
    def __init__(self, stdout: str = "", stderr: str = "", code: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self._code = code

    def ok(self) -> bool:
        return self._code == 0


class _FakeSession:
    def __init__(self, result: _Result | None = None, *, raises: bool = False) -> None:
        self._result = result or _Result()
        self._raises = raises
        self.calls: list[tuple[str, ...]] = []
        # "DEFAULTED" is the sentinel for a caller that let the SDK choose.
        self.shell_flags: list[object] = []

    async def exec(self, *_args: str, **_kwargs: object) -> _Result:
        self.calls.append(_args)
        self.shell_flags.append(_kwargs.get("shell", "DEFAULTED"))
        if self._raises:
            raise RuntimeError("sandbox exec unavailable")
        joined = "\n".join(str(a) for a in _args)
        # Isolation bring-up probes (C1/C2) run before the inventory; answer them
        # as the container would, not with the inventory listing.
        if "apf-image-inventory" in joined:
            # The inventory probe prints [spelling, realpath] pairs; a test listing
            # is its own canonical spelling.
            lines = [line for line in self._result.stdout.splitlines() if line.strip()]
            pairs = json.dumps([[line, line] for line in lines])
            return _Result(stdout=pairs)
        if "os.path.realpath" in joined:
            separator = _args.index("--")
            paths = [str(a) for a in _args[separator + 1 :]]
            payload = json.dumps([[p, os.path.realpath(p)] for p in paths])
            return _Result(stdout=payload)
        if "os.walk" in joined:
            return _Result(stdout="[]")
        return self._result

    @property
    def inventory_calls(self) -> list[tuple[str, ...]]:
        return [call for call in self.calls if any("find" in str(a) for a in call)]


class TestExecutableListing:
    """The inventory parse is pure and rejects anything that is not an absolute path."""

    def test_keeps_absolute_paths_only(self) -> None:
        listing = "/usr/bin/nmap\nrelative/path\n\n/usr/bin/ffuf\n"

        assert parse_executable_listing(listing) == (Path("/usr/bin/nmap"), Path("/usr/bin/ffuf"))

    def test_dedupes_repeated_paths(self) -> None:
        listing = "/usr/bin/nmap\n/usr/bin/nmap\n"

        assert parse_executable_listing(listing) == (Path("/usr/bin/nmap"),)

    def test_empty_listing_is_empty(self) -> None:
        assert parse_executable_listing("") == ()


class TestSeedPaths:
    """An explicit container path list is recorded as image-sourced."""

    def test_records_every_path_as_image_source(self) -> None:
        ledger = ProvenanceLedger()

        seeded = seed_paths(ledger, ["/usr/bin/nmap", "/usr/bin/ffuf"])

        assert seeded == 2
        for path in ("/usr/bin/nmap", "/usr/bin/ffuf"):
            envelope = ledger.lookup(path)
            assert isinstance(envelope, ProvenanceEnvelope)
            assert envelope.sources == frozenset({Source.SANDBOX_IMAGE})
            assert envelope.is_tainted() is False

    def test_seeded_paths_are_not_inferred(self) -> None:
        ledger = ProvenanceLedger()

        seed_paths(ledger, ["/usr/bin/nmap"])

        assert ledger.is_inferred("/usr/bin/nmap") is False


class TestBringUp:
    """One ledger per sandbox epoch, seeded from the container's own inventory."""

    def test_seeds_from_container_listing(self) -> None:
        session = _FakeSession(_Result(stdout="/usr/bin/nmap\n/usr/bin/ffuf\n"))

        ledger = asyncio.run(bring_up_provenance(session))

        assert len(ledger) == 2
        envelope = ledger.lookup("/usr/bin/nmap")
        assert isinstance(envelope, ProvenanceEnvelope)
        assert envelope.is_tainted() is False

    def test_runs_the_inventory_inside_the_sandbox(self) -> None:
        session = _FakeSession(_Result(stdout="/usr/bin/nmap\n"))

        asyncio.run(bring_up_provenance(session))

        assert session.calls, "bring-up must exec into the sandbox, not read the host"
        assert session.inventory_calls, "the inventory walk must run in the sandbox"
        argv = session.inventory_calls[0]
        assert argv[:2] == ("/usr/bin/env", "-i"), argv
        assert "/usr/bin/find" in argv, argv
        assert all(flag is False for flag in session.shell_flags), session.shell_flags

    def test_exec_failure_aborts_bring_up(self) -> None:
        """C1: a bring-up assertion that cannot be observed refuses the sandbox."""
        session = _FakeSession(raises=True)

        with pytest.raises(IsolationBringupError):
            asyncio.run(bring_up_provenance(session))

    def test_non_zero_exit_still_seeds_what_parsed(self) -> None:
        session = _FakeSession(
            _Result(stdout="/usr/bin/nmap\n", stderr="find: /opt: denied", code=1)
        )

        ledger = asyncio.run(bring_up_provenance(session))

        assert len(ledger) == 1

    def test_empty_inventory_is_a_failed_seed(self, caplog: object) -> None:
        session = _FakeSession(_Result(stdout=""))

        with caplog.at_level("WARNING"):  # type: ignore[attr-defined]
            ledger = asyncio.run(bring_up_provenance(session))

        assert len(ledger) == 0
        assert ledger.lookup("/usr/bin/nmap") is LedgerMiss.MISS
        assert "FAILED seed" in caplog.text  # type: ignore[attr-defined]

    def test_no_engagement_taint_is_ever_created_at_bring_up(self) -> None:
        session = _FakeSession(_Result(stdout="/usr/bin/nmap\n/bin/sh\n"))

        ledger = asyncio.run(bring_up_provenance(session))

        for path in ledger.operators():
            envelope = ledger.lookup(path)
            assert isinstance(envelope, ProvenanceEnvelope)
            assert envelope.is_tainted() is False


class TestSeedClosesTheLiveLoop:
    """The integration replay's FINDING-1 shape, end to end.

    A seeded binary is allowed at the gate with no miss; an unseeded one denies —
    which is exactly the live failure the replay measured (`curl --version` denied
    on a 0-entry ledger). The wiring exists (session-manager bring-up → this
    function → `seed_paths`); this cell pins the loop, not the symbol name.
    """

    def test_a_seeded_binary_is_allowed_and_an_unseeded_one_denies(self) -> None:
        import shutil  # noqa: PLC0415 - platform lookup

        from sagaward.core.provenance.classify import classify  # noqa: PLC0415
        from sagaward.core.provenance.gate import ReasonCode, decide_action  # noqa: PLC0415

        seeded = shutil.which("ls")
        unseeded = shutil.which("cat")
        assert seeded is not None and unseeded is not None
        session = _FakeSession(_Result(stdout=f"{seeded}\n"))

        ledger = asyncio.run(bring_up_provenance(session))

        assert decide_action(classify(f"{seeded} -la"), ledger).verdict == "ALLOW"
        denied = decide_action(classify(f"{unseeded} /etc/hosts"), ledger)
        assert denied.reason is ReasonCode.PROVENANCE_MISS


class TestAliasKeys:
    """Round-31: the usrmerged root records one file under two spellings.

    Kali is usrmerged (`/bin` -> `/usr/bin`). The inventory canonicalizes
    in-container; the gate resolves on the host process, which cannot see a
    container symlink, so the seed must record the canonical key *and* the alias
    key — otherwise the gate asks for `/bin/ls` and the ledger answers for
    `/usr/bin/ls` (the replay's sixth-check defect, measured to the key).
    """

    def test_an_alias_pair_hits_on_both_spellings(self) -> None:
        from sagaward.core.provenance.seed import seed_inventory  # noqa: PLC0415

        ledger = ProvenanceLedger()
        seeded = seed_inventory(
            ledger,
            [("/opt/apf-alias/bin/tool", "/opt/apf-alias/usr/bin/tool")],
        )

        assert seeded == 1
        alias = ledger.lookup("/opt/apf-alias/bin/tool")
        canonical = ledger.lookup("/opt/apf-alias/usr/bin/tool")
        assert isinstance(alias, ProvenanceEnvelope)
        assert isinstance(canonical, ProvenanceEnvelope)
        assert alias == canonical
        assert alias.is_tainted() is False

    def test_the_pair_parser_is_fail_closed(self) -> None:
        from sagaward.core.provenance.seed import parse_inventory_pairs  # noqa: PLC0415

        assert parse_inventory_pairs("not json") is None
        assert parse_inventory_pairs('{"x": 1}') is None
        pairs = parse_inventory_pairs('[["/bin/ls", "/usr/bin/ls"], ["bad"], [1, 2]]')
        assert pairs == (("/bin/ls", "/usr/bin/ls"),)

    def test_a_symlinked_root_binary_is_reachable_through_the_alias(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The host *can* resolve this one, so the canonical key serves it; the
        # cell proves the pair shape end to end without depending on the host's
        # own usrmerge layout.
        from sagaward.core.provenance import seed as seed_module  # noqa: PLC0415
        from sagaward.core.provenance.classify import classify  # noqa: PLC0415
        from sagaward.core.provenance.gate import decide_action  # noqa: PLC0415
        from sagaward.core.provenance.seed import seed_inventory  # noqa: PLC0415

        # The subject here is the alias pair, not the writable-root skip (which
        # has its own cells). Under a /tmp extraction the fixture itself is
        # agent-writable, so the root list is emptied for this cell only.
        monkeypatch.setattr(seed_module, "AGENT_WRITABLE_ROOTS", ())
        probe_dir = Path(__file__).parent.resolve()
        real = probe_dir / "_alias_probe.bin"
        real.write_text("#!/bin/sh\nexit 0\n")
        real.chmod(0o755)
        alias = probe_dir / "_alias_probe_link"
        if alias.exists() or alias.is_symlink():
            alias.unlink()
        alias.symlink_to(real)
        try:
            ledger = ProvenanceLedger()
            # The pair's canonical value is what the in-container probe emits:
            # os.path.realpath. On macOS a /tmp extraction is itself behind
            # /private/tmp, and the canonical key must match the gate's resolve.
            seed_inventory(ledger, [(str(alias), real.resolve().as_posix())])
            decision = decide_action(classify(str(alias)), ledger)
            assert decision.verdict == "ALLOW", decision
        finally:
            alias.unlink(missing_ok=True)
            real.unlink(missing_ok=True)

    def test_the_inventory_probe_produces_alias_pairs(self, tmp_path: Path) -> None:
        """The probe's own pair production, against a symlinked root (round-33).

        The recorder was tested with fake pairs; this runs the shipped probe
        against a real symlinked root and asserts the alias spelling reaches the
        output. Without `find -L` the root is not traversed and no pair differs.
        """
        import subprocess  # noqa: PLC0415
        import sys  # noqa: PLC0415

        from sagaward.core.provenance.seed import (  # noqa: PLC0415
            INVENTORY_SCRIPT,
            parse_inventory_pairs,
        )

        real = tmp_path / "real"
        real.mkdir()
        tool = real / "tool"
        tool.write_text("#!/bin/sh\nexit 0\n")
        tool.chmod(0o755)
        link = tmp_path / "link"
        link.symlink_to(real)

        proc = subprocess.run(  # noqa: S603 - fixed argv, test-only
            [sys.executable, "-I", "-c", INVENTORY_SCRIPT, "--", "/usr/bin/find", str(link)],
            capture_output=True,
            text=True,
            check=True,
        )
        pairs = parse_inventory_pairs(proc.stdout)

        assert pairs, "the probe must produce at least one pair"
        spellings = {spelling for spelling, _canonical in pairs}
        canonicals = {canonical for _spelling, canonical in pairs}
        assert str(link / "tool") in spellings, "the alias spelling must be listed"
        assert str(real.resolve() / "tool") in canonicals
        assert any(spelling != canonical for spelling, canonical in pairs), (
            "the pair must differ for a symlinked root — otherwise the dual-key "
            "recording never fires"
        )
