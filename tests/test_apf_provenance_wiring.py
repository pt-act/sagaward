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

from strix.core.provenance import (
    LedgerMiss,
    ProvenanceEnvelope,
    ProvenanceLedger,
    Source,
    parse_executable_listing,
    seed_paths,
)
from strix.runtime.isolation_bringup import IsolationBringupError
from strix.runtime.provenance_bringup import bring_up_provenance


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
