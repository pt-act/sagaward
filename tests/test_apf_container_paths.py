"""S-5 — the classifier's path resolution routes through the container's view.

The host process cannot answer what a path means inside the container: the same
spelling resolves to a different inode, or to nothing. These cells exercise the
resolver seam without a container runtime: a fake session stands in for the
observation channel, and the classifier decides over the answers it returns.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from sagaward.core.provenance.classify import (
    CollectingPathResolver,
    HostPathResolver,
    PathRequest,
    ResolvedPathResolver,
    UnresolvedPathResolver,
    classify,
)
from sagaward.core.provenance.content import engagement_envelope
from sagaward.core.provenance.gate import ReasonCode, Resolution, decide_action
from sagaward.core.provenance.ledger import ProvenanceLedger
from sagaward.runtime.container_paths import (
    container_path_resolver,
    resolve_paths_in_container,
)


class _Result:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", code: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = code

    def ok(self) -> bool:
        return self.exit_code == 0


class _ProbeSession:
    """Answers the in-container probe from a raw-spelling -> row map."""

    def __init__(self, rows: dict[str, dict[str, Any]], *, fail: bool = False) -> None:
        self._rows = rows
        self._fail = fail
        self.calls: list[tuple[tuple[str, ...], object]] = []

    async def exec(
        self,
        *command: str,
        timeout: float | None = None,  # noqa: ARG002 - mirrors the SDK signature
        shell: bool | list[str] = True,
    ) -> _Result:
        argv = tuple(str(item) for item in command)
        self.calls.append((argv, shell))
        if self._fail:
            return _Result(b"", b"probe failed", 1)
        requests = json.loads(argv[-1])
        out: list[dict[str, Any]] = []
        for index, request in enumerate(requests):
            row = self._rows.get(request["raw"])
            if row is None:
                out.append(
                    {
                        "index": index,
                        "kind": request.get("kind", "path"),
                        "raw": request["raw"],
                        "path": request["raw"],
                        "exists": False,
                    }
                )
            else:
                out.append(
                    {"index": index, "kind": request.get("kind", "path"), **row}
                )
        return _Result(json.dumps(out).encode())


def _container_row(
    path: str,
    *,
    exists: bool = True,
    executable: bool = False,
    is_file: bool = True,
    dev: int = 41,
    ino: int = 7,
) -> dict[str, Any]:
    return {
        "raw": path,
        "path": path,
        "exists": exists,
        "executable": executable,
        "is_dir": not is_file,
        "is_file": is_file,
        "dev": dev,
        "ino": ino,
    }


class TestContainerResolution:
    def test_a_container_only_path_resolves_to_the_container_inode(self) -> None:
        session = _ProbeSession({"/apf-container-only": _container_row("/apf-container-only")})
        collector = CollectingPathResolver()
        classify("sh /apf-container-only", None, resolver=collector)

        probes = asyncio.run(resolve_paths_in_container(session, collector.requests))

        assert probes is not None
        action = classify(
            "sh /apf-container-only", None, resolver=container_path_resolver(probes)
        )
        target = next(t for t in action.targets if t.raw == "/apf-container-only")
        assert target.resolution is Resolution.PATH
        assert target.ref is not None
        assert target.ref.inode_key == (41, 7), "the container's inode, not the host's"

    def test_a_host_path_absent_in_the_container_carries_no_inode(self) -> None:
        """The host has /etc/passwd; the container probe says it is absent."""
        session = _ProbeSession({})
        collector = CollectingPathResolver()
        classify("sh /etc/passwd", None, resolver=collector)

        probes = asyncio.run(resolve_paths_in_container(session, collector.requests))

        assert probes is not None
        action = classify("sh /etc/passwd", None, resolver=container_path_resolver(probes))
        target = next(t for t in action.targets if t.raw == "/etc/passwd")
        assert target.resolution is Resolution.PATH
        assert target.ref is not None and target.ref.inode_key is None

    def test_the_collector_records_candidates_the_host_would_filter_out(self) -> None:
        """A non-executable operand is still a request: the container decides its mode."""
        collector = CollectingPathResolver()
        classify("sh /workspace/script.sh", None, resolver=collector)
        raws = {request.raw for request in collector.requests}
        assert "/workspace/script.sh" in raws

    def test_a_bare_word_is_resolved_on_the_container_path(self) -> None:
        session = _ProbeSession(
            {
                "nmap": {
                    "raw": "nmap",
                    "path": "/usr/bin/nmap",
                    "exists": True,
                    "executable": True,
                    "is_dir": False,
                    "is_file": True,
                    "dev": 41,
                    "ino": 9,
                }
            }
        )
        collector = CollectingPathResolver()
        classify("nmap -sV target", None, resolver=collector)
        assert any(request.kind == "which" and request.raw == "nmap" for request in collector.requests)

        probes = asyncio.run(resolve_paths_in_container(session, collector.requests))

        assert probes is not None
        action = classify("nmap -sV target", None, resolver=container_path_resolver(probes))
        target = next(t for t in action.targets if t.raw == "/usr/bin/nmap")
        assert target.ref is not None and target.ref.inode_key == (41, 9)

    def test_an_unobservable_probe_is_the_refusing_shape(self) -> None:
        session = _ProbeSession({}, fail=True)
        collector = CollectingPathResolver()
        classify("sh /apf-container-only", None, resolver=collector)

        probes = asyncio.run(resolve_paths_in_container(session, collector.requests))

        assert probes is None
        action = classify(
            "sh /apf-container-only", None, resolver=UnresolvedPathResolver()
        )
        target = next(t for t in action.targets if t.raw == "/apf-container-only")
        assert target.resolution is Resolution.UNRESOLVED

    def test_an_unanswered_request_is_unresolved_not_host_resolved(self) -> None:
        resolver = ResolvedPathResolver({})
        probe = resolver.probe("/etc/passwd", None)
        assert probe.resolved.resolution is Resolution.UNRESOLVED
        assert probe.exists is False

    def test_the_host_resolver_is_the_named_fallback(self) -> None:
        probe = HostPathResolver().probe("/etc/passwd", None)
        assert probe.resolved.resolution is Resolution.PATH
        assert probe.exists is True

    def test_the_probe_is_argv_form_and_never_a_shell(self) -> None:
        session = _ProbeSession({})
        asyncio.run(
            resolve_paths_in_container(session, (PathRequest(raw="/x", cwd=None),))
        )
        argv, shell = session.calls[0]
        assert shell is False
        assert argv[0] == "/usr/bin/env"
        assert "/usr/bin/python3" in argv
        assert "-c" in argv

    def test_an_empty_request_set_makes_no_observation(self) -> None:
        session = _ProbeSession({})
        probes = asyncio.run(resolve_paths_in_container(session, ()))
        assert probes == {}
        assert session.calls == []


class TestNamedPathExtraction:
    """S-4: the classifier sees the paths a command names, including fused flags."""

    def test_a_fused_flag_value_is_a_named_path(self) -> None:
        """``--file=/path`` carries a path; the tainted-path check fires on it."""
        path = "/workspace/scratch/implant.sh"
        session = _ProbeSession({path: _container_row(path)})
        collector = CollectingPathResolver()
        classify(f"Rscript --file={path}", None, resolver=collector)
        assert any(request.raw == path for request in collector.requests)

        probes = asyncio.run(resolve_paths_in_container(session, collector.requests))

        assert probes is not None
        action = classify(
            f"Rscript --file={path}", None, resolver=container_path_resolver(probes)
        )
        assert [target.raw for target in action.named_paths] == [path]
        ledger = ProvenanceLedger()
        ledger.record(path, engagement_envelope())
        decision = decide_action(action, ledger)
        assert (decision.verdict, decision.reason) == (
            "DENY",
            ReasonCode.UNLISTED_INTERPRETER,
        )

    def test_a_bare_flag_and_a_short_cluster_are_not_paths(self) -> None:
        """Only the long fused form carries a value; a bare flag and ``-abc`` do not."""
        collector = CollectingPathResolver()
        classify("tool --verbose -abc --empty=", None, resolver=collector)
        raws = {request.raw for request in collector.requests}
        assert "--verbose" not in raws
        assert "-abc" not in raws
        assert "--empty=" not in raws

    def test_a_container_only_tainted_path_named_by_an_unlisted_head_denies(self) -> None:
        """S-4 + S-5: the container-resolved path's provenance fires the deny."""
        path = "/workspace/scratch/implant.sh"
        session = _ProbeSession({path: _container_row(path)})
        collector = CollectingPathResolver()
        classify(f"tclsh {path}", None, resolver=collector)

        probes = asyncio.run(resolve_paths_in_container(session, collector.requests))

        assert probes is not None
        action = classify(f"tclsh {path}", None, resolver=container_path_resolver(probes))
        named = next(target for target in action.named_paths if target.raw == path)
        assert named.ref is not None and named.ref.inode_key == (41, 7)
        ledger = ProvenanceLedger()
        ledger.record(path, engagement_envelope())
        decision = decide_action(action, ledger)
        assert (decision.verdict, decision.reason) == (
            "DENY",
            ReasonCode.UNLISTED_INTERPRETER,
        )
