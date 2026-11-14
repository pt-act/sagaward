"""Attach the model-authored write hook to the sandbox filesystem toolset.

Kept free of SDK imports so the hook is provable offline: the toolset is
duck-typed (``vars()`` + ``on_invoke_tool``), exactly as the SDK hands it over.
The caller supplies the optional chat-completions converter so this module does
not need to know about it.
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sagaward.core.provenance.content import ABSENT, digest, engagement_envelope
from sagaward.core.provenance.model import ProvenanceEnvelope
from sagaward.core.provenance.paths import is_quarantine_path, resolve_or_none
from sagaward.core.provenance.writes import (
    WORKSPACE_ROOT,
    added_file_contents,
    model_authored_envelope,
    touched_paths,
)


if TYPE_CHECKING:
    from collections.abc import Iterable


logger = logging.getLogger(__name__)

APPLY_PATCH_TOOL_NAME = "apply_patch"

# Conservative failure vocabulary. A result we cannot read as success is treated as
# failure only when it says so; the authored-content check below is the real gate.
FAILURE_TOKENS = (
    "error",
    "failed",
    "failure",
    "rejected",
    "denied",
    "not allowed",
    "read-only",
    "no such file",
)


def patch_reported_failure(result: Any) -> bool:
    """True when the tool's own result says the patch did not land."""
    if not isinstance(result, str):
        return False
    folded = result.casefold()
    return any(token in folded for token in FAILURE_TOKENS)


EXPECTED_WRITE_TOOLS: frozenset[str] = frozenset({APPLY_PATCH_TOOL_NAME})


@lru_cache(maxsize=1)
def _warn_missing_ledger() -> None:
    logger.warning(
        "apply_patch ran without a provenance ledger in context; model-authored writes are "
        "unrecorded and will read as PROVENANCE_MISS (denied)",
    )


def ledger_from_ctx(ctx: Any) -> Any:
    """The per-sandbox provenance ledger, or None outside a sandbox run."""
    context = getattr(ctx, "context", None)
    if not isinstance(context, dict):
        return None
    return context.get("provenance")


def record_observed_writes(
    ledger: Any,
    observed: Iterable[tuple[Any, tuple[str | None, int]]],
    before: dict[Any, tuple[str | None, int]] | None,
    not_before_ns: int = 0,
    authored: dict[Any, str] | None = None,
) -> int:
    """Record writes the sandbox confirms happened; taint index matches.

    "Happened" means the file is newly present or its digest changed — existence
    alone is not a write. A failed patch over an existing file leaves the digest
    identical, so it blesses nothing and the path stays a miss. Quarantine paths
    are never recorded clean.

    The key that is observed must be the key that is recorded: if resolving the
    path now lands somewhere else, a link or traversal moved the filesystem
    between the two observations, and the digest describes a file this path did
    not name when it was observed. That is refused rather than canonicalized,
    because canonicalizing would bless the target's bytes at the target's key
    (round 12, R12-ATK).

    Resolution happens exactly once, here, and the store is bound to the value
    that was checked (``record_key``). A store that resolved again would be a
    second, unbound resolution: a link toggled between the check and the store
    would select the link's target as the key (round 13, R13-ATK).
    """
    if before is None:
        # Unknown baseline: we cannot tell a write from a pre-existing file, so
        # nothing is recorded. Misses are denied; a false clean is not.
        return 0
    recorded = 0
    for path, (content_digest, mtime_ns) in observed:
        key = _expected_key(path)
        if key is None:
            continue
        if not _confirms_write(
            path,
            content_digest,
            mtime_ns,
            before.get(path),
            authored,
            not_before_ns,
        ):
            continue
        envelope = model_authored_envelope(key)
        if isinstance(ledger.content_lookup_digest(content_digest), ProvenanceEnvelope):
            envelope = envelope.merged_with(engagement_envelope())
        ledger.record_key(key, envelope)
        recorded += 1
    return recorded


def _expected_key(path: Any) -> Path | None:
    """The key this observation is about, or ``None`` when it is not the path's own.

    Quarantine, an unresolvable path, and a resolution that leaves the expected
    key are all refusals: in those cases the observed digest does not describe the
    path that was requested (round 12 R12-ATK; round 13 R13-QALIAS).
    """
    if is_quarantine_path(path):
        return None
    resolved = resolve_or_none(path)
    if resolved is None:
        # A racing unlink/replace must refuse, not raise out of the tool.
        return None
    if Path(path).is_relative_to(WORKSPACE_ROOT):
        # Tolerate the workspace root itself being a mount/link; a link below
        # it still shows up as a resolved path that leaves the expected key.
        expected = WORKSPACE_ROOT.resolve() / Path(path).relative_to(WORKSPACE_ROOT)
    else:
        expected = Path(path)
    return expected if resolved == expected else None


def _confirms_write(
    path: Any,
    content_digest: str | None,
    mtime_ns: int,
    prior: tuple[str | None, int] | None,
    authored: dict[Any, str] | None,
    not_before_ns: int,
) -> bool:
    """True when this observation is a write this operation made."""
    if content_digest is None or content_digest == ABSENT:
        # Unreadable, or confirmed absent after the write: nothing landed.
        return False
    if prior is None or prior[0] is None:
        # No baseline, or one that existed but was unreadable: a digest now
        # does not prove this patch wrote it (round 13, R13-NONE).
        return False
    if prior[0] == content_digest:
        # Unchanged: the patch did not land.
        return False
    if authored is not None and path in authored and content_digest != digest(authored[path]):
        # Observed bytes are not what the patch declared: refuse.
        return False
    # The bytes must not predate this operation: a moved-aside file restored to
    # its old mtime is not a write (round-8 B2).
    return mtime_ns >= not_before_ns


def wrap_apply_patch_tool(tool: Any, verifier: Any = None) -> Any:
    """Record every path an ``apply_patch`` document writes as MODEL_AUTHORED.

    R3 denies ``EXECUTE`` on any path with no envelope, so without this the
    agent's own scripts are misses and the engine refuses to run them.
    Recording happens after the tool returns; the patch is never altered and the
    result is passed through untouched.
    """
    invoke_tool = tool.on_invoke_tool

    async def invoke(ctx: Any, raw_input: str) -> Any:
        ledger = ledger_from_ctx(ctx)
        if ledger is None:
            _warn_missing_ledger()
            return await invoke_tool(ctx, raw_input)
        paths = touched_paths(raw_input)
        if verifier is None:
            # No observation available: record nothing. The patch document states
            # intent, not outcome, and a failed patch over an existing file must
            # not be blessed. Paths stay misses, which is a DENY.
            logger.warning(
                "apply_patch ran without an observation verifier; nothing recorded "
                "(paths stay PROVENANCE_MISS)",
            )
            return await invoke_tool(ctx, raw_input)
        before = await verifier(ctx, paths)
        started_ns = time.time_ns()
        result = await invoke_tool(ctx, raw_input)
        if patch_reported_failure(result):
            # The tool says it failed. Whatever the filesystem now shows is not
            # this patch's doing (round-8 verdict B2, primary gate).
            return result
        after = await verifier(ctx, paths)
        if before is None or after is None:
            logger.warning(
                "apply_patch write could not be observed before/after; nothing recorded "
                "(paths stay PROVENANCE_MISS)",
            )
            return result
        authored = added_file_contents(raw_input)
        record_observed_writes(
            ledger,
            after.items(),
            before=before,
            not_before_ns=started_ns,
            authored=authored,
        )
        return result

    tool.on_invoke_tool = invoke
    return tool


def configure_filesystem_tools(
    toolset: Any,
    *,
    chat_completions: bool,
    chat_converter: Any = None,
    verifier: Any = None,
) -> None:
    """Attach the write hook, then hand the toolset to the chat-completions converter.

    Refuses at build time when the SDK's write tool is absent. A scan that
    proceeds with a dead hook fails its own anti-strangulation criteria and
    teaches operators to override denials; APF-1 AC-11 and the PM disposition
    (§2a) both require refusal here, not a warning.
    """
    detected = {name for name, tool in vars(toolset).items() if hasattr(tool, "on_invoke_tool")}
    missing = EXPECTED_WRITE_TOOLS - detected
    if missing:
        raise RuntimeError(
            "apf-provenance: sandbox write hook cannot attach — expected tool(s) "
            f"{sorted(EXPECTED_WRITE_TOOLS)} not found in the filesystem toolset; "
            f"detected: {sorted(detected)}. The SDK may have renamed its write tool. "
            "Model-authored writes would be unrecorded, every agent script would read as "
            "PROVENANCE_MISS, and the action gate would deny it (apf-provenance AC-11).",
        )
    for name in detected & EXPECTED_WRITE_TOOLS:
        setattr(toolset, name, wrap_apply_patch_tool(getattr(toolset, name), verifier))
    if chat_completions and chat_converter is not None:
        chat_converter(toolset)
