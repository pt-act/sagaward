"""Round 13 — R12-ATK: a truthful observation must not be redirected by a link.

Round 12's validator showed that a swallowed SDK write reporting success over an
``*** Update File:`` document, plus a symlink created between the pre- and the
post-probe, makes the *real* argv probe read a pre-existing file the model never
wrote; the recorder then stored that file ``MODEL_AUTHORED`` at its own canonical
key, and recorded a quarantine key clean.

Two independent layers refuse it, each with a test that dies when the layer is
removed:

1. the probe reports a link as ``SYMLINK`` and ``hash_paths`` folds it into the
   unobserved state (``None``) — a link is never a write observation;
2. the recorder refuses any observation whose resolved path is not the observed
   key, so a link or traversal cannot move the record to another key.

The anti-strangulation cell keeps the second layer honest: a regular new file in
a real directory is still recorded.
"""

from __future__ import annotations

import asyncio
import hashlib
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from oriontrix.core.provenance import LedgerMiss, ProvenanceEnvelope, ProvenanceLedger
from oriontrix.core.provenance.content import ABSENT, digest
from oriontrix.core.provenance.write_hook import record_observed_writes, wrap_apply_patch_tool
from oriontrix.runtime.provenance_reconcile import (
    PROBE_SCRIPT,
    SYMLINK_MARKER,
    hash_paths,
    verify_patch_writes,
)


if TYPE_CHECKING:
    import pytest


class _Result:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", code: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = code

    def ok(self) -> bool:
        return self.exit_code == 0


class _ProbeSession:
    """A session whose probe answers per call: the pre-observation, then the post."""

    def __init__(self, answers: list[bytes]) -> None:
        self._answers = answers
        self.calls: list[tuple[tuple[str, ...], object]] = []

    async def exec(
        self,
        *command: str,
        timeout: float | None = None,  # noqa: ARG002 - mirrors the SDK signature
        shell: bool | list[str] = True,
    ) -> _Result:
        argv = tuple(str(item) for item in command)
        self.calls.append((argv, shell))
        index = min(len(self.calls), len(self._answers)) - 1
        return _Result(self._answers[index])


class _Ctx:
    def __init__(self, context: dict[str, object]) -> None:
        self.context = context


class _Patch:
    name = "apply_patch"

    def __init__(self, result: str) -> None:
        self._result = result

    async def on_invoke_tool(self, _ctx: object, _raw: str) -> str:
        return self._result


def _line(marker: str, path: str, mtime: int = 0) -> bytes:
    return f"{marker}  {mtime}  {path}\n".encode()


class TestProbeMarksLinks:
    def test_the_shipped_probe_script_reports_a_link(self, tmp_path: Path) -> None:
        secret = tmp_path / "secret.sh"
        secret.write_bytes(b"# SECRET FROM TARGET\n")
        link = tmp_path / "x.py"
        link.symlink_to(secret)

        completed = subprocess.run(  # noqa: S603 - fixed argv, module-owned script
            [sys.executable, "-c", PROBE_SCRIPT, "--", str(link), str(secret)],
            capture_output=True,
            text=True,
            check=True,
        )
        lines = completed.stdout.splitlines()

        assert lines[0].split("  ", 2)[0] == SYMLINK_MARKER, lines[0]
        assert lines[0].endswith(str(link)), lines[0]
        assert len(lines[1].split("  ", 2)[0]) == 64, lines[1]

    def test_hash_paths_folds_a_link_into_unobserved(self) -> None:
        path = "/workspace/scratch/x.py"
        session = _ProbeSession([_line(SYMLINK_MARKER, path, 1_700_000_000_000_000_000)])

        observed = asyncio.run(hash_paths(session, (Path(path),)))

        assert observed == {Path(path): (None, 1_700_000_000_000_000_000)}
        assert session.calls[0][1] is False


class TestRedirectChain:
    """R12-ATK end to end: a swallowed write plus a mid-flight link."""

    def _run(self, post_line: bytes) -> tuple[_ProbeSession, ProvenanceLedger]:
        ledger = ProvenanceLedger()
        session = _ProbeSession([_line(ABSENT, "/workspace/scratch/x.py"), post_line])
        ctx = _Ctx({"provenance": ledger, "sandbox_session": session})
        tool = wrap_apply_patch_tool(_Patch("Updated scratch/x.py"), verify_patch_writes)
        patch = "*** Begin Patch\n*** Update File: scratch/x.py\n+echo pwned\n*** End Patch\n"

        result = asyncio.run(tool.on_invoke_tool(ctx, patch))

        assert result == "Updated scratch/x.py"
        return session, ledger

    def test_an_update_redirected_by_a_midflight_link_records_nothing(self) -> None:
        secret_mtime = 1_700_000_000_000_000_000
        session, ledger = self._run(_line(SYMLINK_MARKER, "/workspace/scratch/x.py", secret_mtime))

        assert ledger.lookup("/workspace/target/secret.sh") is LedgerMiss.MISS
        assert ledger.lookup("/workspace/scratch/x.py") is LedgerMiss.MISS
        assert len(session.calls) == 2, "the hook must still observe before and after"
        assert [shell for _argv, shell in session.calls] == [False, False]

    def test_the_same_chain_with_a_quarantine_target_records_nothing(self) -> None:
        _session, ledger = self._run(_line(SYMLINK_MARKER, "/workspace/scratch/x.py", 1))

        assert ledger.lookup("/workspace/quarantine/credman") is LedgerMiss.MISS

    def test_the_failure_result_still_blocks_before_any_post_probe(self) -> None:
        ledger = ProvenanceLedger()
        session = _ProbeSession([_line(ABSENT, "/workspace/scratch/x.py")])
        ctx = _Ctx({"provenance": ledger, "sandbox_session": session})
        tool = wrap_apply_patch_tool(
            _Patch("apply_patch failed: read-only file system"),
            verify_patch_writes,
        )
        patch = "*** Begin Patch\n*** Update File: scratch/x.py\n+echo pwned\n*** End Patch\n"

        asyncio.run(tool.on_invoke_tool(ctx, patch))

        assert len(session.calls) == 1, "the result gate returns before the second observation"
        assert ledger.lookup("/workspace/scratch/x.py") is LedgerMiss.MISS


class TestRecorderCanonicality:
    """Layer 2 alone: even a digest for the wrong key must not be recorded."""

    def test_a_redirected_key_is_refused(self, tmp_path: Path) -> None:
        secret = tmp_path / "target" / "secret.sh"
        secret.parent.mkdir()
        secret.write_bytes(b"# SECRET FROM TARGET\n")
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        link = scratch / "x.py"
        link.symlink_to(secret)
        ledger = ProvenanceLedger()

        recorded = record_observed_writes(
            ledger,
            [(link, (digest(b"# SECRET FROM TARGET\n"), time.time_ns()))],
            before={link: (ABSENT, 0)},
        )

        assert recorded == 0
        assert ledger.lookup(secret) is LedgerMiss.MISS
        assert ledger.lookup(link) is LedgerMiss.MISS

    def test_a_redirect_into_quarantine_is_refused(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from oriontrix.core.provenance import paths as provenance_paths  # noqa: PLC0415

        quarantine = tmp_path / "quarantine"
        quarantine.mkdir()
        credman = quarantine / "credman"
        credman.write_bytes(b"\x7fELF definitely not nmap\n")
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        link = scratch / "x"
        link.symlink_to(credman)
        monkeypatch.setattr(provenance_paths, "QUARANTINE_DIR", quarantine)
        ledger = ProvenanceLedger()

        recorded = record_observed_writes(
            ledger,
            [(link, (digest(b"\x7fELF definitely not nmap\n"), time.time_ns()))],
            before={link: (ABSENT, 0)},
        )

        assert recorded == 0
        assert ledger.lookup(credman) is LedgerMiss.MISS

    def test_a_regular_write_is_still_recorded(self, tmp_path: Path) -> None:
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        written = scratch / "scan.py"
        written.write_bytes(b"print('hi')\n")
        ledger = ProvenanceLedger()

        recorded = record_observed_writes(
            ledger,
            [(written, (hashlib.sha256(b"print('hi')\n").hexdigest(), time.time_ns()))],
            before={written: (ABSENT, 0)},
        )

        assert recorded == 1
        envelope = ledger.lookup(written)
        assert isinstance(envelope, ProvenanceEnvelope)
        assert envelope.is_tainted() is False


class _RacingLedger(ProvenanceLedger):
    """Plants the link at store time — the model winning the check→store window."""

    def __init__(self, link: Path, target: Path) -> None:
        super().__init__()
        self._link = link
        self._target = target

    def _swap(self) -> None:
        if not self._link.is_symlink():
            self._link.unlink()
            self._link.symlink_to(self._target)

    def record(self, path: object, envelope: object, derived_from: object = ()) -> object:
        self._swap()
        return super().record(path, envelope, derived_from)  # type: ignore[arg-type]

    def record_key(self, path_key: object, envelope: object, derived_from: object = ()) -> object:
        self._swap()
        return super().record_key(path_key, envelope, derived_from)  # type: ignore[arg-type]


class TestStoreBinding:
    """R13-ATK: the check and the store must be one resolution, not two."""

    def test_the_store_is_bound_to_the_checked_key(self, tmp_path: Path) -> None:
        target = tmp_path / "target" / "secret.sh"
        target.parent.mkdir()
        target.write_bytes(b"# SECRET FROM TARGET\n")
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        written = scratch / "x.py"
        written.write_bytes(b"print('mine')\n")
        ledger = _RacingLedger(written, target)

        recorded = record_observed_writes(
            ledger,
            [(written, (hashlib.sha256(b"print('mine')\n").hexdigest(), time.time_ns()))],
            before={written: (ABSENT, 0)},
        )

        assert recorded == 1
        assert ledger.lookup(target) is LedgerMiss.MISS, (
            "a link planted after the check must not move the record onto its target"
        )
        assert ledger.lookup(written) is LedgerMiss.MISS, (
            "the envelope is keyed by the spelling that was checked, and that spelling "
            "now resolves elsewhere — it must not be reachable as the target"
        )

    def test_an_unreadable_baseline_is_not_a_write(self, tmp_path: Path) -> None:
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        written = scratch / "x.py"
        written.write_bytes(b"# SECRET FROM TARGET\n")
        ledger = ProvenanceLedger()

        recorded = record_observed_writes(
            ledger,
            [(written, (hashlib.sha256(b"# SECRET FROM TARGET\n").hexdigest(), time.time_ns()))],
            before={written: (None, 0)},
        )

        assert recorded == 0
        assert ledger.lookup(written) is LedgerMiss.MISS

    def test_a_resolution_failure_refuses_instead_of_raising(self, tmp_path: Path) -> None:
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        loop_a = scratch / "a"
        loop_b = scratch / "b"
        loop_a.symlink_to(loop_b)
        loop_b.symlink_to(loop_a)
        ledger = ProvenanceLedger()

        recorded = record_observed_writes(
            ledger,
            [(loop_a, (digest(b"anything"), time.time_ns()))],
            before={loop_a: (ABSENT, 0)},
        )

        assert recorded == 0
        assert len(ledger) == 0, "nothing may be stored for an unresolvable path"


class TestQuarantineAlias:
    """R13-QALIAS: an aliased constant still names the real quarantine directory."""

    def test_the_real_spelling_is_quarantine_when_the_constant_is_an_alias(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from oriontrix.core.provenance import paths as provenance_paths  # noqa: PLC0415

        quarantine = tmp_path / "quarantine"
        quarantine.mkdir()
        credman = quarantine / "credman"
        credman.write_bytes(b"\x7fELF definitely not nmap\n")
        alias = tmp_path / "qlink"
        alias.symlink_to(quarantine)
        monkeypatch.setattr(provenance_paths, "QUARANTINE_DIR", alias)
        ledger = ProvenanceLedger()

        for spelling in (credman, alias / "credman"):
            recorded = record_observed_writes(
                ledger,
                [(spelling, (digest(b"\x7fELF definitely not nmap\n"), time.time_ns()))],
                before={spelling: (ABSENT, 0)},
            )
            assert recorded == 0, spelling
        assert ledger.lookup(credman) is LedgerMiss.MISS
