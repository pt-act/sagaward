"""Write-hook tests for apf-provenance (AC-10, PM reshape).

The SDK's only file-creation surface is `apply_patch`, a raw patch document.
These tests exercise the wrapper offline — fake toolset, fake ctx — because the
hook's correctness is parse-and-record, not container behaviour.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from sagaward.core.provenance import (
    LedgerMiss,
    ProvenanceEnvelope,
    ProvenanceLedger,
    Source,
    paths_in_patch,
    record_model_authored,
    resolve_workspace_path,
)
from sagaward.core.provenance.content import ABSENT, digest
from sagaward.core.provenance.write_hook import (
    EXPECTED_WRITE_TOOLS,
    configure_filesystem_tools,
    wrap_apply_patch_tool,
)


def obs(text: str, mtime: int = 10**19) -> tuple[str, int]:
    return (digest(text), mtime)


ABSENT_OBS = (ABSENT, 0)


class _StubTool:
    """Stands in for the SDK's CustomTool: a name plus an invokable."""

    def __init__(self, name: str, *, result: str = "ok") -> None:
        self.name = name
        self._result = result
        self.calls: list[str] = []

    async def on_invoke_tool(self, _ctx: Any, raw_input: str) -> str:
        self.calls.append(raw_input)
        return self._result


class _Toolset:
    def __init__(self, *tools: _StubTool) -> None:
        for tool in tools:
            setattr(self, tool.name, tool)


class _Ctx:
    def __init__(self, ledger: Any) -> None:
        self.context = {"provenance": ledger}


PATCH = """*** Begin Patch
*** Add File: scratch/scan.py
+print(1)
*** Update File: scratch/lib.py
*** Move to: scratch/lib2.py
@@ def f():
-a
+b
*** Delete File: scratch/old.py
*** End Patch
"""


class TestPatchParsing:
    """Pure parse of the SDK's patch grammar."""

    def test_finds_every_write_operation(self) -> None:
        paths = paths_in_patch(PATCH)

        assert Path("/workspace/scratch/scan.py") in paths
        assert Path("/workspace/scratch/lib.py") in paths
        assert Path("/workspace/scratch/lib2.py") in paths
        assert Path("/workspace/scratch/old.py") in paths

    def test_ignores_body_lines(self) -> None:
        assert Path("/workspace/print(1)") not in paths_in_patch(PATCH)

    def test_rejects_absolute_paths(self) -> None:
        assert paths_in_patch("*** Add File: /etc/passwd\n") == ()

    def test_rejects_escaping_paths(self) -> None:
        assert resolve_workspace_path("../../etc/passwd") is None
        assert resolve_workspace_path("scratch/../../etc/passwd") is None

    def test_resolves_relative_against_workspace(self) -> None:
        assert resolve_workspace_path("scratch/scan.py") == Path("/workspace/scratch/scan.py")

    def test_empty_patch_yields_nothing(self) -> None:
        assert paths_in_patch("*** Begin Patch\n*** End Patch\n") == ()


class TestRecording:
    def test_records_model_authored_envelopes(self) -> None:
        ledger = ProvenanceLedger()

        recorded = record_model_authored(ledger, [Path("/workspace/scratch/scan.py")])

        assert recorded == 1
        envelope = ledger.lookup("/workspace/scratch/scan.py")
        assert isinstance(envelope, ProvenanceEnvelope)
        assert envelope.sources == frozenset({Source.MODEL_AUTHORED})
        assert envelope.is_tainted() is False

    def test_recording_never_clears_taint(self) -> None:
        ledger = ProvenanceLedger()
        path = Path("/workspace/scratch/pasted.py")
        ledger.record(path, ProvenanceEnvelope.of(Source.ENGAGEMENT_SURFACE))

        record_model_authored(ledger, [path])

        envelope = ledger.lookup(path)
        assert isinstance(envelope, ProvenanceEnvelope)
        assert envelope.is_tainted() is True


async def _fresh_verifier(_ctx: object, paths: tuple[object, ...]) -> dict[object, object]:
    """Baseline: every touched path absent, so a write is a real change."""
    return dict.fromkeys(paths, ABSENT_OBS)


class TestWriteHook:
    """The wrapper records what the patch touches, after the tool returns."""

    def test_records_written_paths_from_patch(self) -> None:
        ledger = ProvenanceLedger()
        tool = _StubTool("apply_patch")
        calls: list[int] = []

        async def verifier(_ctx: object, paths: tuple[object, ...]) -> dict[object, object]:
            calls.append(1)
            if len(calls) == 1:
                return dict.fromkeys(paths, ABSENT_OBS)
            return {path: obs("print(1)\n") for path in paths}

        wrap_apply_patch_tool(tool, verifier)

        asyncio.run(tool.on_invoke_tool(_Ctx(ledger), PATCH))

        envelope = ledger.lookup("/workspace/scratch/scan.py")
        assert isinstance(envelope, ProvenanceEnvelope)
        assert envelope.sources == frozenset({Source.MODEL_AUTHORED})

    def test_does_not_alter_tool_result(self) -> None:
        ledger = ProvenanceLedger()
        tool = _StubTool("apply_patch", result="Applied 4 operations")
        wrap_apply_patch_tool(tool)

        result = asyncio.run(tool.on_invoke_tool(_Ctx(ledger), PATCH))

        assert result == "Applied 4 operations"

    def test_never_records_a_quarantine_path_as_clean(self) -> None:
        ledger = ProvenanceLedger()
        tool = _StubTool("apply_patch")
        wrap_apply_patch_tool(tool, _fresh_verifier)

        asyncio.run(
            tool.on_invoke_tool(
                _Ctx(ledger),
                "*** Begin Patch\n*** Add File: quarantine/credman\n+x\n*** End Patch\n",
            ),
        )

        assert ledger.lookup("/workspace/quarantine/credman") is LedgerMiss.MISS

    def test_missing_ledger_is_survivable(self) -> None:
        tool = _StubTool("apply_patch", result="ok")
        wrap_apply_patch_tool(tool)

        class _EmptyCtx:
            context = None

        assert asyncio.run(tool.on_invoke_tool(_EmptyCtx(), PATCH)) == "ok"


class TestRefusalPosture:
    """PM condition 2a — a dead hook refuses at build time, it does not warn and run."""

    def test_expected_tool_names_are_declared(self) -> None:
        assert frozenset({"apply_patch"}) == EXPECTED_WRITE_TOOLS

    def test_refuses_when_write_tool_is_absent(self) -> None:
        toolset = _Toolset(_StubTool("view_image"))

        with pytest.raises(RuntimeError) as caught:
            configure_filesystem_tools(toolset, chat_completions=False)

        message = str(caught.value)
        assert "apply_patch" in message
        assert "view_image" in message
        assert "APF" in message.upper() or "apf-provenance" in message.lower()

    def test_attaches_when_write_tool_is_present(self) -> None:
        toolset = _Toolset(_StubTool("apply_patch"), _StubTool("view_image"))

        configure_filesystem_tools(
            toolset,
            chat_completions=False,
            verifier=_fresh_verifier,
        )

        ledger = ProvenanceLedger()
        ctx = _Ctx(ledger)
        asyncio.run(toolset.apply_patch.on_invoke_tool(ctx, PATCH))
        # A static verifier reports the same state twice; nothing is claimed.
        assert ledger.lookup("/workspace/scratch/scan.py") is LedgerMiss.MISS
