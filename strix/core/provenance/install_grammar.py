"""The declared install-trigger grammar (pure: stdlib only).

One grammar for two consumers: the runtime's install reconciler
(``strix.runtime.provenance_install``) and the gate's classifier
(``strix.core.provenance.classify``). The spec's kind-grammar contract (C3)
requires that a member which fires the provenance walk classifies as
``PACKAGE_INSTALL``; keeping one table in core makes that true by construction
and keeps classify inside the package purity boundary.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path


# Declared (program, verb) pair -> trigger key. The trigger key names its roots
# in core's TRIGGER_PREFIXES; the pair is only the parseable spelling. A manager
# that installs outside this table is not reconciled; its files stay misses until
# the table is extended (a spec revision, not a code commit).
_INSTALL_PAIRS: dict[tuple[str, str], str] = {
    ("uv", "pip"): "uv-pip",
    ("poetry", "add"): "poetry-add",
    ("npm", "install"): "npm-install",
    ("npm", "i"): "npm-install",
    ("npm", "ci"): "npm-ci",
    ("yarn", "add"): "yarn-add",
    ("yarn", "install"): "yarn-add",
    ("pnpm", "add"): "pnpm-add",
    ("pnpm", "install"): "pnpm-add",
    ("gem", "install"): "gem-install",
    ("cargo", "install"): "cargo-install",
    ("go", "install"): "go-install",
    ("apt-get", "install"): "apt-get-install",
    ("apt", "install"): "apt-install",
    ("dpkg", "-i"): "dpkg-install",
    ("conda", "install"): "conda-install",
    ("micromamba", "install"): "micromamba-install",
    ("apk", "add"): "apk-add",
    ("brew", "install"): "brew-install",
}

_PIP_NAME = re.compile(r"pip3?(?:\.\d+)?$")
_PYTHON_NAME = re.compile(r"(?:python|pypy)\d*(?:\.\d+)?$")


def _is_assignment(token: str) -> bool:
    name, sep, _value = token.partition("=")
    if not sep or not name or token.startswith("-"):
        return False
    return name.replace("_", "").isalnum()


def command_tokens(command: str) -> tuple[str, ...]:
    """Tokenise the command, dropping leading ``VAR=value`` assignments.

    A command that will not lex is not guessed at: no tokens means no trigger,
    which leaves installed files as misses rather than reconciling on a guess.
    """
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return ()
    start = 0
    while start < len(tokens) and _is_assignment(tokens[start]):
        start += 1
    return tuple(tokens[start:])


def _verb_index(tokens: tuple[str, ...]) -> int | None:
    """Index of the first token that is not an option.

    Options *before* the verb are skipped when they are pure flags (`-q`,
    `--quiet`) or carry their value inline (`--prefix=/opt/x`). An option whose
    value is a separate token (`npm --prefix /opt/app install`) makes that value
    look like a verb, so the shape misses the trigger — a miss (deny), named in
    the spec rather than guessed at.
    """
    for index, item in enumerate(tokens):
        if item == "--":
            continue
        if not item.startswith("-"):
            return index
    return None


def install_trigger(command: str) -> str | None:
    """The declared trigger key for this command, or None. A trigger, never a verdict."""
    tokens = command_tokens(command)
    if len(tokens) < 2:
        return None
    head = Path(tokens[0]).name
    rest = tokens[1:]
    if _PIP_NAME.match(head):
        verb = _verb_index(rest)
        return "pip" if verb is not None and rest[verb] == "install" else None
    if _PYTHON_NAME.match(head):
        if len(tokens) >= 4 and tokens[1] == "-m" and tokens[2] == "pip":
            return "pip" if "install" in tokens[3:] else None
        return None
    # The verb is normally the first non-option token, but option-verbs exist
    # (`dpkg -i`), so the literal second token is tried too.
    candidates: list[str] = []
    verb = _verb_index(rest)
    if verb is not None:
        candidates.append(rest[verb])
    candidates.append(rest[0])
    for candidate in candidates:
        trigger = _INSTALL_PAIRS.get((head, candidate))
        if trigger is not None:
            return trigger
    return None


def looks_like_install(command: str) -> bool:
    """True for the declared install-command shapes."""
    return install_trigger(command) is not None
