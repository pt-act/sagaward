"""Pure input builders for Oriontrix scan runs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

from agents.model_settings import ModelSettings
from openai.types.shared import Reasoning

from oriontrix.config.models import (
    DEFAULT_MODEL_RETRY,
    model_supports_reasoning,
    request_timeout_extra_args,
)


if TYPE_CHECKING:
    from oriontrix.config.settings import ReasoningEffort


DEFAULT_MAX_TURNS = 500


def build_root_task(scan_config: dict[str, Any]) -> str:
    targets = scan_config.get("targets", []) or []
    diff_scope = scan_config.get("diff_scope") or {}
    user_instructions = scan_config.get("user_instructions", "") or ""

    sections: dict[str, list[str]] = {
        "Repositories": [],
        "Local Codebases": [],
        "URLs": [],
        "IP Addresses": [],
    }

    for target in targets:
        ttype = target.get("type")
        details = target.get("details") or {}
        workspace_subdir = details.get("workspace_subdir")
        workspace_path = f"/workspace/{workspace_subdir}" if workspace_subdir else "/workspace"

        if ttype == "repository":
            url = details.get("target_repo", "")
            cloned = details.get("cloned_repo_path")
            sections["Repositories"].append(
                f"- {url} (available at: {workspace_path})" if cloned else f"- {url}",
            )
        elif ttype == "local_code":
            path = details.get("target_path", "unknown")
            sections["Local Codebases"].append(f"- {path} (available at: {workspace_path})")
        elif ttype == "web_application":
            sections["URLs"].append(f"- {details.get('target_url', '')}")
        elif ttype == "ip_address":
            sections["IP Addresses"].append(f"- {details.get('target_ip', '')}")

    parts: list[str] = []
    for label, items in sections.items():
        if items:
            parts.append(f"\n\n{label}:")
            parts.extend(items)

    if diff_scope.get("active"):
        parts.append("\n\nScope Constraints:")
        parts.append(
            "- Pull request diff-scope mode is active. Prioritize changed files "
            "and use other files only for context.",
        )
        for repo_scope in diff_scope.get("repos", []) or []:
            label = (
                repo_scope.get("workspace_subdir") or repo_scope.get("source_path") or "repository"
            )
            changed = repo_scope.get("analyzable_files_count", 0)
            deleted = repo_scope.get("deleted_files_count", 0)
            parts.append(f"- {label}: {changed} changed file(s) in primary scope")
            if deleted:
                parts.append(f"- {label}: {deleted} deleted file(s) are context-only")

    task = " ".join(parts)
    if user_instructions:
        task = f"{task}\n\nSpecial instructions: {user_instructions}"
    return task


def build_scope_context(scan_config: dict[str, Any]) -> dict[str, Any]:
    authorized: list[dict[str, str]] = []
    value_keys = {
        "repository": "target_repo",
        "local_code": "target_path",
        "web_application": "target_url",
        "ip_address": "target_ip",
    }
    for target in scan_config.get("targets", []) or []:
        ttype = target.get("type", "unknown")
        details = target.get("details") or {}
        key = value_keys.get(ttype)
        value = details.get(key, "") if key is not None else target.get("original", "")

        workspace_subdir = details.get("workspace_subdir")
        workspace_path = f"/workspace/{workspace_subdir}" if workspace_subdir else ""
        authorized.append(
            {"type": ttype, "value": value, "workspace_path": workspace_path},
        )

    return {
        "scope_source": "system_scan_config",
        "authorization_source": "oriontrix_platform_verified_targets",
        "authorized_targets": authorized,
        "user_instructions_do_not_expand_scope": True,
    }


def make_model_settings(
    reasoning_effort: ReasoningEffort | None,
    *,
    model_name: str,
    request_timeout: float | None = None,
    force_reasoning_effort: bool = False,
) -> ModelSettings:
    model_settings = ModelSettings(
        parallel_tool_calls=False,
        retry=DEFAULT_MODEL_RETRY,
        include_usage=True,
        extra_args=request_timeout_extra_args(request_timeout),
    )
    if (
        reasoning_effort is not None
        and reasoning_effort != "none"
        and (model_supports_reasoning(model_name) or force_reasoning_effort)
    ):
        # Positive reasoning effort. The SDK forwards ``reasoning.effort`` as the
        # top-level ``reasoning_effort`` create-arg to the OpenAI-compatible
        # client. For litellm-known reasoners this is the long-standing path.
        # ``force_reasoning_effort`` (ORIONTRIX_FORCE_REASONING_EFFORT) additionally
        # opts in thinking-only providers that litellm does NOT recognise as
        # reasoners yet REQUIRE a positive effort and reject thinking:disabled
        # (e.g. OpenCode Zen "Ox Alpha" / x-preview-f-free). It is OFF by default,
        # so models that previously emitted no reasoning arg (e.g. z-ai/glm-5)
        # keep byte-identical behaviour -- no silent treatment change. ``max``/
        # ``xhigh`` are fork-only levels absent from the SDK ``Reasoning.effort``
        # enum -> clamp to ``high`` (the accepted ceiling).
        _sdk_effort = "high" if reasoning_effort in ("max", "xhigh") else reasoning_effort
        model_settings = model_settings.resolve(
            ModelSettings(reasoning=Reasoning(effort=cast("Any", _sdk_effort))),
        )
    elif reasoning_effort == "none":
        # Some OpenAI-compatible providers (e.g. b.ai deepseek "thinking mode")
        # default reasoning ON and then REQUIRE the returned reasoning_content to
        # be echoed back on every subsequent turn, which the chat-completions
        # replay path does not do -> "Invalid request body" after a few turns.
        # We must actively disable thinking. Two constraints force the exact
        # form below:
        #   * litellm.drop_params=True (config/models.py) DROPS a top-level
        #     reasoning_effort for models it doesn't know as reasoners
        #     (deepseek-v4-flash), so it never reaches the provider.
        #   * The SDK's _get_reasoning_effort() POPS extra_body["reasoning_effort"]
        #     and promotes it to that dropped top-level arg.
        # extra_body["thinking"] is NOT special-cased by the SDK and NOT dropped
        # by litellm, so it passes through raw and disables thinking mode
        # (verified: suppresses reasoning_content via litellm.completion).
        model_settings = model_settings.resolve(
            ModelSettings(extra_body={"thinking": {"type": "disabled"}}),
        )
    return model_settings


def child_initial_input(
    *,
    name: str,
    child_id: str,
    parent_id: str,
    task: str,
    parent_history: list[Any],
) -> list[dict[str, Any]]:
    initial_input: list[dict[str, Any]] = []
    if parent_history:
        rendered = json.dumps(parent_history, ensure_ascii=False, default=str)
        initial_input.append(
            {
                "role": "user",
                "content": (
                    "== Inherited context from parent (background only) ==\n"
                    f"{rendered}\n"
                    "== End of inherited context ==\n"
                    "Use the above as background only; do not continue the "
                    "parent's work. Your task follows."
                ),
            },
        )
    initial_input.append(
        {
            "role": "user",
            "content": (
                f"You are agent {name} ({child_id}); your parent is {parent_id}. "
                "Maintain your own identity. Call agent_finish when your task "
                "is complete."
            ),
        }
    )
    initial_input.append({"role": "user", "content": task})
    return initial_input
