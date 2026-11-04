"""Tests for strix.core.provenance — the action-fence origin ledger.

Covers AC-1..AC-9 of apf-provenance. AC-10 (tool-boundary wiring) lives in
``tests/test_apf_provenance_wiring.py``.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from enum import Enum
from pathlib import Path

import pytest

from strix.core.govern.scope import AuthzTier
from strix.core.provenance import (
    ArtifactRef,
    DeclassifyForbidden,
    Label,
    LedgerMiss,
    Principal,
    ProvenanceEnvelope,
    ProvenanceLedger,
    Source,
    canonical_path,
    default_image_roots,
    seed_image_inventory,
)


PACKAGE_DIR = Path(__file__).resolve().parent.parent / "strix" / "core" / "provenance"
_GOVERN_DIR = Path(__file__).resolve().parent.parent / "strix" / "core" / "govern"
_RULED_EDGE_MODULE = "strix.core.govern.scope"


def _absolute(module_file: Path, node: ast.ImportFrom) -> str:
    """Resolve ``from ..x import y`` against the file's package so relative edges are checked."""
    if not node.level:
        return node.module or ""
    rel = module_file.resolve().relative_to(Path(__file__).resolve().parent.parent)
    package = list(rel.with_suffix("").parts[:-1])
    base = package[: len(package) - (node.level - 1)] if node.level > 1 else package
    return ".".join([*base, *([node.module] if node.module else [])])


_ENGINE_ROOTS = frozenset(
    {"docker", "httpx", "requests", "aiohttp", "litellm", "openai", "agents", "caido"}
)
ALLOWED_IMPORT_ROOTS = frozenset(
    {
        "__future__",
        "collections",
        "dataclasses",
        "datetime",
        "enum",
        "functools",
        "hashlib",
        "contextlib",
        "json",
        "logging",
        "os",
        "pathlib",
        "threading",
        "time",
        "typing",
        "pydantic",
        "strix",
        # apf-action-gate G2a: the shell parser for classify.py. One root, one
        # consumer; no other third-party import may join this set silently.
        "bashlex",
        # classify.py / install_grammar.py stdlib: tokenising (re, shlex) and
        # RFC-3986 host extraction (urllib, 1c-5).
        "re",
        "shlex",
        "urllib",
    },
)


def _engagement() -> ProvenanceEnvelope:
    return ProvenanceEnvelope.of(Source.ENGAGEMENT_SURFACE, Label.INSTRUCTION_BEARING)


class TestEngagementContentIsTainted:
    """AC-1 — content fetched from the engagement surface is tainted."""

    def test_fetched_runbook_is_tainted(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()
        runbook = tmp_path / "quarantine" / "instructions.txt"

        envelope = ledger.record(runbook, _engagement())

        assert envelope.is_tainted() is True
        looked_up = ledger.lookup(runbook)
        assert isinstance(looked_up, ProvenanceEnvelope)
        assert looked_up.is_tainted() is True
        assert looked_up.labels == frozenset({Label.INSTRUCTION_BEARING})

    def test_downloaded_binary_is_tainted(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()
        binary = tmp_path / "quarantine" / "credman"

        ledger.record(binary, ProvenanceEnvelope.of(Source.ENGAGEMENT_SURFACE, Label.BINARY))

        looked_up = ledger.lookup(binary)
        assert isinstance(looked_up, ProvenanceEnvelope)
        assert looked_up.is_tainted() is True


class TestCleanOrigins:
    """AC-2 / AC-3 — image and model-authored artifacts are not tainted."""

    @pytest.mark.parametrize("binary", ["nmap", "ffuf", "nuclei", "sqlmap", "python3"])
    def test_image_binaries_are_clean(self, binary: str) -> None:
        ledger = ProvenanceLedger()
        path = Path("/usr/bin") / binary

        envelope = ledger.record(path, ProvenanceEnvelope.of(Source.SANDBOX_IMAGE, Label.BINARY))

        assert envelope.is_tainted() is False
        assert envelope.sources == frozenset({Source.SANDBOX_IMAGE})

    def test_model_authored_script_is_clean(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()
        script = tmp_path / "scratch" / "scan.py"

        envelope = ledger.record(script, ProvenanceEnvelope.of(Source.MODEL_AUTHORED, Label.SCRIPT))

        assert envelope.is_tainted() is False
        assert envelope.sources == frozenset({Source.MODEL_AUTHORED})

    def test_operator_supplied_file_is_clean(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()

        envelope = ledger.record(
            tmp_path / "cookies.txt",
            ProvenanceEnvelope.of(Source.OPERATOR, Label.INSTRUCTION_BEARING),
        )

        assert envelope.is_tainted() is False


class TestMonotoneTaint:
    """AC-4 — derivation propagates taint through copies, renames and appends."""

    def test_single_derivation_inherits_taint(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()
        source = tmp_path / "quarantine" / "instructions.txt"
        leaf = tmp_path / "scratch" / "notes.py"
        ledger.record(source, _engagement())

        envelope = ledger.mark_derived(leaf, source)

        assert envelope.is_tainted() is True
        assert ledger.lookup(leaf).is_tainted() is True  # type: ignore[union-attr]

    @pytest.mark.parametrize("depth", [1, 2, 3, 4, 5])
    def test_chain_of_any_length_stays_tainted(self, tmp_path: Path, depth: int) -> None:
        ledger = ProvenanceLedger()
        source = ledger.record(tmp_path / "n0", _engagement())

        previous = Path(tmp_path / "n0")
        for step in range(1, depth + 1):
            current = tmp_path / f"n{step}"
            ledger.mark_derived(current, previous)
            previous = current

        leaf = ledger.lookup(previous)
        assert isinstance(leaf, ProvenanceEnvelope)
        assert leaf.is_tainted() is True
        assert source.is_tainted() is True

    def test_merging_only_adds_sources(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()
        path = tmp_path / "artifact"

        ledger.record(path, ProvenanceEnvelope.of(Source.MODEL_AUTHORED))
        merged = ledger.record(path, ProvenanceEnvelope.of(Source.ENGAGEMENT_SURFACE))

        assert merged.sources == frozenset({Source.MODEL_AUTHORED, Source.ENGAGEMENT_SURFACE})
        assert merged.is_tainted() is True

    def test_unrecorded_ancestor_taints_and_is_flagged(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()

        envelope = ledger.mark_derived(tmp_path / "leaf", tmp_path / "never-recorded")

        assert envelope.is_tainted() is True
        assert ledger.is_inferred(tmp_path / "leaf") is True

    def test_known_ancestor_is_not_flagged_inferred(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()
        source = tmp_path / "quarantine" / "x"
        ledger.record(source, _engagement())

        ledger.mark_derived(tmp_path / "leaf", source)

        assert ledger.is_inferred(tmp_path / "leaf") is False

    def test_derivation_edges_are_exposed(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()
        source = tmp_path / "a"
        leaf = tmp_path / "b"
        ledger.record(source, _engagement())

        ledger.mark_derived(leaf, source)

        edges = ledger.operators()
        assert edges[canonical_path(leaf)] == frozenset({canonical_path(source)})


class TestNoModelReachableClear:
    """AC-5 — nothing reachable by the model can turn taint off."""

    def test_ledger_exposes_no_clearing_method_but_the_guarded_one(self) -> None:
        names = {name for name in dir(ProvenanceLedger) if not name.startswith("_")}

        assert "declassify" in names
        assert not names & {"clear", "untaint", "reset", "forget", "purge"}

    def test_long_mutation_sequence_never_clears(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()
        path = tmp_path / "artifact"
        ledger.record(path, _engagement())

        other = tmp_path / "other"
        ledger.record(other, ProvenanceEnvelope.of(Source.MODEL_AUTHORED))
        for _ in range(10):
            ledger.record(path, ProvenanceEnvelope.of(Source.MODEL_AUTHORED))
            ledger.mark_derived(other, path)
            ledger.record(other, ProvenanceEnvelope.of(Source.SANDBOX_IMAGE))

        assert ledger.lookup(path).is_tainted() is True  # type: ignore[union-attr]
        assert ledger.lookup(other).is_tainted() is True  # type: ignore[union-attr]


class TestDeclassify:
    """AC-6 — only the operator principal can clear taint, and it is audited."""

    @pytest.mark.parametrize(
        "principal",
        [Principal.MODEL, Principal.SANDBOX, Principal.TOOL],
    )
    def test_non_operator_principals_are_refused(
        self,
        tmp_path: Path,
        principal: Principal,
    ) -> None:
        ledger = ProvenanceLedger()
        path = tmp_path / "artifact"
        ledger.record(path, _engagement())

        with pytest.raises(DeclassifyForbidden):
            ledger.declassify(path, principal)

        assert ledger.lookup(path).is_tainted() is True  # type: ignore[union-attr]
        assert ledger.declassifications() == ()

    def test_operator_clears_and_is_audited(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()
        path = tmp_path / "artifact"
        ledger.record(path, _engagement())

        cleared = ledger.declassify(path, Principal.OPERATOR)

        assert cleared.is_tainted() is False
        assert cleared.sources == frozenset({Source.OPERATOR})
        audit = ledger.declassifications()
        assert len(audit) == 1
        assert audit[0].path == canonical_path(path)
        assert audit[0].principal is Principal.OPERATOR
        assert audit[0].at.tzinfo is not None

    def test_operator_keeps_other_sources(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()
        path = tmp_path / "artifact"
        ledger.record(
            path,
            ProvenanceEnvelope(
                sources=frozenset({Source.ENGAGEMENT_SURFACE, Source.MODEL_AUTHORED}),
                labels=frozenset({Label.SCRIPT}),
            ),
        )

        cleared = ledger.declassify(path, Principal.OPERATOR)

        assert cleared.sources == frozenset({Source.MODEL_AUTHORED})
        assert cleared.labels == frozenset({Label.SCRIPT})

    def test_declassify_clears_inferred_flag(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()
        leaf = tmp_path / "leaf"
        ledger.mark_derived(leaf, tmp_path / "unknown")
        assert ledger.is_inferred(leaf) is True

        ledger.declassify(leaf, Principal.OPERATOR)

        assert ledger.is_inferred(leaf) is False


class TestCanonicalization:
    """AC-7 — one artifact has one key, whichever spelling reaches it."""

    def test_parent_traversal_resolves_to_same_key(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()
        artifact = tmp_path / "quarantine" / "credman"
        ledger.record(artifact, _engagement())

        via_dotdot = tmp_path / "quarantine" / "sub" / ".." / "credman"

        assert ledger.lookup(via_dotdot).is_tainted() is True  # type: ignore[union-attr]

    def test_symlink_resolves_to_same_key(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()
        artifact = tmp_path / "quarantine" / "credman"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("#!/bin/sh\n", encoding="utf-8")
        link = tmp_path / "scratch-link"
        link.symlink_to(artifact)
        ledger.record(artifact, _engagement())

        assert ledger.lookup(link).is_tainted() is True  # type: ignore[union-attr]

    def test_hardlink_resolves_to_same_key(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()
        artifact = tmp_path / "quarantine" / "credman"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("#!/bin/sh\n", encoding="utf-8")
        hardlink = tmp_path / "scratch-copy"
        hardlink.hardlink_to(artifact)
        ledger.record(artifact, _engagement())

        assert ledger.lookup(hardlink).is_tainted() is True  # type: ignore[union-attr]


class TestMissIsNotClean:
    """AC-8 — an unknown path is unverified, not image provenance."""

    def test_unknown_path_returns_miss(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()

        result = ledger.lookup(tmp_path / "never-recorded")

        assert result is LedgerMiss.MISS
        assert not isinstance(result, ProvenanceEnvelope)

    def test_miss_survives_other_records(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()
        ledger.record(tmp_path / "known", ProvenanceEnvelope.of(Source.SANDBOX_IMAGE))

        assert ledger.lookup(tmp_path / "other") is LedgerMiss.MISS


class TestPackagePurity:
    """AC-9 — no Docker, network, SDK, or engine imports in the package."""

    def test_imports_are_stdlib_pydantic_and_siblings(self) -> None:
        roots: set[str] = set()
        for module in PACKAGE_DIR.glob("*.py"):
            tree = ast.parse(module.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    roots.add(node.module.split(".", maxsplit=1)[0])
                elif isinstance(node, ast.Import):
                    roots.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)

        assert roots <= ALLOWED_IMPORT_ROOTS

    def test_strix_imports_are_package_local_only(self) -> None:
        """Package-local, with ONE ruled edge (operator ruling 2026-11-04, option a).

        ``gate.py`` may import the ``AuthzTier`` enum — a type, used for the decision's
        tier label, never for decide logic — from ``strix.core.govern.scope``. Nothing
        else crosses the package boundary, and no other module may take that edge.
        """
        for module in PACKAGE_DIR.glob("*.py"):
            tree = ast.parse(module.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert not alias.name.startswith("strix") or alias.name.startswith(
                            "strix.core.provenance"
                        ), f"{module.name} imports outside the package: {alias.name}"
                if isinstance(node, ast.ImportFrom):
                    target = _absolute(module, node)
                    if not target.startswith("strix"):
                        continue
                    if target.startswith("strix.core.provenance"):
                        continue
                    names = {alias.name for alias in node.names}
                    assert (module.name, target, names) == (
                        "gate.py",
                        _RULED_EDGE_MODULE,
                        {"AuthzTier"},
                    ), f"{module.name} imports outside the package: {target} {names}"

    def test_ruled_edge_is_a_type_only(self) -> None:
        assert issubclass(AuthzTier, Enum)

    def test_reverse_edge_govern_never_imports_provenance(self) -> None:
        """The DAG stays one-way: govern -> provenance would close a cycle."""
        for module in _GOVERN_DIR.rglob("*.py"):
            tree = ast.parse(module.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                mods: list[str] = []
                if isinstance(node, ast.ImportFrom):
                    mods = [_absolute(module, node)]
                elif isinstance(node, ast.Import):
                    mods = [alias.name for alias in node.names]
                for mod in mods:
                    assert not mod.startswith("strix.core.provenance"), (
                        f"govern/{module.name} imports provenance: {mod}"
                    )

    def test_gate_import_closure_stays_engine_free(self) -> None:
        """Importing the gate loads only the two packages and no SDK/Docker/network libs."""
        code = (
            "import sys\n"
            "import strix.core.provenance.gate\n"
            "print('\\n'.join(sorted(sys.modules)))\n"
        )
        out = subprocess.run(  # noqa: S603 - fixed argv, test-only
            [sys.executable, "-c", code],
            check=True,
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent.parent,
        ).stdout.split()
        strix_mods = {m for m in out if m.startswith("strix.")}
        assert all(
            m in {"strix.core", "strix.core.govern", "strix.core.provenance"}
            or m.startswith(("strix.core.govern.", "strix.core.provenance."))
            for m in strix_mods
        ), strix_mods
        roots = {m.split(".")[0] for m in out}
        assert not roots & _ENGINE_ROOTS, roots & _ENGINE_ROOTS

    def test_envelope_rejects_empty_sources(self) -> None:
        with pytest.raises(ValueError, match="at least one source"):
            ProvenanceEnvelope(sources=frozenset())


class TestImageInventorySeed:
    """AC-2 (population) — image-owned content is recorded before any action."""

    def _bin_dir(self, tmp_path: Path) -> Path:
        bin_dir = tmp_path / "usr" / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "nmap").write_text("#!/bin/sh\n", encoding="utf-8")
        (bin_dir / "nmap").chmod(0o755)
        (bin_dir / "tool.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        (bin_dir / "tool.sh").chmod(0o755)
        (bin_dir / "README").write_text("not executable\n", encoding="utf-8")
        (bin_dir / "README").chmod(0o644)
        return bin_dir

    def test_seeds_executables_only(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()
        bin_dir = self._bin_dir(tmp_path)

        seeded = seed_image_inventory(ledger, [bin_dir])

        assert seeded == 2
        nmap = ledger.lookup(bin_dir / "nmap")
        assert isinstance(nmap, ProvenanceEnvelope)
        assert nmap.sources == frozenset({Source.SANDBOX_IMAGE})
        assert nmap.is_tainted() is False
        assert ledger.lookup(bin_dir / "README") is LedgerMiss.MISS

    def test_seeded_scripts_are_labelled(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()
        bin_dir = self._bin_dir(tmp_path)

        seed_image_inventory(ledger, [bin_dir])

        script = ledger.lookup(bin_dir / "tool.sh")
        assert isinstance(script, ProvenanceEnvelope)
        assert script.labels == frozenset({Label.SCRIPT})

    def test_seed_cannot_overwrite_taint(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()
        bin_dir = self._bin_dir(tmp_path)
        nmap = bin_dir / "nmap"
        ledger.record(nmap, ProvenanceEnvelope.of(Source.ENGAGEMENT_SURFACE, Label.BINARY))

        seed_image_inventory(ledger, [bin_dir])

        after = ledger.lookup(nmap)
        assert isinstance(after, ProvenanceEnvelope)
        assert after.is_tainted() is True
        assert Source.SANDBOX_IMAGE in after.sources

    def test_missing_root_seeds_nothing(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()

        assert seed_image_inventory(ledger, [tmp_path / "absent"]) == 0
        assert len(ledger) == 0

    def test_duplicate_roots_are_counted_once(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()
        bin_dir = self._bin_dir(tmp_path)

        assert seed_image_inventory(ledger, [bin_dir, bin_dir, str(bin_dir)]) == 2

    def test_default_image_roots_dedupes_and_drops_blanks(self) -> None:
        roots = default_image_roots("/usr/bin::/bin:/usr/bin:")

        assert roots == (canonical_path("/usr/bin"), canonical_path("/bin"))

    def test_seed_never_records_engagement_surface(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()
        bin_dir = self._bin_dir(tmp_path)

        seed_image_inventory(ledger, [bin_dir])

        for env in ledger.operators():
            recorded = ledger.lookup(env)
            assert isinstance(recorded, ProvenanceEnvelope)
            assert recorded.is_tainted() is False


class TestPureKeyLookup:
    """Gate AC-10 under ruling (b) — the decision path never touches the filesystem."""

    def test_artifact_ref_carries_path_and_inode_keys(self, tmp_path: Path) -> None:
        artifact = tmp_path / "credman"
        artifact.write_text("#!/bin/sh\n", encoding="utf-8")

        ref = ArtifactRef.resolve(str(artifact))

        assert ref.path_key == str(canonical_path(artifact))
        assert ref.inode_key is not None
        assert ref.is_present() is True

    def test_artifact_ref_for_absent_path_has_no_inode(self, tmp_path: Path) -> None:
        ref = ArtifactRef.resolve(str(tmp_path / "not-yet-written"))

        assert ref.inode_key is None
        assert ref.is_present() is False

    def test_lookup_ref_is_pure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        ledger = ProvenanceLedger()
        artifact = tmp_path / "credman"
        artifact.write_text("#!/bin/sh\n", encoding="utf-8")
        ledger.record(artifact, _engagement())
        ref = ArtifactRef.resolve(str(artifact))

        def _forbidden(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("lookup_ref touched the filesystem")

        monkeypatch.setattr("os.stat", _forbidden)
        monkeypatch.setattr("os.lstat", _forbidden)
        monkeypatch.setattr(Path, "open", _forbidden)
        monkeypatch.setattr(Path, "stat", _forbidden)

        assert ledger.lookup_ref(ref).is_tainted() is True  # type: ignore[union-attr]

    def test_lookup_keys_is_pure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        ledger = ProvenanceLedger()
        artifact = tmp_path / "credman"
        artifact.write_text("#!/bin/sh\n", encoding="utf-8")
        ledger.record(artifact, _engagement())
        ref = ArtifactRef.resolve(str(artifact))

        def _forbidden(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("lookup_keys touched the filesystem")

        monkeypatch.setattr("os.stat", _forbidden)
        monkeypatch.setattr("os.lstat", _forbidden)

        found = ledger.lookup_keys(Path(ref.path_key), ref.inode_key)
        assert found.is_tainted() is True  # type: ignore[union-attr]

    def test_miss_means_neither_index_knows(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()

        result = ledger.lookup_keys(tmp_path / "unknown", (999, 998))

        assert result is LedgerMiss.MISS

    def test_hardlink_ref_resolves_through_inode_key(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()
        artifact = tmp_path / "quarantine" / "credman"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("#!/bin/sh\n", encoding="utf-8")
        ledger.record(artifact, _engagement())
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        hardlink = scratch / "innocent-name"
        hardlink.hardlink_to(artifact)

        ref = ArtifactRef.resolve(str(hardlink))

        found = ledger.lookup_ref(ref)
        assert isinstance(found, ProvenanceEnvelope)
        assert found.is_tainted() is True
        assert ref.path_key != str(canonical_path(artifact))

    def test_unrecorded_path_with_recorded_inode_still_hits(self, tmp_path: Path) -> None:
        ledger = ProvenanceLedger()
        artifact = tmp_path / "quarantine" / "credman"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("#!/bin/sh\n", encoding="utf-8")
        ledger.record(artifact, _engagement())
        link = tmp_path / "same-bytes"
        link.hardlink_to(artifact)
        ref = ArtifactRef.resolve(str(link))

        assert ledger.lookup_keys(Path(ref.path_key)) is LedgerMiss.MISS
        assert ledger.lookup_keys(Path(ref.path_key), ref.inode_key).is_tainted() is True  # type: ignore[union-attr]
