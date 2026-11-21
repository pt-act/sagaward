"""S-5 — the classifier reads the host process's filesystem, not the container's.

``classify`` resolves paths with ``Path.resolve``/``Path.stat`` in the host
process. The container's path spellings are therefore read as the *host* sees the
same spelling: a path that exists only in the container is a frozen identity by
spelling with **no host inode** (the gate then denies it as a provenance miss),
and a path that exists on the host resolves to the host's inode. This test runs
against a live container to show the divergence rather than assert it in prose.

Integration-class: skipped when no container runtime (or no base image) is
available.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from sagaward.core.provenance.classify import classify
from sagaward.core.provenance.gate import Resolution


_IMAGE = "kalilinux/kali-rolling:latest"
_CONTAINER_ONLY = "/apf-container-only"


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return (
            subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


def _image_available(image: str) -> bool:
    try:
        return (
            subprocess.run(
                ["docker", "image", "inspect", image], capture_output=True, timeout=10
            ).returncode
            == 0
        )
    except (OSError, subprocess.SubprocessError):
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _docker_available(), reason="no container runtime"),
    pytest.mark.skipif(not _image_available(_IMAGE), reason=f"image {_IMAGE} not present"),
]


@pytest.fixture(scope="module")
def container() -> str:
    """A live container with a file that exists only inside it."""
    result = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            _IMAGE,
            "sh",
            "-c",
            f"echo container-only > {_CONTAINER_ONLY} && sleep 300",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    container_id = result.stdout.strip()
    try:
        yield container_id
    finally:
        subprocess.run(["docker", "stop", container_id], capture_output=True, timeout=30)


def test_a_container_only_path_has_no_host_inode(container: str) -> None:
    """The path exists in the container but not on the host: the host probe finds no inode."""
    inside = subprocess.run(
        ["docker", "exec", container, "test", "-f", _CONTAINER_ONLY],
        capture_output=True,
    )
    assert inside.returncode == 0, "the fixture file must exist in the container"

    action = classify(f"sh {_CONTAINER_ONLY}", None)
    targets = [t for t in action.targets if t.raw == _CONTAINER_ONLY]
    assert targets, "the interpreter operand must be a target"
    # The classifier reads the host's filesystem: the path is a frozen identity by
    # spelling, but the host has no inode for it (the container's file is invisible).
    assert targets[0].resolution is Resolution.PATH
    assert targets[0].ref is not None and targets[0].ref.inode_key is None


def test_a_host_path_resolves_to_the_host_inode(container: str) -> None:
    """A path that exists on the host resolves to the host's inode, not the container's."""
    action = classify("sh /etc/passwd", None)
    targets = [t for t in action.targets if t.raw == "/etc/passwd"]
    assert targets, "the interpreter operand must be a target"
    assert targets[0].resolution is Resolution.PATH
    assert targets[0].path == Path("/etc/passwd").resolve()
    assert targets[0].ref is not None and targets[0].ref.inode_key is not None
