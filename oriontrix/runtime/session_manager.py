"""Per-scan sandbox session lifecycle."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from agents.sandbox.entries import BaseEntry, LocalDir
from agents.sandbox.manifest import Environment, Manifest

from oriontrix.config import load_settings
from oriontrix.core.isolation import session_key as _session_key
from oriontrix.runtime.backends import get_backend
from oriontrix.runtime.caido_bootstrap import bootstrap_caido
from oriontrix.runtime.provenance_bringup import bring_up_provenance


logger = logging.getLogger(__name__)


# In-container Caido sidecar port (matches the image's caido-cli bind).
_CONTAINER_CAIDO_PORT = 48080


_SESSION_CACHE: dict[str, dict[str, Any]] = {}


async def create_or_reuse(
    scan_id: str,
    *,
    image: str,
    local_sources: list[dict[str, str]],
    agent_id: str | None = None,
    profile: str = "default",
) -> dict[str, Any]:
    """Return the existing session bundle for ``(scan_id, agent_id)`` or create it.

    Each ``local_sources`` entry mounts its host ``source_path`` at
    ``/workspace/<workspace_subdir>`` inside the container. ``profile`` selects
    the capability set (see ``oriontrix.core.isolation``); the quarantine volume is
    mounted noexec per agent.
    """
    key = _session_key(scan_id, agent_id)
    cached = _SESSION_CACHE.get(key)
    if cached is not None:
        logger.info("Reusing existing sandbox session for %s", key)
        return cached

    entries: dict[str | Path, BaseEntry] = {}
    for src in local_sources:
        ws_subdir = src.get("workspace_subdir") or ""
        host_path = src.get("source_path") or ""
        if not ws_subdir or not host_path:
            continue
        entries[ws_subdir] = LocalDir(src=Path(host_path).expanduser().resolve())

    # Caido runs as an in-container sidecar; HTTP(S) traffic from any
    # process started via ``session.exec`` (the SDK's Shell tool, etc.)
    # picks up these env vars automatically. ``NO_PROXY`` keeps the
    # agent-browser CDP daemon's localhost traffic from looping back
    # through Caido.
    container_caido_url = f"http://127.0.0.1:{_CONTAINER_CAIDO_PORT}"
    manifest = Manifest(
        entries=entries,
        environment=Environment(
            value={
                "PYTHONUNBUFFERED": "1",
                "HOST_GATEWAY": "host.docker.internal",
                "http_proxy": container_caido_url,
                "https_proxy": container_caido_url,
                "ALL_PROXY": container_caido_url,
                "NO_PROXY": "localhost,127.0.0.1",
            },
        ),
    )

    backend_name = load_settings().runtime.backend
    backend = get_backend(backend_name)

    logger.info(
        "Creating sandbox session for %s (backend=%s, image=%s, profile=%s)",
        key,
        backend_name,
        image,
        profile,
    )
    client, session = await backend(
        image=image,
        manifest=manifest,
        exposed_ports=(_CONTAINER_CAIDO_PORT,),
        profile=profile,
        scan_id=scan_id,
        agent_id=agent_id or "root",
    )

    caido_endpoint = await session.resolve_exposed_port(_CONTAINER_CAIDO_PORT)
    host_caido_url = f"http://{caido_endpoint.host}:{caido_endpoint.port}"
    logger.debug("Caido host endpoint resolved: %s", host_caido_url)

    # Host-side tools (identity replay via caido_api.get_client) resolve the
    # Caido endpoint through caido_url() -> os.environ["ORIONTRIX_CAIDO_URL"],
    # defaulting to the CONTAINER port 48080. The host maps 48080 to a DYNAMIC
    # port, so without this export replay_send_raw connects to 127.0.0.1:48080
    # and fails with "Connection refused" -> empty auth_matrix. Pin the env to
    # the resolved host endpoint so replay reaches the live Caido sidecar.
    os.environ["ORIONTRIX_CAIDO_URL"] = host_caido_url

    caido_client = await bootstrap_caido(
        session,
        host_url=host_caido_url,
        container_url=container_caido_url,
    )

    # Per-sandbox-epoch provenance. Built after the container is up and before
    # any agent action can run, so the image inventory describes what the
    # sandbox actually shipped. Dies with the container; never shared across
    # scans (session_manager caches per scan/agent key).
    provenance = await bring_up_provenance(session)

    bundle = {
        "client": client,
        "session": session,
        "provenance": provenance,
        "caido_client": caido_client,
    }
    _SESSION_CACHE[key] = bundle
    logger.info("Sandbox session for %s ready and cached", key)
    return bundle


async def cleanup(scan_id: str, agent_id: str | None = None) -> None:
    """Tear down ``scan_id``'s container and drop its cache entry.

    Best-effort: any error during ``client.delete`` is logged and
    swallowed. We never want a cleanup failure to prevent the next
    scan from starting; the worst case is a stranded container that
    Docker's normal reaping will catch on next ``docker prune``.
    """
    key = _session_key(scan_id, agent_id)
    bundle = _SESSION_CACHE.pop(key, None)
    if bundle is None:
        # Teardown of one agent must not strand its siblings: clean the whole
        # scan only when the caller names no agent.
        if agent_id is None:
            for sibling in [k for k in _SESSION_CACHE if k.startswith(f"{scan_id}:")]:
                _SESSION_CACHE.pop(sibling, None)
        logger.debug("cleanup(%s): no cached session", key)
        return

    caido_client = bundle.get("caido_client")
    if caido_client is not None:
        try:
            await caido_client.aclose()
        except Exception:  # noqa: BLE001
            logger.debug("cleanup(%s): caido_client.aclose() raised", scan_id, exc_info=True)

    try:
        await bundle["client"].delete(bundle["session"])
        logger.info("Cleaned up sandbox session for scan %s", scan_id)
    except Exception:
        logger.exception(
            "cleanup(%s): client.delete raised; container may need manual reaping",
            scan_id,
        )
