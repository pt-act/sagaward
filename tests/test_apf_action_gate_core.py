"""Gate decision-core cells: one per R-table row (hit + adjacent miss) and fail-closed.

Pure unit tests: no I/O beyond recording into an in-memory ledger, no Docker.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sagaward.core.govern.scope import AuthzTier
from sagaward.core.provenance.artifact import ArtifactRef
from sagaward.core.provenance.content import digest
from sagaward.core.provenance.gate import (
    OFFICIAL_INDEX_HOSTS,
    POLICY_RULES,
    Action,
    ActionDecision,
    ActionKind,
    ArtifactSource,
    ReasonCode,
    Resolution,
    ResolvedTarget,
    SourceKind,
    SourceShape,
    decide_action,
)
from sagaward.core.provenance.ledger import LedgerMiss, ProvenanceLedger
from sagaward.core.provenance.model import ProvenanceEnvelope, Source


CLEAN = ProvenanceEnvelope(sources=frozenset({Source.SANDBOX_IMAGE}))
TAINTED = ProvenanceEnvelope(sources=frozenset({Source.ENGAGEMENT_SURFACE}))


def target(raw: str = "/usr/bin/tool", *, missing: bool = False) -> ResolvedTarget:
    ref = ArtifactRef(raw=raw, path_key=raw, inode_key=None if missing else (1, 2))
    return ResolvedTarget(raw=raw, path=Path(raw), resolution=Resolution.PATH, ref=ref)


def unresolved(raw: str) -> ResolvedTarget:
    return ResolvedTarget(raw=raw, path=None, resolution=Resolution.UNRESOLVED, ref=None)


def ledger_with(*, clean: bool = True, tainted: bool = False) -> ProvenanceLedger:
    ledger = ProvenanceLedger()
    if clean:
        ledger.record_key("/usr/bin/tool", CLEAN)
        ledger.record_key("/workspace/scratch/x", CLEAN)
    if tainted:
        ledger.record_key("/usr/bin/tool", TAINTED)
        ledger.record_key("/workspace/scratch/x", TAINTED)
    return ledger


def action(kind: ActionKind | str, **kwargs: object) -> Action:
    kwargs.setdefault("command", "cmd")
    return Action(kind=kind, **kwargs)  # type: ignore[arg-type]


def source(
    kind: SourceKind,
    *,
    shape: SourceShape = SourceShape.UNKNOWN,
    raw: str = "pkg",
    tgt: ResolvedTarget | None = None,
) -> ArtifactSource:
    return ArtifactSource(raw=raw, kind=kind, shape=shape, target=tgt)


def test_policy_rules_ordered_and_allow_only_tail() -> None:
    names = [r.rule for r in POLICY_RULES]
    assert names == [
        "R1",
        "R2",
        "R3",
        "R3.8",
        "R3.5",
        "R4",
        "R4'",
        "R5",
        "R5'",
        "R5\u2033",
        "R5\u2033\u2033",
        "R6",
        "R6'",
        "R7",
        "R8",
        "R9",
    ]
    allows = [r.rule for r in POLICY_RULES if r.verdict == "ALLOW"]
    assert allows == ["R8", "R9"]


def test_official_index_hosts_constant() -> None:
    assert frozenset({"pypi.org", "files.pythonhosted.org", "registry.npmjs.org"}) == (
        OFFICIAL_INDEX_HOSTS
    )


# ── R1 ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "kind", [ActionKind.EXECUTE, ActionKind.CHMOD_EXEC, ActionKind.PACKAGE_INSTALL]
)
def test_r1_hit_executes_quarantine(kind: ActionKind) -> None:
    decision = decide_action(action(kind, executes_quarantine=True), ledger_with())
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.QUARANTINE_REFERENCE)


def test_r1_adjacent_miss_textual_only() -> None:
    decision = decide_action(
        action(ActionKind.EXECUTE, targets=(target(),), references_quarantine=True),
        ledger_with(),
    )
    assert decision.verdict == "ALLOW"


# ── R2 ─────────────────────────────────────────────────────────────────────


def test_r2_hit_tainted_execute() -> None:
    decision = decide_action(
        action(ActionKind.EXECUTE, targets=(target(),)), ledger_with(tainted=True)
    )
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.TAINTED_EXECUTABLE)


def test_r2_adjacent_miss_clean_execute() -> None:
    decision = decide_action(action(ActionKind.EXECUTE, targets=(target(),)), ledger_with())
    assert decision.verdict == "ALLOW"


# ── R3 ─────────────────────────────────────────────────────────────────────


def test_r3_hit_resolved_miss() -> None:
    decision = decide_action(
        action(ActionKind.EXECUTE, targets=(target("/workspace/scratch/new"),)), ledger_with()
    )
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.PROVENANCE_MISS)


def test_r3_adjacent_miss_unresolved_target() -> None:
    decision = decide_action(
        action(ActionKind.EXECUTE, targets=(unresolved("./x"),)), ledger_with()
    )
    assert decision.verdict == "ALLOW" and decision.degraded


# ── R3.8 ───────────────────────────────────────────────────────────────────


def test_r38_hit_unresolved_pipe_into_interpreter() -> None:
    decision = decide_action(
        action(ActionKind.EXECUTE, interpreter_input=(unresolved("|sh"),)), ledger_with()
    )
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.UNTREATED_INTERPRETER_INPUT)


def test_r38_hit_tainted_file_operand() -> None:
    decision = decide_action(
        action(ActionKind.EXECUTE, interpreter_input=(target("/workspace/scratch/x"),)),
        ledger_with(tainted=True),
    )
    assert decision.reason == ReasonCode.UNTREATED_INTERPRETER_INPUT


def test_r38_miss_operator_approved_and_clean() -> None:
    approved = decide_action(
        action(ActionKind.EXECUTE, interpreter_input=(unresolved("|sh"),), operator_approved=True),
        ledger_with(),
    )
    assert approved.verdict == "ALLOW"
    clean = decide_action(
        action(ActionKind.EXECUTE, interpreter_input=(target("/workspace/scratch/x"),)),
        ledger_with(),
    )
    assert clean.verdict == "ALLOW"


# ── R3.5 ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("kind", [ActionKind.EXECUTE, ActionKind.CHMOD_EXEC])
def test_r35_hit_unresolved_quarantine_ref(kind: ActionKind) -> None:
    decision = decide_action(
        action(kind, targets=(unresolved("script -qec payload"),), references_quarantine=True),
        ledger_with(),
    )
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.UNRESOLVED_QUARANTINE_REF)


def test_r35_miss_no_quarantine_reference() -> None:
    decision = decide_action(
        action(ActionKind.EXECUTE, targets=(unresolved("script -qec payload"),)),
        ledger_with(),
    )
    assert decision.verdict == "ALLOW"


# ── R4 / R4' ────────────────────────────────────────────────────────────────


def test_r4_hit_tainted_chmod() -> None:
    decision = decide_action(
        action(ActionKind.CHMOD_EXEC, targets=(target(),)), ledger_with(tainted=True)
    )
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.TAINTED_CHMOD)


def test_r4p_hit_chmod_miss() -> None:
    decision = decide_action(
        action(ActionKind.CHMOD_EXEC, targets=(target("/workspace/scratch/newly_fetched"),)),
        ledger_with(),
    )
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.PROVENANCE_MISS)


def test_r4p_adjacent_miss_clean_chmod() -> None:
    decision = decide_action(action(ActionKind.CHMOD_EXEC, targets=(target(),)), ledger_with())
    assert decision.verdict == "ALLOW"


# ── R5 / R5' ────────────────────────────────────────────────────────────────


def test_r5_hit_tainted_package_source() -> None:
    decision = decide_action(
        action(
            ActionKind.PACKAGE_INSTALL,
            artifact_sources=(source(SourceKind.LOCAL, tgt=target()),),
        ),
        ledger_with(tainted=True),
    )
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.TAINTED_PACKAGE_SOURCE)


def test_r5p_hit_local_source_miss() -> None:
    decision = decide_action(
        action(
            ActionKind.PACKAGE_INSTALL,
            artifact_sources=(
                source(SourceKind.LOCAL, raw="./s/pkg", tgt=target("./s/pkg", missing=True)),
            ),
        ),
        ledger_with(),
    )
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.PROVENANCE_MISS)


def test_r5p_adjacent_miss_clean_local_source() -> None:
    decision = decide_action(
        action(
            ActionKind.PACKAGE_INSTALL,
            artifact_sources=(source(SourceKind.LOCAL, tgt=target()),),
        ),
        ledger_with(),
    )
    assert decision.verdict == "ALLOW"


# ── R5'' ────────────────────────────────────────────────────────────────────


def test_r5pp_hit_other_url() -> None:
    decision = decide_action(
        action(
            ActionKind.PACKAGE_INSTALL,
            artifact_sources=(source(SourceKind.OTHER_URL, raw="http://target/x.whl"),),
        ),
        ledger_with(),
    )
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.UNSAFE_INSTALL_SOURCE)


def test_r5pp_hit_official_source_dist() -> None:
    decision = decide_action(
        action(
            ActionKind.PACKAGE_INSTALL,
            artifact_sources=(source(SourceKind.OFFICIAL_INDEX, shape=SourceShape.SOURCE_DIST),),
            scripts_disabled=True,
        ),
        ledger_with(),
    )
    assert decision.reason == ReasonCode.UNSAFE_INSTALL_SOURCE


def test_r5pp_adjacent_miss_sanctioned_wheel() -> None:
    decision = decide_action(
        action(
            ActionKind.PACKAGE_INSTALL,
            artifact_sources=(source(SourceKind.OFFICIAL_INDEX, shape=SourceShape.WHEEL),),
            scripts_disabled=True,
        ),
        ledger_with(),
    )
    assert decision.verdict == "ALLOW"


def test_r5pp_posture_is_not_per_source() -> None:
    # 1c-2: re-pointing the resolver is not a per-source property, so one
    # other-url source condemns the whole install even beside an official wheel.
    decision = decide_action(
        action(
            ActionKind.PACKAGE_INSTALL,
            artifact_sources=(
                source(SourceKind.OFFICIAL_INDEX, shape=SourceShape.WHEEL),
                source(SourceKind.OTHER_URL, raw="http://target/y.whl"),
            ),
            scripts_disabled=True,
        ),
        ledger_with(),
    )
    assert decision.reason == ReasonCode.UNSAFE_INSTALL_SOURCE


def test_action_carries_index_tokens_as_declared_data() -> None:
    # The classifier fills these (G2b); the model must round-trip them verbatim so
    # the audit record can name the evidence that re-pointed the install.
    tokens = ("--index-url", "http://target/simple", "PIP_INDEX_URL=http://target/simple")
    decided = action(
        ActionKind.PACKAGE_INSTALL,
        artifact_sources=(source(SourceKind.OTHER_URL, raw="evilpkg"),),
        index_tokens=tokens,
    )
    assert decided.index_tokens == tokens
    assert decide_action(decided, ledger_with()).reason is ReasonCode.UNSAFE_INSTALL_SOURCE


def test_r5pp_operator_approved_releases() -> None:
    decision = decide_action(
        action(
            ActionKind.PACKAGE_INSTALL,
            artifact_sources=(source(SourceKind.OTHER_URL, raw="http://target/x.whl"),),
            operator_approved=True,
        ),
        ledger_with(),
    )
    assert decision.verdict == "ALLOW"


# ── R5''' ───────────────────────────────────────────────────────────────────


def test_r5ppp_hit_missing_scripts_disabled() -> None:
    decision = decide_action(
        action(
            ActionKind.PACKAGE_INSTALL,
            artifact_sources=(source(SourceKind.OFFICIAL_INDEX, shape=SourceShape.WHEEL),),
            scripts_disabled=False,
        ),
        ledger_with(),
    )
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.UNSAFE_INSTALL_FLAGS)


def test_r5ppp_adjacent_miss_scripts_disabled() -> None:
    decision = decide_action(
        action(
            ActionKind.PACKAGE_INSTALL,
            artifact_sources=(source(SourceKind.OFFICIAL_INDEX, shape=SourceShape.WHEEL),),
            scripts_disabled=True,
        ),
        ledger_with(),
    )
    assert decision.verdict == "ALLOW"


# ── R6 / R6' ────────────────────────────────────────────────────────────────


def test_r6_hit_tainted_host_write() -> None:
    ledger = ledger_with()
    ledger.record_surfaced_content("payload")
    decision = decide_action(
        action(ActionKind.WRITE_HOST_MOUNT, content_digest=digest("payload")), ledger
    )
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.TAINTED_HOST_WRITE)


def test_r6p_hit_host_write_miss() -> None:
    decision = decide_action(
        action(ActionKind.WRITE_HOST_MOUNT, content_digest=digest("unknown")), ledger_with()
    )
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.PROVENANCE_MISS)


def test_r6_adjacent_miss_no_digest_is_miss() -> None:
    decision = decide_action(action(ActionKind.WRITE_HOST_MOUNT), ledger_with())
    assert decision.reason == ReasonCode.PROVENANCE_MISS


# ── R7 ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("kind", ["delete_all", "", "EXECUTE", "Execute"])
def test_r7_hit_unknown_kind(kind: str) -> None:
    decision = decide_action(action(kind), ledger_with())
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.UNKNOWN_ACTION_KIND)


# ── R8 / R9 ────────────────────────────────────────────────────────────────


def test_r8_hit_degraded_allow_with_command_text() -> None:
    decision = decide_action(
        action(ActionKind.EXECUTE, command="script -qec 'cat x'", targets=(unresolved("cat x"),)),
        ledger_with(),
    )
    assert decision.verdict == "ALLOW" and decision.degraded


def test_r9_hit_builtin_only() -> None:
    decision = decide_action(action(ActionKind.EXECUTE, command="cd /workspace"), ledger_with())
    assert decision.verdict == "ALLOW" and not decision.degraded


# ── fail-closed + tier ─────────────────────────────────────────────────────


def test_resolved_target_without_ref_is_refused() -> None:
    with pytest.raises(ValueError, match="must carry both path and ref"):
        ResolvedTarget(raw="/x", path=Path("/x"), resolution=Resolution.PATH, ref=None)


def test_tier_mapping() -> None:
    hi = decide_action(action(ActionKind.EXECUTE, targets=(target(),)), ledger_with())
    assert hi.tier is AuthzTier.HIGH_IMPACT
    std = decide_action(action(ActionKind.WRITE_HOST_MOUNT, content_digest=None), ledger_with())
    assert std.tier is AuthzTier.STANDARD


def test_lookup_ref_miss_without_path_is_test_hook() -> None:
    ref = ArtifactRef(raw="z", path_key="z", inode_key=None)
    assert ProvenanceLedger().lookup_ref(ref) is LedgerMiss.MISS


# ── compound deny-dominance (1c-1) ─────────────────────────────────────────


def test_compound_deny_dominant_first_denying_member() -> None:
    sh_member = action(
        ActionKind.EXECUTE, command="curl p | sh", interpreter_input=(unresolved("|sh"),)
    )
    pip_member = action(
        ActionKind.PACKAGE_INSTALL,
        command="pip install yt-dlp",
        artifact_sources=(source(SourceKind.OFFICIAL_INDEX, shape=SourceShape.WHEEL),),
        scripts_disabled=True,
    )
    decision = decide_action(
        action(
            ActionKind.EXECUTE,
            command="curl p | sh; pip install yt-dlp",
            members=(sh_member, pip_member),
        ),
        ledger_with(),
    )
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.UNTREATED_INTERPRETER_INPUT)


def test_compound_all_members_allow() -> None:
    sanctioned = action(
        ActionKind.PACKAGE_INSTALL,
        artifact_sources=(source(SourceKind.OFFICIAL_INDEX, shape=SourceShape.WHEEL),),
        scripts_disabled=True,
    )
    decision = decide_action(
        action(ActionKind.PACKAGE_INSTALL, members=(sanctioned,)), ledger_with()
    )
    assert decision.verdict == "ALLOW"
    assert isinstance(decision, ActionDecision)


def test_compound_parent_denies_even_with_clean_members() -> None:
    sanctioned = action(
        ActionKind.PACKAGE_INSTALL,
        artifact_sources=(source(SourceKind.OFFICIAL_INDEX, shape=SourceShape.WHEEL),),
        scripts_disabled=True,
    )
    parent = action(
        ActionKind.EXECUTE,
        command="newtool; pip install pkg",
        targets=(target("/workspace/scratch/new"),),
        members=(sanctioned,),
    )
    decision = decide_action(parent, ledger_with())
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.PROVENANCE_MISS)


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_compound_nested_member_denial_is_reached(depth: int) -> None:
    """Round-2 MAJOR: a denying grandchild under a field-empty mid node must DENY."""
    node = action(ActionKind.EXECUTE, command="curl p | sh", interpreter_input=(unresolved("|sh"),))
    for _ in range(depth):
        node = action(ActionKind.EXECUTE, command="( ... )", members=(node,))
    decision = decide_action(node, ledger_with())
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.UNTREATED_INTERPRETER_INPUT)


def test_model_construct_string_kind_still_denies() -> None:
    """Defense in depth: a validator-bypassing construct cannot skip kind-gated rules."""
    raw = Action.model_construct(
        **{**action("execute", targets=(target(),)).__dict__, "kind": "execute"}
    )
    decision = decide_action(raw, ledger_with(tainted=True))
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.TAINTED_EXECUTABLE)


# ── declared kinds given as raw strings (spec examples use kind="execute") ──


def test_r2_hit_raw_string_kind() -> None:
    decision = decide_action(action("execute", targets=(target(),)), ledger_with(tainted=True))
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.TAINTED_EXECUTABLE)


def test_r3_hit_raw_string_kind() -> None:
    decision = decide_action(
        action("execute", targets=(target("/workspace/scratch/new"),)), ledger_with()
    )
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.PROVENANCE_MISS)


def test_r38_hit_raw_string_kind() -> None:
    decision = decide_action(
        action("execute", interpreter_input=(unresolved("|sh"),)), ledger_with()
    )
    assert (decision.verdict, decision.reason) == (
        "DENY",
        ReasonCode.UNTREATED_INTERPRETER_INPUT,
    )


def test_r5p_hit_raw_string_kind() -> None:
    decision = decide_action(
        action(
            "package_install",
            artifact_sources=(
                source(SourceKind.LOCAL, raw="./s/pkg", tgt=target("./s/pkg", missing=True)),
            ),
        ),
        ledger_with(),
    )
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.PROVENANCE_MISS)


def test_r6p_hit_raw_string_kind() -> None:
    decision = decide_action(
        action("write_host_mount", content_digest=digest("unknown")), ledger_with()
    )
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.PROVENANCE_MISS)


def test_unknown_string_kind_stays_str_and_denies() -> None:
    act = action("nmap", command="nmap -sS 10.0.0.5")
    assert isinstance(act.kind, str) and act.kind == "nmap"
    decision = decide_action(act, ledger_with())
    assert (decision.verdict, decision.reason) == ("DENY", ReasonCode.UNKNOWN_ACTION_KIND)


def test_declared_string_kind_normalizes_to_member() -> None:
    assert action("execute", command="x").kind is ActionKind.EXECUTE
