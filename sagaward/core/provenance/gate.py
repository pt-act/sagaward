"""The action gate's pure decision core (apf-action-gate G1).

``decide_action`` evaluates a classified :class:`Action` against the fixed rule
table and returns a frozen :class:`ActionDecision`. It is the only entry point
and it is pure: no I/O, no subprocess, no SDK import — the caller (``classify``)
owns every filesystem touch and hands the gate a snapshot of resolved targets
and artifact sources.

Fail-closed by construction: an unknown ``kind`` denies (R7); a resolved target
with no ledger record denies (R3/R4'/R5'/R6'); a compound is deny-dominant over
its members with the first denying member's code in source order (1c-1).
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path  # noqa: TC003 - resolved at runtime by pydantic model build
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from sagaward.core.govern.scope import AuthzTier
from sagaward.core.provenance.artifact import ArtifactRef  # noqa: TC001 - pydantic runtime
from sagaward.core.provenance.ledger import LedgerMiss, ProvenanceLedger


OFFICIAL_INDEX_HOSTS: frozenset[str] = frozenset(
    {"pypi.org", "files.pythonhosted.org", "registry.npmjs.org"}
)

# S-4: the reviewed readers list. These commands read tainted content and are
# reviewed as safe to read it: the agent must be able to read the target's own
# source. Reading is not exfiltration; the content is already in the sandbox.
TAINT_READERS: frozenset[str] = frozenset({"cat", "grep", "less", "head", "tail"})

# S-4: the commands that pass through without reading the content. They name a
# path but never consume its bytes, so the tainted-path deny does not apply.
TAINT_PASSTHROUGH: frozenset[str] = frozenset({"mkdir", "touch", "chmod"})

# S-4: the exfiltration surface. These commands move tainted content out of the
# sandbox; ``curl`` joins them only in its upload form (``-T``/``--upload-file``).
EXFILTRATION_HEADS: frozenset[str] = frozenset({"tee", "scp", "nc", "ncat", "netcat", "socat"})
CURL_UPLOAD_FLAGS: frozenset[str] = frozenset({"-T", "--upload-file"})


class ActionKind(StrEnum):
    """The four declared action kinds. Anything else is R7 (fail-closed)."""

    EXECUTE = "execute"
    CHMOD_EXEC = "chmod_exec"
    PACKAGE_INSTALL = "package_install"
    WRITE_HOST_MOUNT = "write_host_mount"


class Resolution(StrEnum):
    PATH = "path"
    UNRESOLVED = "unresolved"


class SourceKind(StrEnum):
    LOCAL = "local"
    OFFICIAL_INDEX = "official-index"
    OTHER_URL = "other-url"
    OPERATOR_APPROVED = "operator-approved"


class SourceShape(StrEnum):
    WHEEL = "wheel"
    SOURCE_DIST = "source-dist"
    UNKNOWN = "unknown"


class ReasonCode(StrEnum):
    """Closed enum. A new denial path needs a new code and a spec revision."""

    ALLOWED = "allowed"
    TAINTED_EXECUTABLE = "tainted_executable"
    UNLISTED_INTERPRETER = "unlisted_interpreter"
    QUARANTINE_REFERENCE = "quarantine_reference"
    TAINTED_CHMOD = "tainted_chmod"
    TAINTED_PACKAGE_SOURCE = "tainted_package_source"
    TAINTED_HOST_WRITE = "tainted_host_write"
    UNRESOLVED_QUARANTINE_REF = "unresolved_quarantine_ref"
    UNKNOWN_ACTION_KIND = "unknown_action_kind"
    PROVENANCE_MISS = "provenance_miss"
    UNTREATED_INTERPRETER_INPUT = "untreated_interpreter_input"
    UNSAFE_INSTALL_SOURCE = "unsafe_install_source"
    UNSAFE_INSTALL_FLAGS = "unsafe_install_flags"


class ResolvedTarget(BaseModel):
    """A target as resolved by ``classify``. ``ref`` is the frozen identity."""

    model_config = ConfigDict(frozen=True)

    raw: str
    path: Path | None
    resolution: Resolution
    ref: ArtifactRef | None

    @model_validator(mode="after")
    def _resolution_matches_fields(self) -> ResolvedTarget:
        if self.resolution is Resolution.PATH and (self.path is None or self.ref is None):
            raise ValueError("a resolved target must carry both path and ref")
        if self.resolution is Resolution.UNRESOLVED and self.path is not None:
            raise ValueError("an unresolved target cannot carry a path")
        return self


class ArtifactSource(BaseModel):
    """One package artifact source. ``kind`` is the C1 derivation input."""

    model_config = ConfigDict(frozen=True)

    raw: str
    kind: SourceKind
    shape: SourceShape = SourceShape.UNKNOWN
    target: ResolvedTarget | None = None


class Action(BaseModel):
    """A classified action. ``kind`` is ``ActionKind | str`` so unknown is representable."""

    model_config = ConfigDict(frozen=True)

    kind: ActionKind | str
    command: str
    members: tuple[Action, ...] = ()
    targets: tuple[ResolvedTarget, ...] = ()
    interpreter_input: tuple[ResolvedTarget, ...] = ()
    # S-4: every non-flag argument that names an existing path, regardless of the
    # head. The interpreter allow-table only probed operands for declared
    # interpreters, so an unlisted interpreter's script operand was invisible.
    named_paths: tuple[ResolvedTarget, ...] = ()
    # The effective head and whether it is an explicitly allow-listed interpreter.
    # A tainted named path is denied unless this is true (deny-by-default).
    head: str = ""
    interpreter_allowlisted: bool = False
    # S-4: this member moves content out of the sandbox (``curl -T``, ``scp``,
    # ``nc``, ``tee``). The exfiltration surface is denied even though it does
    # not execute the tainted path.
    exfiltrates: bool = False
    artifact_sources: tuple[ArtifactSource, ...] = ()
    index_tokens: tuple[str, ...] = ()
    cwd: Path | None = None
    references_quarantine: bool = False
    executes_quarantine: bool = False
    scripts_disabled: bool = False
    operator_approved: bool = False
    content_digest: str | None = None

    @field_validator("kind", mode="before")
    @classmethod
    def _normalize_kind(cls, value: object) -> object:
        """Map a declared kind string to its member; unknown strings stay ``str`` (R7)."""
        if isinstance(value, str):
            try:
                return ActionKind(value)
            except ValueError:
                return value
        return value


class ActionDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    verdict: Literal["ALLOW", "DENY"]
    reason: ReasonCode
    tier: AuthzTier
    degraded: bool = False


class PolicyRule(BaseModel):
    """One row of the normative rule table, exported as data."""

    model_config = ConfigDict(frozen=True)

    rule: str
    verdict: Literal["ALLOW", "DENY"]
    reason: ReasonCode


POLICY_RULES: tuple[PolicyRule, ...] = (
    PolicyRule(rule="R1", verdict="DENY", reason=ReasonCode.QUARANTINE_REFERENCE),
    PolicyRule(rule="R2", verdict="DENY", reason=ReasonCode.TAINTED_EXECUTABLE),
    PolicyRule(rule="R2'", verdict="DENY", reason=ReasonCode.UNLISTED_INTERPRETER),
    PolicyRule(rule="R3", verdict="DENY", reason=ReasonCode.PROVENANCE_MISS),
    PolicyRule(rule="R3.8", verdict="DENY", reason=ReasonCode.UNTREATED_INTERPRETER_INPUT),
    PolicyRule(rule="R3.5", verdict="DENY", reason=ReasonCode.UNRESOLVED_QUARANTINE_REF),
    PolicyRule(rule="R4", verdict="DENY", reason=ReasonCode.TAINTED_CHMOD),
    PolicyRule(rule="R4'", verdict="DENY", reason=ReasonCode.PROVENANCE_MISS),
    PolicyRule(rule="R5", verdict="DENY", reason=ReasonCode.TAINTED_PACKAGE_SOURCE),
    PolicyRule(rule="R5'", verdict="DENY", reason=ReasonCode.PROVENANCE_MISS),
    PolicyRule(rule="R5\u2033", verdict="DENY", reason=ReasonCode.UNSAFE_INSTALL_SOURCE),
    PolicyRule(rule="R5\u2033\u2033", verdict="DENY", reason=ReasonCode.UNSAFE_INSTALL_FLAGS),
    PolicyRule(rule="R6", verdict="DENY", reason=ReasonCode.TAINTED_HOST_WRITE),
    PolicyRule(rule="R6'", verdict="DENY", reason=ReasonCode.PROVENANCE_MISS),
    PolicyRule(rule="R7", verdict="DENY", reason=ReasonCode.UNKNOWN_ACTION_KIND),
    PolicyRule(rule="R8", verdict="ALLOW", reason=ReasonCode.ALLOWED),
    PolicyRule(rule="R9", verdict="ALLOW", reason=ReasonCode.ALLOWED),
)

_EXEC_KINDS: frozenset[str] = frozenset({ActionKind.EXECUTE, ActionKind.PACKAGE_INSTALL})
_QUARANTINE_EXEC_KINDS: frozenset[str] = frozenset(
    {ActionKind.EXECUTE, ActionKind.CHMOD_EXEC, ActionKind.PACKAGE_INSTALL}
)
_UNRESOLVED_QUARANTINE_KINDS: frozenset[str] = frozenset(
    {ActionKind.EXECUTE, ActionKind.CHMOD_EXEC}
)


def tier_for(kind: ActionKind | str) -> AuthzTier:
    """EXECUTE and PACKAGE_INSTALL are high impact; everything else standard."""
    return AuthzTier.HIGH_IMPACT if kind in _EXEC_KINDS else AuthzTier.STANDARD


def _deny(reason: ReasonCode, kind: ActionKind | str, *, degraded: bool = False) -> ActionDecision:
    return ActionDecision(verdict="DENY", reason=reason, tier=tier_for(kind), degraded=degraded)


def _allow_all(
    kind: ActionKind | str,
) -> ActionDecision:
    return ActionDecision(verdict="ALLOW", reason=ReasonCode.ALLOWED, tier=tier_for(kind))


def _ref_state(ledger: ProvenanceLedger, target: ResolvedTarget) -> object:
    """Pure lookup by the frozen ref. A missing ref is a classification defect."""
    if target.ref is None:
        return LedgerMiss.MISS
    return ledger.lookup_ref(target.ref)


def _is_tainted(state: object) -> bool:
    if state is LedgerMiss.MISS or not hasattr(state, "is_tainted"):
        return False
    return bool(state.is_tainted())


def _is_miss(state: object) -> bool:
    return state is LedgerMiss.MISS


def _source_target_tainted(ledger: ProvenanceLedger, source: ArtifactSource) -> bool:
    if source.target is None:
        return False
    return _is_tainted(_ref_state(ledger, source.target))


def _local_source_miss(ledger: ProvenanceLedger, source: ArtifactSource) -> bool:
    if source.kind is not SourceKind.LOCAL:
        return False
    if source.target is None:
        return True
    return _is_miss(_ref_state(ledger, source.target))


def _install_source_unsafe(action: Action) -> bool:
    if action.operator_approved:
        return False
    for source in action.artifact_sources:
        if source.kind is SourceKind.OTHER_URL:
            return True
        if source.kind is SourceKind.OFFICIAL_INDEX and source.shape is SourceShape.SOURCE_DIST:
            return True
    return False


def _install_flags_unsafe(action: Action) -> bool:
    if action.operator_approved or action.scripts_disabled:
        return False
    return any(source.kind is SourceKind.OFFICIAL_INDEX for source in action.artifact_sources)


def _exec_target_tainted(ledger: ProvenanceLedger, action: Action) -> bool:
    return any(_is_tainted(_ref_state(ledger, t)) for t in action.targets)


def _head_name(head: str) -> str:
    """The command word of a head spelling (pure: no filesystem access)."""
    return head.rsplit("/", 1)[-1]


def _named_path_tainted_unlisted(ledger: ProvenanceLedger, action: Action) -> bool:
    """S-4: a tainted path named by a command that is not a reviewed reader.

    The interpreter allow-table only probes operands for declared interpreters, so
    an unlisted interpreter (``tclsh``, ``deno``, ``Rscript``) could execute a
    tainted script the gate never saw. The deny-by-default rule closes that: a
    command that names a tainted path is denied unless its head is an explicitly
    allow-listed interpreter (whose targets the existing R2/R3 rules already
    decide). A merely unrecorded path is not denied here — only taint is — so a
    legitimate read of an unrecorded file keeps its existing posture.

    The deny is scoped to the commands that can move the content (S-4's reviewed
    readers list): the reviewed readers (``cat``, ``grep``, ``less``, ``head``,
    ``tail``) may read the target's own source, and the pass-through commands
    (``mkdir``, ``touch``, ``chmod``) never read it. The exfiltration surface
    (``tee``, ``scp``, ``nc``, ``curl -T``) stays denied, as does every command
    the tables do not name (deny-by-default).
    """
    if action.interpreter_allowlisted:
        return False
    if not any(_is_tainted(_ref_state(ledger, t)) for t in action.named_paths):
        return False
    head = _head_name(action.head)
    if head in TAINT_READERS or head in TAINT_PASSTHROUGH:
        return False
    # A plain fetch is not exfiltration; only the upload form moves bytes.
    return not (head == "curl" and not action.exfiltrates)


def _exec_target_miss(ledger: ProvenanceLedger, action: Action) -> bool:
    return any(
        t.resolution is Resolution.PATH and _is_miss(_ref_state(ledger, t)) for t in action.targets
    )


def _interpreter_input_untreated(ledger: ProvenanceLedger, action: Action) -> bool:
    if action.operator_approved:
        return False
    for source in action.interpreter_input:
        if source.resolution is Resolution.UNRESOLVED:
            return True
        state = _ref_state(ledger, source)
        if _is_miss(state) or _is_tainted(state):
            return True
    return False


def _has_unresolved_exec_target(action: Action) -> bool:
    return any(t.resolution is Resolution.UNRESOLVED for t in action.targets)


def _write_content_tainted(ledger: ProvenanceLedger, action: Action) -> bool:
    if action.content_digest is None:
        return False
    return _is_tainted(ledger.content_lookup_digest(action.content_digest))


def _write_content_miss(ledger: ProvenanceLedger, action: Action) -> bool:
    if action.content_digest is None:
        return True
    return _is_miss(ledger.content_lookup_digest(action.content_digest))


def _decide_member(  # noqa: PLR0911, PLR0912 - the fixed R1-R9 rule table is the contract
    action: Action, ledger: ProvenanceLedger
) -> ActionDecision:
    kind = action.kind
    if kind not in {k.value for k in ActionKind}:
        return _deny(ReasonCode.UNKNOWN_ACTION_KIND, kind)
    # Defense in depth: the model validator normalizes at construction, but a
    # ``model_construct`` bypasses it; the ``is`` checks below must never see a str.
    kind = ActionKind(kind)

    if action.executes_quarantine and kind in _QUARANTINE_EXEC_KINDS:
        return _deny(ReasonCode.QUARANTINE_REFERENCE, kind)

    if kind is ActionKind.EXECUTE:
        if _exec_target_tainted(ledger, action):
            return _deny(ReasonCode.TAINTED_EXECUTABLE, kind)
        if _named_path_tainted_unlisted(ledger, action):
            return _deny(ReasonCode.UNLISTED_INTERPRETER, kind)
        if _exec_target_miss(ledger, action):
            return _deny(ReasonCode.PROVENANCE_MISS, kind)
        if _interpreter_input_untreated(ledger, action):
            return _deny(ReasonCode.UNTREATED_INTERPRETER_INPUT, kind)

    if (
        action.references_quarantine
        and kind in _UNRESOLVED_QUARANTINE_KINDS
        and _has_unresolved_exec_target(action)
    ):
        return _deny(ReasonCode.UNRESOLVED_QUARANTINE_REF, kind)

    if kind is ActionKind.CHMOD_EXEC:
        if _exec_target_tainted(ledger, action):
            return _deny(ReasonCode.TAINTED_CHMOD, kind)
        if _exec_target_miss(ledger, action):
            return _deny(ReasonCode.PROVENANCE_MISS, kind)

    if kind is ActionKind.PACKAGE_INSTALL:
        if any(_source_target_tainted(ledger, s) for s in action.artifact_sources):
            return _deny(ReasonCode.TAINTED_PACKAGE_SOURCE, kind)
        if any(_local_source_miss(ledger, s) for s in action.artifact_sources):
            return _deny(ReasonCode.PROVENANCE_MISS, kind)
        if _install_source_unsafe(action):
            return _deny(ReasonCode.UNSAFE_INSTALL_SOURCE, kind)
        if _install_flags_unsafe(action):
            return _deny(ReasonCode.UNSAFE_INSTALL_FLAGS, kind)

    if kind is ActionKind.WRITE_HOST_MOUNT:
        if _write_content_tainted(ledger, action):
            return _deny(ReasonCode.TAINTED_HOST_WRITE, kind)
        if _write_content_miss(ledger, action):
            return _deny(ReasonCode.PROVENANCE_MISS, kind)

    degraded = (
        kind is ActionKind.EXECUTE
        and not action.references_quarantine
        and (
            _has_unresolved_exec_target(action)
            or any(s.resolution is Resolution.UNRESOLVED for s in action.interpreter_input)
        )
    )
    if degraded:
        return ActionDecision(
            verdict="ALLOW",
            reason=ReasonCode.ALLOWED,
            tier=tier_for(kind),
            degraded=True,
        )

    return _allow_all(kind)


def decide_action(action: Action, provenance: ProvenanceLedger) -> ActionDecision:
    """Decide one action. Deny-dominant over the parent and its members.

    The parent's own targets/interpreter_input are always decided, even when a
    compound carries members; members are decided by this same composite rule
    at every depth (pre-order, source order), and the first denying node wins.
    """
    decision = _decide_member(action, provenance)
    if decision.verdict == "DENY":
        return decision
    for member in action.members:
        # Same composite rule at every depth: a member that is itself a compound
        # (subshell / substitution body) has its own members decided too.
        member_decision = decide_action(member, provenance)
        if member_decision.verdict == "DENY":
            return member_decision
    return decision
