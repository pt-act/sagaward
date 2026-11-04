"""Scratch reconciliation tests (apf-provenance 0.2.4, PM disposition 2026-10-28).

Covers the four binding conditions: closed-world bounds, fail-closed + loud failure
posture with escalation, tool-written artifacts recorded as MODEL_AUTHORED, and the
reason string the gate consumes. Offline throughout: fake session, fake ctx.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from strix.core.provenance import (
    LedgerMiss,
    ProvenanceEnvelope,
    ProvenanceLedger,
    Source,
)
from strix.core.provenance.reconcile import (
    RECONCILE_COMMAND,
    RECONCILE_MAX_DEPTH,
    RECONCILE_MAX_ENTRIES,
    SCRATCH_ROOT,
    is_within_scratch,
    paths_in_scratch_listing,
    record_scratch_artifacts,
)
from strix.core.provenance.seed import (
    IMAGE_ROOTS,
    MAX_DEPTH,
    MAX_PATHS,
    is_agent_writable,
    seed_paths,
)
from strix.runtime.provenance_reconcile import (
    RECONCILE_FAILURE_LIMIT,
    reconcile_after_exec,
    reconcile_scratch,
)


if TYPE_CHECKING:
    from pathlib import Path

    import pytest


class _Result:
    def __init__(self, stdout: str = "", stderr: str = "", code: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self._code = code

    def ok(self) -> bool:
        return self._code == 0


class _Session:
    def __init__(self, result: _Result | None = None, *, raises: bool = False) -> None:
        self._result = result or _Result()
        self._raises = raises
        self.calls: list[tuple[str, ...]] = []
        # "DEFAULTED" is the sentinel for a caller that let the SDK choose.
        self.shell_flags: list[object] = []

    async def exec(self, *args: str, **_kwargs: object) -> _Result:
        self.calls.append(args)
        self.shell_flags.append(_kwargs.get("shell", "DEFAULTED"))
        if self._raises:
            raise RuntimeError("exec unavailable")
        return self._result


class _Ctx:
    def __init__(self, **context: object) -> None:
        self.context = context


class _Coordinator:
    def __init__(self) -> None:
        self.reasons: list[str] = []

    async def kill_switch(self, reason: str) -> None:
        self.reasons.append(reason)


class TestBounds:
    """Condition 1 — bounded and closed-world."""

    def test_depth_matches_seed_bound(self) -> None:
        assert RECONCILE_MAX_DEPTH == MAX_DEPTH == 3

    def test_entry_cap_matches_seed_bound(self) -> None:
        assert RECONCILE_MAX_ENTRIES == MAX_PATHS == 20_000

    def test_command_is_bounded_to_scratch(self) -> None:
        assert str(SCRATCH_ROOT) in RECONCILE_COMMAND
        assert "-maxdepth" in RECONCILE_COMMAND
        assert RECONCILE_COMMAND[RECONCILE_COMMAND.index("-maxdepth") + 1] == str(
            RECONCILE_MAX_DEPTH,
        )

    def test_scratch_membership(self) -> None:
        assert is_within_scratch("/workspace/scratch/scan.py") is True
        assert is_within_scratch("/workspace/target/scan.py") is False
        assert is_within_scratch("/usr/bin/nmap") is False

    def test_quarantine_is_never_in_scratch(self) -> None:
        assert is_within_scratch("/workspace/quarantine/credman") is False


class TestListing:
    def test_keeps_only_scratch_paths(self) -> None:
        listing = (
            "/workspace/scratch/nuclei.json\n"
            "/workspace/target/app.py\n"
            "/usr/bin/nmap\n"
            "/workspace/quarantine/credman"
        )

        paths = paths_in_scratch_listing(listing)

        assert paths == (SCRATCH_ROOT / "nuclei.json",)

    def test_dedupes(self) -> None:
        listing = "/workspace/scratch/a\n/workspace/scratch/a\n"

        assert paths_in_scratch_listing(listing) == (SCRATCH_ROOT / "a",)

    def test_truncates_at_entry_cap(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("strix.core.provenance.reconcile.RECONCILE_MAX_ENTRIES", 2)
        listing = "\n".join(f"/workspace/scratch/f{i}" for i in range(10))

        paths = paths_in_scratch_listing(listing)

        assert len(paths) == 2

    def test_ignores_relative_lines(self) -> None:
        assert paths_in_scratch_listing("scratch/a\n./b\n") == ()


class TestRecording:
    def test_records_tool_written_artifact(self) -> None:
        ledger = ProvenanceLedger()

        recorded = record_scratch_artifacts(ledger, ["/workspace/scratch/nuclei.json"])

        assert recorded == 1
        envelope = ledger.lookup("/workspace/scratch/nuclei.json")
        assert isinstance(envelope, ProvenanceEnvelope)
        assert envelope.sources == frozenset({Source.MODEL_AUTHORED})
        assert envelope.is_tainted() is False

    def test_refuses_paths_outside_scratch(self) -> None:
        ledger = ProvenanceLedger()

        recorded = record_scratch_artifacts(
            ledger,
            ["/workspace/target/app.py", "/usr/bin/nmap", "/workspace/quarantine/credman"],
        )

        assert recorded == 0
        assert len(ledger) == 0

    def test_never_clears_existing_taint(self) -> None:
        ledger = ProvenanceLedger()
        path = "/workspace/scratch/pasted.py"
        ledger.record(path, ProvenanceEnvelope.of(Source.ENGAGEMENT_SURFACE))

        record_scratch_artifacts(ledger, [path])

        envelope = ledger.lookup(path)
        assert isinstance(envelope, ProvenanceEnvelope)
        assert envelope.is_tainted() is True

    def test_tool_artifact_is_runnable_under_the_gate_predicate(self) -> None:
        """AC-3/AC-4's live-flow twin: a scanned-output file must not read as a miss."""
        ledger = ProvenanceLedger()
        record_scratch_artifacts(ledger, ["/workspace/scratch/nmap-oA.xml"])

        envelope = ledger.lookup("/workspace/scratch/nmap-oA.xml")

        assert isinstance(envelope, ProvenanceEnvelope)
        assert envelope.is_tainted() is False


class TestReconcileSession:
    def test_success_records_artifacts(self) -> None:
        ledger = ProvenanceLedger()
        session = _Session(_Result(stdout=f"{'a' * 64}  /workspace/scratch/scan.py\n"))

        recorded = asyncio.run(reconcile_scratch(session, ledger))

        assert recorded == 1
        assert isinstance(ledger.lookup("/workspace/scratch/scan.py"), ProvenanceEnvelope)

    def test_observation_runs_in_the_sandbox(self) -> None:
        session = _Session(_Result(stdout=""))

        asyncio.run(reconcile_scratch(session, ProvenanceLedger()))

        assert session.calls, "reconciliation must exec into the sandbox, not read the host"
        argv = session.calls[0]
        assert argv[:2] == ("/usr/bin/env", "-i"), argv
        assert "/usr/bin/find" in argv, argv
        assert session.shell_flags == [False], session.shell_flags

    def test_exec_failure_returns_none(self) -> None:
        assert asyncio.run(reconcile_scratch(_Session(raises=True), ProvenanceLedger())) is None

    def test_non_zero_exit_returns_none(self) -> None:
        session = _Session(_Result(stdout="", stderr="find: denied", code=1))

        assert asyncio.run(reconcile_scratch(session, ProvenanceLedger())) is None


class TestFailurePosture:
    """Condition 2 — fail-closed, loud, and escalate after N consecutive failures."""

    def test_three_consecutive_failures_refuse(self) -> None:
        coordinator = _Coordinator()
        ctx = _Ctx(
            provenance=ProvenanceLedger(),
            sandbox_session=_Session(raises=True),
            coordinator=coordinator,
        )

        for _ in range(RECONCILE_FAILURE_LIMIT):
            asyncio.run(reconcile_after_exec(ctx))

        assert len(coordinator.reasons) == 1
        assert "reconciliation failed" in coordinator.reasons[0]

    def test_two_failures_do_not_refuse(self) -> None:
        coordinator = _Coordinator()
        ctx = _Ctx(
            provenance=ProvenanceLedger(),
            sandbox_session=_Session(raises=True),
            coordinator=coordinator,
        )

        for _ in range(RECONCILE_FAILURE_LIMIT - 1):
            asyncio.run(reconcile_after_exec(ctx))

        assert coordinator.reasons == []

    def test_success_resets_the_counter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from strix.runtime import provenance_reconcile as rec  # noqa: PLC0415

        async def _empty_sweep(_session: object, _ledger: object) -> int:
            return 0

        # This cell measures the SCRATCH counter; the quarantine sweep has its own
        # failure cells and would otherwise consume the single fake answer.
        monkeypatch.setattr(rec, "reconcile_quarantine", _empty_sweep)
        coordinator = _Coordinator()
        ledger = ProvenanceLedger()
        ctx = _Ctx(
            provenance=ledger,
            sandbox_session=_Session(raises=True),
            coordinator=coordinator,
        )

        asyncio.run(reconcile_after_exec(ctx))
        asyncio.run(reconcile_after_exec(ctx))
        ctx.context["sandbox_session"] = _Session(_Result(stdout=""))
        asyncio.run(reconcile_after_exec(ctx))
        ctx.context["sandbox_session"] = _Session(raises=True)
        asyncio.run(reconcile_after_exec(ctx))
        asyncio.run(reconcile_after_exec(ctx))

        assert coordinator.reasons == []

    def test_no_ledger_is_a_noop(self) -> None:
        ctx = _Ctx(sandbox_session=_Session(raises=True))

        asyncio.run(reconcile_after_exec(ctx))

        assert "provenance_reconcile" not in ctx.context


class TestValidatorRound1Regressions:
    """Regressions found in validation round 1. Each maps to a blocking item."""

    def test_b2_hardlink_to_unrecorded_quarantine_does_not_read_clean(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """B2 — the inode index may extend taint, never cleanliness."""
        quarantine = tmp_path / "quarantine"
        scratch = tmp_path / "scratch"
        quarantine.mkdir()
        scratch.mkdir()
        monkeypatch.setattr("strix.core.provenance.reconcile.SCRATCH_ROOT", scratch)
        implant = quarantine / "credman"
        implant.write_text("#!/bin/sh\n", encoding="utf-8")
        link = scratch / "innocent"
        link.hardlink_to(implant)

        ledger = ProvenanceLedger()
        recorded = record_scratch_artifacts(ledger, [link])
        assert recorded == 1, "the fixture must actually be recorded, or the test proves nothing"

        looked_up = ledger.lookup(implant)
        assert looked_up is LedgerMiss.MISS

    def test_b2_tainted_hardlink_still_propagates(self, tmp_path: Path) -> None:
        """The hardlink defence itself must survive the fix."""
        ledger = ProvenanceLedger()
        source = tmp_path / "quarantine" / "credman"
        source.parent.mkdir()
        source.write_text("#!/bin/sh\n", encoding="utf-8")
        ledger.record(source, ProvenanceEnvelope.of(Source.ENGAGEMENT_SURFACE))
        link = tmp_path / "scratch" / "alias"
        link.parent.mkdir()
        link.hardlink_to(source)

        found = ledger.lookup(link)

        assert isinstance(found, ProvenanceEnvelope)
        assert found.is_tainted() is True

    def test_b3_agent_writable_roots_are_never_seeded(self, tmp_path: Path) -> None:
        """B3 — the image cannot vouch for content the agent can rewrite."""
        ledger = ProvenanceLedger()
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        tool = bin_dir / "nmap"
        tool.write_text("#!/bin/sh\n", encoding="utf-8")
        tool.chmod(0o755)

        seeded = seed_paths(ledger, ["/home/pentester/tools/nmap", "/usr/bin/nmap"])

        assert seeded == 1
        assert ledger.lookup("/home/pentester/tools/nmap") is LedgerMiss.MISS
        assert isinstance(ledger.lookup("/usr/bin/nmap"), ProvenanceEnvelope)

    def test_b3_image_roots_exclude_agent_writable_prefixes(self) -> None:
        for root in IMAGE_ROOTS:
            assert not is_agent_writable(root), f"{root} is agent-writable"
