"""Command -> :class:`Action` classification (apf-action-gate G2a + G2b).

This is the gate's single I/O point. ``decide_action`` is pure and decides over a
frozen snapshot; everything the decision needs from the filesystem — a target's
existence and mode, its frozen :class:`ArtifactRef`, the quarantine resolution,
a ``$PATH`` probe — is read here, once, and frozen into the :class:`Action`.

The command is parsed by a real shell parser (``bashlex``) behind a small
:class:`Parser` protocol so a pinned alternative can plug in. Three postures
govern every branch:

* **Member-wise (1c-1).** A compound (``;``, ``&&``, ``||``, ``|``, a subshell,
  a substitution body, an interpreter ``-c`` body) is decomposed into member
  :class:`Action` nodes. Each member derives exactly one kind; the gate decides
  them recursively and the composite is deny-dominant.
* **Fail-closed, never a guess (2.3).** A parse failure or an unsupported
  construct yields ``UNRESOLVED`` targets and ``EXECUTE`` — the refusing shape,
  never a silent ``ALLOW``.
* **No second grammar (2.5).** ``PACKAGE_INSTALL`` is decided by the *same*
  declared install table the provenance trigger uses
  (:func:`sagaward.runtime.provenance_install.install_trigger`), applied to each
  member's argv. A member that fires the walk classifies as an install.

G2b adds the classifier's second structural half: **index-selection evidence**
(1c-2 — flags, env assignments and config files, where any non-official value
re-points every source of that install), the **assignment contract** (R8/N8 — the
value of a ``VAR=value`` assignment and the embedded path of a declared
interpreter-env flag are resolved at the same single I/O point), **module
execution** (R12 — ``python* -m <module>`` resolves against the recorded
site-packages roots, never against ``cwd``), and the **busybox applet table**
(1c-7 — applets are positional, so the shipped interpreter-class applets are
declared data merged into ``INTERPRETER_CLASS``).
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import urlsplit

import bashlex

from sagaward.core.provenance.artifact import ArtifactRef
from sagaward.core.provenance.gate import (
    OFFICIAL_INDEX_HOSTS,
    Action,
    ActionKind,
    ArtifactSource,
    Resolution,
    ResolvedTarget,
    SourceKind,
    SourceShape,
)
from sagaward.core.provenance.install_grammar import install_trigger
from sagaward.core.provenance.paths import QUARANTINE_DIR, is_quarantine_path
from sagaward.core.provenance.seed import is_agent_writable


if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


# ---------------------------------------------------------------------------
# Closed data tables (N10). Membership is asserted in tests; an addition requires
# a spec revision because it widens what the gate can see as exec-bearing.
# ---------------------------------------------------------------------------

# Shell builtins: they have no artifact identity on disk, so a bare builtin word
# is never a target and never a miss (R9). An operand is still a path only when
# the builtin reads it (`cd /workspace` resolves the directory, not executes it).
SHELL_BUILTINS: frozenset[str] = frozenset(
    {
        "cd",
        "echo",
        "printf",
        "export",
        "unset",
        "set",
        "alias",
        "unalias",
        "source",
        ".",
        "true",
        "false",
        "exit",
        "return",
        "read",
        "eval",
        "exec",
        "command",
        "builtin",
        "test",
        "[",
        "pwd",
        "umask",
        "wait",
        "shift",
        "type",
        "hash",
        "trap",
        "ulimit",
        "jobs",
        "kill",
        "bg",
        "fg",
    }
)

# Declared interpreter / wrapper binaries: an argument to one of these is a
# target candidate (A5(b)). Versioned forms are normalized by ``_is_interpreter``.
INTERPRETER_CLASS: frozenset[str] = frozenset(
    {
        "sh",
        "bash",
        "dash",
        "zsh",
        "ash",
        "python",
        "perl",
        "ruby",
        "node",
        "awk",
        "php",
        "lua",
        "env",
        "timeout",
        "nice",
        "nohup",
        "setsid",
        "flock",
        "stdbuf",
        "ionice",
        "strace",
        "watch",
        "xargs",
        "busybox",
    }
)
EXEC_BEARING_WRAPPERS: frozenset[str] = frozenset({"find"})

# 1c-7 — multi-call binaries. ``busybox`` selects an applet positionally, so no
# ELF/shebang derivation covers it. The table is the shipped set (declared data,
# not a discovery); the interpreter-class applets merge into
# ``INTERPRETER_CLASS`` at bring-up, and everything the image does not ship is
# the named remainder with AC-33 as its exit criterion.
BUSYBOX_APPLETS: frozenset[str] = frozenset(
    {
        "ash",
        "sh",
        "awk",
        "sed",
        "grep",
        "egrep",
        "fgrep",
        "find",
        "xargs",
        "env",
        "printenv",
        "timeout",
        "nohup",
        "setsid",
        "flock",
        "stdbuf",
        "ionice",
        "nice",
        "tee",
        "dd",
        "cp",
        "mv",
        "rm",
        "chmod",
        "chown",
        "install",
        "tar",
        "gzip",
        "gunzip",
        "bzip2",
        "xz",
        "unzip",
        "wget",
        "nc",
        "netcat",
        "ping",
        "base64",
        "xxd",
        "od",
        "md5sum",
        "sha256sum",
        "head",
        "tail",
        "cat",
        "cut",
        "tr",
        "wc",
        "sort",
        "uniq",
        "printf",
        "echo",
        "test",
        "true",
        "false",
        "ls",
        "mkdir",
        "rmdir",
        "ln",
        "touch",
        "stat",
        "readlink",
        "realpath",
        "mktemp",
        "sleep",
        "date",
        "id",
        "whoami",
        "uname",
    }
)
# The applets that execute code or forward an operand: the only members that
# change target extraction. The rest of the table is inventory, not policy.
BUSYBOX_INTERPRETER_APPLETS: frozenset[str] = frozenset(
    {
        "ash",
        "sh",
        "awk",
        "env",
        "timeout",
        "nohup",
        "setsid",
        "flock",
        "stdbuf",
        "ionice",
        "nice",
        "xargs",
    }
)
# ``find`` is exec-bearing through its ``-exec`` family, declared separately.
BUSYBOX_EXEC_WRAPPER_APPLETS: frozenset[str] = frozenset({"find"})


def merged_interpreter_class() -> frozenset[str]:
    """``INTERPRETER_CLASS`` with the busybox applet table merged (1c-7 bring-up).

    The merge is what makes ``busybox sh`` an interpreter invocation even though
    ``sh`` never appears as an argv[0]: the applet is selected positionally.
    """
    return INTERPRETER_CLASS | BUSYBOX_INTERPRETER_APPLETS | BUSYBOX_EXEC_WRAPPER_APPLETS


# Builtins that execute an operand rather than reading it as data (1c-1). Their
# operand is probed like a wrapper's (``exec``/``command``/``builtin``) or an
# interpreter's (``source``/``.``); ``eval``/``trap`` string bodies descend (C8).
_PROBE_OPERAND_BUILTINS: frozenset[str] = frozenset({"exec", "command", "builtin"})
_SOURCE_BUILTINS: frozenset[str] = frozenset({"source", "."})
_STRING_BODY_BUILTINS: frozenset[str] = frozenset({"eval", "trap"})
_PACKAGE_TOOL_RUNNERS: frozenset[str] = frozenset({"uvx"})
_LOADER_PREFIXES: tuple[str, ...] = ("ld-linux", "ld.so", "ld-musl")

# Build/exec verbs (1c-6): they fetch, build, or run package code inside the
# action, so the member is PACKAGE_INSTALL. The declared install table stays the
# single grammar (see ``_install_member``); this is only the build/exec addendum.
_PIP_BUILD_VERBS: frozenset[str] = frozenset({"wheel"})
_PACKAGE_EXEC_VERBS: dict[str, frozenset[str]] = {"npm": frozenset({"exec"})}
_PACKAGE_EXEC_HEADS: frozenset[str] = frozenset({"npx"})
# Tokens of an install member that are the verb, not an artifact source.
_INSTALL_VERBS: frozenset[str] = frozenset({"install", "wheel", "exec", "add", "ci", "-i", "i"})

# Command-taking flags whose string argument is a command, not a path (C7).
_COMMAND_FLAGS: frozenset[str] = frozenset({"-c", "-e", "-qec", "-r", "--command", "--eval"})

# Shell-evaluating interpreters: their command-flag body is a shell body that
# descends into members (1c-1). Others (awk, node, perl) keep a synthetic string
# body — R3.8's unobserved-operand class, never descended as shell.
_SHELL_INTERPRETERS: frozenset[str] = frozenset({"sh", "bash", "dash", "zsh"})

# Interpreters whose stdin is executed as code: a bare start is a REPL, and the
# shell toolset ships a stdin feeder (write_stdin). Wrappers (env/timeout/xargs)
# are excluded: a bare wrapper does not interpret its stdin as commands.
_CODE_INTERPRETERS: frozenset[str] = frozenset({"awk", "ash", "perl", "ruby", "node", "php", "lua"})

# Env flags that load code by construction: their operand is a target regardless
# of mode. Search-path flags add only their executable members as targets.
# TODO(G2b): the assignment contract R8/N8 owns the full VAR=value matrix; G2a
# implements only the declared interpreter-env flags that make a file executable.
_EXEC_BY_CONSTRUCTION_ENV: frozenset[str] = frozenset(
    {"LD_PRELOAD", "BASH_ENV", "ENV", "PYTHONSTARTUP"}
)
_SEARCH_PATH_ENV: frozenset[str] = frozenset(
    {"PYTHONPATH", "LD_LIBRARY_PATH", "PERL5LIB", "RUBYOPT"}
)
_RUBYOPT_ENV = "RUBYOPT"

# --- Index-selection evidence (C1 / 1c-2) -----------------------------------
#
# Declared data, not heuristics: a flag, an env assignment, or a config path.
# Any non-official value re-points the resolver, and the posture is then not
# per-source — every source of that install derives ``other-url``.
INDEX_SELECTION_FLAGS: tuple[str, ...] = (
    "--index-url",
    "-i",
    "--extra-index-url",
    "--registry",
)
INDEX_SELECTION_ENV: tuple[str, ...] = (
    "PIP_INDEX_URL",
    "UV_INDEX_URL",
    "NPM_CONFIG_REGISTRY",
    "PIP_CONFIG_FILE",  # 1c-2: the explicit config pointer joins the env set
)
INDEX_SELECTION_CONFIG: tuple[str, ...] = (
    "~/.pip/pip.conf",
    "~/.config/pip/pip.conf",
    "$VIRTUAL_ENV/pip.conf",
    "/etc/pip.conf",
    "~/.npmrc",
    "./.npmrc",
)
# Config-mutating commands: ``<manager> config set`` with an index key is a
# PACKAGE_INSTALL member carrying an ``other-url`` source, so R5'' denies the
# re-point before it can persist.
_CONFIG_MUTATING_MANAGERS: frozenset[str] = frozenset({"pip", "pip3", "npm", "yarn", "pnpm"})
_INDEX_KEY_TOKENS: tuple[str, ...] = ("index-url", "index_url", "registry")

# The declared config set is manager-scoped: a pip install does not read
# ``.npmrc``, so a stray npm config must not re-point it (and an unknown manager
# reads every location — the refusing direction).
_CONFIG_PATHS_BY_FAMILY: dict[str, tuple[str, ...]] = {
    "pip": ("~/.pip/pip.conf", "~/.config/pip/pip.conf", "$VIRTUAL_ENV/pip.conf", "/etc/pip.conf"),
    "npm": ("~/.npmrc", "./.npmrc"),
}
_PIP_INDEX_ENV: frozenset[str] = frozenset({"PIP_INDEX_URL", "UV_INDEX_URL"})
_NPM_INDEX_ENV: frozenset[str] = frozenset({"NPM_CONFIG_REGISTRY"})

# R12 — module execution resolves against the interpreter's recorded roots, never
# against ``cwd``: ``python3 -m yt_dlp`` is a module name, not a relative path.
_MODULE_FLAG = "-m"
_MODULE_SOURCE_SUFFIX = ".so"

# Write-capable argument shapes whose write operand is a host-mount write (A8/N6).
_TEE_VERBS: frozenset[str] = frozenset({"tee"})
_DD_VERBS: frozenset[str] = frozenset({"dd"})
_COPY_VERBS: frozenset[str] = frozenset({"cp", "mv", "rsync"})

# Mode-flag escalation (A9/N11): verbs that can grant exec bits or extract with
# pre-set modes into an agent-writable prefix.
_CHMOD_VERBS: frozenset[str] = frozenset({"install", "chmod", "setfacl"})
_EXTRACT_VERBS: frozenset[str] = frozenset({"tar", "unzip", "dpkg"})

_WHEEL_SUFFIXES: tuple[str, ...] = (".whl",)
_SDIST_SUFFIXES: tuple[str, ...] = (".tar.gz", ".tar.bz2", ".tgz", ".zip", ".tar.xz", ".tar")

# Flags of an install verb whose following token is their value, not a source.
_INSTALL_VALUE_FLAGS: frozenset[str] = frozenset(
    {
        "--only-binary",
        "--target",
        "--prefix",
        "--index-url",
        "-i",
        "--extra-index-url",
        "--registry",
    }
)
# Flags whose following token is a fetched requirement / project source.
_INSTALL_SOURCE_FLAGS: frozenset[str] = frozenset(
    {"-r", "--requirement", "-e", "--editable", "-c", "--constraint"}
)

_ASSIGNMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# Constraints that suppress install scripts; their presence is recorded on the
# action so R5‴ can distinguish a sanctioned install from a bare one.
_SCRIPTS_DISABLED_FLAGS: frozenset[str] = frozenset({"--only-binary=:all:", "--ignore-scripts"})


class ParseError(Exception):
    """Raised by a :class:`Parser` when the command cannot be parsed."""


class Parser(Protocol):
    """A shell parser: text in, bashlex-shaped AST nodes out.

    The protocol exists so a pinned alternative to ``bashlex`` can plug in
    without touching the classifier. Nodes are consumed structurally (``kind``,
    ``parts``, ``word``, ``pos``), which is the shape bashlex emits.
    """

    def parse(self, command: str) -> list[Any]:
        """Parse ``command``; raise :class:`ParseError` on failure."""
        ...


class BashlexParser:
    """The :class:`Parser` over ``bashlex``."""

    def parse(self, command: str) -> list[Any]:
        try:
            return list(bashlex.parse(command))
        except Exception as exc:
            # bashlex raises more than ParsingError on hostile input (AttributeError,
            # IndexError, AssertionError, RecursionError seen in practice); every one
            # is "could not parse", which is UNRESOLVED (2.3), never a classifier crash.
            raise ParseError(f"{type(exc).__name__}: {exc}") from exc


# ---------------------------------------------------------------------------
# Filesystem resolution — the one I/O point.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Probe:
    """A single path probe: what the filesystem said once, frozen."""

    resolved: ResolvedTarget
    exists: bool
    executable: bool


def _unresolved(raw: str) -> ResolvedTarget:
    return ResolvedTarget(raw=raw, path=None, resolution=Resolution.UNRESOLVED, ref=None)


def _probe(raw: str, cwd: Path | None) -> _Probe:
    """Resolve ``raw`` against ``cwd`` once and read its mode.

    Only ``Path.stat`` / ``Path.resolve`` touch the filesystem. A path that will
    not resolve is a classification failure and becomes ``UNRESOLVED`` — the
    refusing shape — not a silently-clean path.
    """
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = (cwd or Path.cwd()) / candidate
    try:
        resolved = candidate.resolve()
    except (OSError, RuntimeError):
        return _Probe(_unresolved(raw), exists=False, executable=False)
    try:
        status = resolved.stat()
    except OSError:
        # Not on disk: still a frozen identity by canonical spelling, no inode.
        ref = ArtifactRef(raw=raw, path_key=str(resolved), inode_key=None)
        return _Probe(
            ResolvedTarget(raw=raw, path=resolved, resolution=Resolution.PATH, ref=ref),
            exists=False,
            executable=False,
        )
    ref = ArtifactRef(raw=raw, path_key=str(resolved), inode_key=(status.st_dev, status.st_ino))
    return _Probe(
        ResolvedTarget(raw=raw, path=resolved, resolution=Resolution.PATH, ref=ref),
        exists=True,
        executable=bool(status.st_mode & 0o111),
    )


def _with_executable(probe: _Probe) -> _Probe:
    """Mark a probe exec-bearing by construction (an exec-by-construction flag)."""
    if probe.resolved.resolution is Resolution.UNRESOLVED:
        return probe
    return _Probe(probe.resolved, exists=probe.exists, executable=True)


def _on_path(name: str) -> _Probe | None:
    """Probe ``$PATH`` for a bare command word; ``None`` when it is not found."""
    if not name or "/" in name or name.startswith("-"):
        return None
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry:
            continue
        candidate = Path(entry) / name
        try:
            status = candidate.stat()
        except OSError:
            continue
        if status.st_mode & 0o111:
            return _probe(str(candidate), None)
    return None


# ---------------------------------------------------------------------------
# bashlex node helpers.
# ---------------------------------------------------------------------------


def _kind(node: Any) -> str:
    return str(getattr(node, "kind", ""))


def _parts(node: Any) -> list[Any]:
    parts = getattr(node, "parts", None)
    return list(parts) if parts is not None else []


def _list_parts(node: Any) -> list[Any]:
    parts = getattr(node, "list", None)
    return list(parts) if parts is not None else []


def _word_text(node: Any) -> str:
    return str(getattr(node, "word", ""))


def _word_nodes(node: Any) -> list[Any]:
    """The word and assignment children of a command, in source order.

    bashlex lifts a leading ``VAR=value`` into an ``assignment`` node whose
    ``word`` is the whole spelling; the shell state is exactly that token, so it
    must stay in the argument list the classifier splits.
    """
    return [part for part in _parts(node) if _kind(part) in {"word", "assignment"}]


def _span(node: Any, text: str) -> str:
    start, end = getattr(node, "pos", (0, len(text)))
    start = max(0, min(int(start), len(text)))
    end = max(start, min(int(end), len(text)))
    return text[start:end]


def _visit(node: Any) -> Iterable[Any]:
    """Every node reachable from ``node``, pre-order, source order."""
    yield node
    for part in [*_parts(node), *_list_parts(node)]:
        yield from _visit(part)
    command = getattr(node, "command", None)
    if command is not None:
        yield from _visit(command)


def _split_assignments(words: Sequence[str]) -> tuple[dict[str, str], list[str]]:
    """Split ``VAR=value`` prefixes from argv.

    Only the *leading* assignments are shell state; a token like ``of=/mnt/x``
    after the command word is an argument (``dd of=…``), never an assignment.
    """
    env: dict[str, str] = {}
    index = 0
    while index < len(words):
        name, sep, value = words[index].partition("=")
        if not (sep and _ASSIGNMENT_NAME.fullmatch(name)):
            break
        env[name] = value
        index += 1
    return env, list(words[index:])


def _base_name(head: str) -> str:
    if head in {".", ".."}:
        # ``Path(".").name`` is ``""``: a bare dot is a builtin (``. file``), not
        # an empty head. A path spelling (``./x``) still resolves to its name.
        return head
    return Path(head).name


def _head_after_wrappers(argv: Sequence[str]) -> tuple[str, Sequence[str]]:
    """Skip leading exec wrappers (``command``/``builtin``/``exec``, ``busybox``).

    The returned pair is the effective head and the argv beginning at it, so an
    operand probe (A5(b)) and kind derivation see the command actually executed.
    """
    rest = list(argv)
    while rest:
        base = _base_name(rest[0])
        if rest[0] in _PROBE_OPERAND_BUILTINS:
            rest = rest[1:]
            while rest and (rest[0].startswith("-") or rest[0] == "--"):
                rest = rest[1:]
            continue
        if base == "busybox" and len(rest) > 1:
            rest = rest[1:]
            while rest and rest[0].startswith("-"):
                rest = rest[1:]
            continue
        break
    return (rest[0] if rest else ""), tuple(rest)


def _is_python(head: str) -> bool:
    """True for ``python``/``pypy`` and their versioned spellings (R12 applies)."""
    base = _base_name(head)
    for prefix in ("python", "pypy"):
        if base.startswith(prefix):
            rest = base[len(prefix) :]
            if not rest or rest.replace(".", "").isdigit():
                return True
    return False


def _is_interpreter(head: str) -> bool:
    return _is_python(head) or _base_name(head) in INTERPRETER_CLASS


def _is_wrapper(head: str) -> bool:
    return (
        _is_interpreter(head)
        or _base_name(head) in EXEC_BEARING_WRAPPERS
        or _base_name(head) in _PACKAGE_TOOL_RUNNERS
        or head.startswith(_LOADER_PREFIXES)
    )


def _suffix_shape(raw: str) -> SourceShape:
    lowered = raw.lower()
    if lowered.endswith(_WHEEL_SUFFIXES):
        return SourceShape.WHEEL
    if lowered.endswith(_SDIST_SUFFIXES):
        return SourceShape.SOURCE_DIST
    return SourceShape.UNKNOWN


def _looks_like_url(raw: str) -> bool:
    return "://" in raw or raw.startswith(("git+", "hg+"))


def host_of(raw: str) -> str | None:
    """RFC-3986 host of ``raw``: after any userinfo, lowercased, no port/trailing dot.

    Returns ``None`` when the operand is not a parseable absolute URI with a
    special scheme. ``pypi.org@10.0.0.5`` yields ``10.0.0.5`` — the userinfo is
    never the host (1c-5). An IDN label makes the host unparseable-as-ASCII and
    returns ``None``; the caller derives ``other-url`` for ``None`` (fail-closed).
    """
    try:
        split = urlsplit(raw)
        host = split.hostname
    except ValueError:
        return None
    if split.scheme not in {"http", "https"} or host is None:
        return None
    host = host.lower().rstrip(".")
    if not host:
        return None
    try:
        host.encode("ascii")
    except UnicodeEncodeError:
        return None
    return host


def _classify_url(raw: str) -> SourceKind:
    host = host_of(raw)
    if host is not None and host in OFFICIAL_INDEX_HOSTS:
        return SourceKind.OFFICIAL_INDEX
    return SourceKind.OTHER_URL


# ---------------------------------------------------------------------------
# Kind derivation.
# ---------------------------------------------------------------------------


def _is_chmod_shape(head: str, argv: Sequence[str], *, redirects_host: bool) -> bool:
    base = _base_name(head)
    if base in _CHMOD_VERBS:
        return any(
            _is_exec_mode_token(arg) or arg == "--mode" or arg.startswith("--mode=")
            for arg in argv[1:]
        )
    if base == "cp":
        return any(arg.startswith("--mode=") for arg in argv[1:])
    return base in _EXTRACT_VERBS and redirects_host


_EXEC_MODE_TOKEN = re.compile(
    r"^(?:[-+]?[ugoa]*[+]?[xX]|[-+]?[rwxXst]*[+]?[xX][rwxXst]*|[0-7]*[1-7][0-7]*)$"
)


def _is_exec_mode_token(arg: str) -> bool:
    """True for a mode argument that can grant execute bits (``+x``, ``u+x``, ``0755``)."""
    if arg in {"-R", "-m", "--recursive"}:
        return arg == "-m"
    if arg.startswith("-m") and arg != "-m":
        return True
    return bool(_EXEC_MODE_TOKEN.match(arg)) and ("x" in arg.lower() or arg.lstrip("-+").isdigit())


def _is_write_host(
    head: str, argv: Sequence[str], *, redirects_host: bool, cwd: Path | None = None
) -> bool:
    """True when this member's write destination is outside the agent's surfaces.

    ``tee``/``dd of=``/copy destinations are judged by where they resolve: into
    scratch or the workspace is an ordinary agent write (the reconcilers record
    it); anywhere else keeps the host-mount posture.
    """
    if redirects_host:
        return True
    base = _base_name(head)
    operands = [arg for arg in argv[1:] if not arg.startswith("-")]
    if base in _TEE_VERBS:
        if not operands:
            return True
        return any(_write_target_is_host(_probe(arg, cwd).resolved.path) for arg in operands)
    if base in _DD_VERBS:
        targets = [arg[3:] for arg in operands if arg.startswith("of=")]
        return any(_write_target_is_host(_probe(arg, cwd).resolved.path) for arg in targets)
    if base in _COPY_VERBS and len(operands) >= 2:
        return _write_target_is_host(_probe(operands[-1], cwd).resolved.path)
    return False


def _derive_kind(
    head: str,
    argv: Sequence[str],
    *,
    redirects_host: bool,
    install: bool,
    cwd: Path | None = None,
) -> ActionKind:
    """One kind per member (1c-1). Install wins, then chmod, then host write, else execute."""
    if install:
        return ActionKind.PACKAGE_INSTALL
    if _is_chmod_shape(head, argv, redirects_host=redirects_host):
        return ActionKind.CHMOD_EXEC
    if _is_write_host(head, argv, redirects_host=redirects_host, cwd=cwd):
        return ActionKind.WRITE_HOST_MOUNT
    return ActionKind.EXECUTE


def _scripts_disabled(argv: Sequence[str]) -> bool:
    """True when argv carries a scripts-disabled constraint (R5‴'s input)."""
    return any(
        token in _SCRIPTS_DISABLED_FLAGS or token.startswith("--only-binary=:all:")
        for token in argv
    )


def _without_index_values(words: Sequence[str]) -> list[str]:
    """``words`` with the index-selection flags' operands removed (flags kept).

    The install grammar looks for the verb positionally and treats every
    non-flag token as a verb candidate, so ``pip --index-url http://target
    install x`` reads the URL as the verb. Removing only the *index-selection*
    operands lets the same grammar see ``install``. Every other declared
    value-flag keeps its named miss intact (AC-28b: ``npm --prefix /opt/app
    install`` stays the EXECUTE the table declares).
    """
    out: list[str] = []
    skip = False
    for token in words:
        if skip:
            skip = False
            continue
        flag, separator, _value = token.partition("=")
        if token in INDEX_SELECTION_FLAGS:
            out.append(token)
            skip = True
            continue
        if flag in INDEX_SELECTION_FLAGS and separator and flag.startswith("--"):
            out.append(flag)
            continue
        if token.startswith("-i") and not token.startswith("--") and len(token) > 2:
            out.append("-i")
            continue
        out.append(token)
    return out


def _install_member(  # noqa: PLR0911 - one return per declared grammar clause
    head: str, argv: Sequence[str]
) -> bool:
    """True when this member's argv fires the install grammar (C3, 1c-6).

    The declared manager/verb table is the provenance trigger's, never a second
    grammar: a member that fires the walk classifies as an install. The 1c-6
    build/exec verbs (``pip wheel``, ``python* -m pip wheel``, ``npm exec``,
    ``npx``, ``uvx``) are members of the same table, so they share its
    position-independence and its declared misses.

    ``install_trigger`` tokenises with ``shlex`` and ignores ``cwd``; it is fed
    the member's own text so the two classifiers cannot disagree.
    """
    command = " ".join([head, *argv[1:]]) if head else ""
    if install_trigger(command) is not None:
        return True
    if install_trigger(" ".join(_without_index_values([head, *argv[1:]]))) is not None:
        # Same grammar, index-selection operands removed: a re-pointed index flag
        # no longer hides the verb (``pip --index-url URL install x``).
        return True
    if _is_config_mutation(argv):
        # 1c-2: a config-mutating command assigns an index key, so it is an
        # install member of the same posture (R5'' denies the re-point).
        return True
    base = _base_name(head)
    rest = list(argv[1:])
    if base in _PACKAGE_EXEC_HEADS or base in _PACKAGE_TOOL_RUNNERS:
        return True
    if base in _PACKAGE_EXEC_VERBS:
        return any(token in _PACKAGE_EXEC_VERBS[base] for token in rest)
    if _is_pip_member(base):
        return any(token in _PIP_BUILD_VERBS for token in rest)
    if _is_pip_module_member(argv):
        return any(token in _PIP_BUILD_VERBS for token in argv[3:])
    return False


def _is_pip_member(base: str) -> bool:
    return base in {"pip", "pip3"} or base.startswith(("pip3.", "pip."))


def _is_pip_module_member(argv: Sequence[str]) -> bool:
    """``python* -m pip ...`` — the pip module form of a build/exec member."""
    return (
        len(argv) >= 3
        and _is_interpreter(argv[0])
        and argv[1] == "-m"
        and argv[2] in {"pip", "pip3"}
    )


# ---------------------------------------------------------------------------
# Target extraction (A5).
# ---------------------------------------------------------------------------


def _write_target_is_host(path: Path | None) -> bool:
    """A write outside quarantine *and* outside the agent's own writable surface.

    Scratch and the workspace are where the agent is supposed to write: the
    reconcilers observe those writes after the exec, so the pre-exec gate must not
    deny them on a ledger miss (round-30 integration FINDING-2 — the chicken-and-egg
    that stopped the observation loop from ever closing). A write anywhere else
    keeps the host-mount posture. An unresolved target refuses.
    """
    if path is None:
        return True
    if is_quarantine_path(path):
        return False
    return not is_agent_writable(path)


def _redirect_probes(node: Any, cwd: Path | None) -> tuple[list[_Probe], bool]:
    """Output-redirection operands and whether any writes outside quarantine."""
    probes: list[_Probe] = []
    writes_host = False
    for part in _parts(node):
        if _kind(part) != "redirect":
            continue
        if str(getattr(part, "type", "")).startswith("<"):
            continue
        output = getattr(part, "output", None)
        if output is None:
            continue
        raw = _word_text(output)
        if not raw or raw in {"-", "/dev/null"} or "$" in raw:
            continue
        probe = _probe(raw, cwd)
        probes.append(probe)
        if _write_target_is_host(probe.resolved.path):
            writes_host = True
    return probes, writes_host


def _env_flag_targets(env: dict[str, str], cwd: Path | None) -> list[_Probe]:
    """Target candidates carried by assignments (N8 — one contract).

    The exec-by-construction flags make their operand a target regardless of
    mode; a search-path flag adds only its existing executable members; any other
    ``VAR=value`` assignment contributes its value only when that value is an
    existing executable file (a plain value names no artifact, so it is neither a
    target nor a deny).
    """
    probes: list[_Probe] = []
    for name, value in env.items():
        if name in _EXEC_BY_CONSTRUCTION_ENV:
            # Code is loaded by the flag, so the operand is a target regardless
            # of its mode (A5(c)); force the exec bit for target selection.
            probes.extend(
                _with_executable(_probe(entry, cwd)) for entry in value.split(":") if entry
            )
        elif name in _SEARCH_PATH_ENV:
            for entry in value.split(":"):
                probe = _probe(entry, cwd) if entry else None
                if probe is not None and probe.executable and not _is_directory(probe):
                    # A directory carries the exec bit; it is never a target
                    # (a ``PYTHONPATH`` entry is neither a target nor a deny).
                    probes.append(probe)
        elif name == "NODE_OPTIONS":
            probes.extend(
                _with_executable(_probe(token.split("=", 1)[1], cwd))
                for token in value.split()
                if token.startswith("--require=")
            )
        elif value:
            probe = _probe(value, cwd)
            if probe.exists and probe.executable and not _is_directory(probe):
                probes.append(probe)
    return probes


def _is_directory(probe: _Probe) -> bool:
    """True when this probe resolved to a directory (never an executable target)."""
    path = probe.resolved.path
    return path is not None and path.is_dir()


def _module_operand(head: str, argv: Sequence[str]) -> tuple[int, str] | None:
    """The (index, name) of a ``python* -m <module>`` selector (R12), if any."""
    if not _is_python(head):
        return None
    for index in range(1, len(argv) - 1):
        if argv[index] == _MODULE_FLAG:
            return index + 1, argv[index + 1]
    return None


def _resolve_module(name: str, roots: Sequence[Path]) -> ResolvedTarget:
    """Resolve ``name`` under the recorded site-packages roots (single I/O point).

    A module name is never a ``cwd``-relative path: probing it as one would both
    invent a target and miss the module. Dotted names walk the package path; an
    extension module is matched by its shared-object suffix. Unresolvable stays
    ``UNRESOLVED`` so R8's degraded class sees it.
    """
    if not name or name.startswith("-") or "/" in name:
        return _unresolved(name)
    parts = name.split(".")
    for root in roots:
        base = root.joinpath(*parts)
        candidates = [Path(f"{base}.py"), base / "__init__.py"]
        candidates.extend(sorted(base.parent.glob(f"{base.name}*{_MODULE_SOURCE_SUFFIX}")))
        for candidate in candidates:
            if candidate.is_file():
                return _probe(str(candidate), None).resolved
    return _unresolved(name)


def _interpreter_operands(
    head: str, argv: Sequence[str], cwd: Path | None, *, piped: bool, descend_body: bool = False
) -> list[_Probe]:
    """Target candidates among an interpreter/wrapper's arguments (A5(b), C7).

    The command string of a command-taking flag is ``UNRESOLVED`` (a command, not
    a path). Other non-flag arguments are probed. For a declared interpreter any
    operand is a target (a script need not carry its own exec bit); for a
    non-interpreter wrapper only an existing executable operand is.
    """
    probes: list[_Probe] = []
    is_interp = _is_interpreter(head)
    module = _module_operand(head, argv)
    module_index = module[0] if module is not None else None
    pending_command = False
    for position, arg in enumerate(argv[1:], start=1):
        if position == module_index:
            # R12: the module selector is resolved against site-packages, never
            # probed as a cwd-relative path.
            continue
        if pending_command:
            # A shell body descends as a member (1c-1); it is not a path target.
            if not descend_body:
                probes.append(_Probe(_unresolved(arg), exists=False, executable=False))
            pending_command = False
            continue
        if arg in _COMMAND_FLAGS:
            pending_command = True
            continue
        if arg.startswith("-") or arg in {"-", "--"}:
            continue
        if "$" in arg or "`" in arg:
            probes.append(_Probe(_unresolved(arg), exists=False, executable=False))
            continue
        probe = _probe(arg, cwd)
        if is_interp or probe.executable:
            probes.append(probe)
    if piped and _is_wrapper(head):
        # The pipeline feeds this interpreter's stdin: an unobserved operand (R3.8).
        probes.append(
            _Probe(_unresolved(f"<stdin>:{_base_name(head)}"), exists=False, executable=False)
        )
    return probes


def _flag_payload(argv: Sequence[str], flag: str) -> str:
    for index, token in enumerate(argv):
        if token == flag and index + 1 < len(argv):
            return argv[index + 1]
    return flag


def _named_path_probes(argv: Sequence[str], cwd: Path | None) -> list[_Probe]:
    """Every non-flag argument that names an existing path, regardless of the head (S-4).

    The interpreter allow-table only probes operands for declared interpreters, so
    an unlisted interpreter's script operand was invisible. This reads every
    non-flag argument as a path candidate; the gate denies a *tainted* one unless
    the head is an allow-listed interpreter. A command-flag body is a command, not
    a path, so it is skipped.
    """
    probes: list[_Probe] = []
    pending_command = False
    for arg in argv[1:]:
        if pending_command:
            pending_command = False
            continue
        if arg in _COMMAND_FLAGS:
            pending_command = True
            continue
        if arg.startswith("-") or arg in {"-", "--"}:
            continue
        if "$" in arg or "`" in arg:
            continue
        probe = _probe(arg, cwd)
        if probe.exists:
            probes.append(probe)
    return probes


# ---------------------------------------------------------------------------
# Index-selection evidence (C1 / 1c-2).
# ---------------------------------------------------------------------------


def _official_index_value(raw: str) -> bool:
    """True when ``raw`` names an official index host; unparseable is never official."""
    host = host_of(raw)
    return host is not None and host in OFFICIAL_INDEX_HOSTS


def _flag_values(argv: Sequence[str]) -> list[tuple[str, str]]:
    """``(token-as-spelled, value)`` for every declared index-selection flag.

    Fused long (``--index-url=…``) and short (``-iURL``) forms carry their value;
    a bare flag takes the next token. A trailing flag with no value is evidence
    with an empty value and therefore re-points (fail-closed).
    """
    values: list[tuple[str, str]] = []
    index = 1
    while index < len(argv):
        token = argv[index]
        flag, separator, value = token.partition("=")
        if flag in INDEX_SELECTION_FLAGS and separator and flag.startswith("--"):
            values.append((token, value))
            index += 1
        elif token in INDEX_SELECTION_FLAGS:
            if index + 1 < len(argv):
                values.append((token, argv[index + 1]))
                index += 2
            else:
                values.append((token, ""))
                index += 1
        elif token.startswith("-i") and not token.startswith("--") and len(token) > 2:
            values.append((token, token[2:]))
            index += 1
        else:
            index += 1
    return values


def _install_family(argv: Sequence[str]) -> str:
    """The package-manager family whose index config this member consults."""
    if not argv:
        return "other"
    base = _base_name(argv[0])
    if _is_pip_member(base) or base == "uv" or _is_pip_module_member(argv):
        return "pip"
    if base in {"npm", "npx", "pnpm", "yarn", "bun"}:
        return "npm"
    return "other"


def _config_paths(env: dict[str, str], cwd: Path | None, family: str) -> list[tuple[str, Path]]:
    """``(declared spelling, path)`` for the config locations this manager reads (1c-2)."""
    home = env.get("HOME") or os.environ.get("HOME") or str(Path.home())
    virtualenv = env.get("VIRTUAL_ENV") or os.environ.get("VIRTUAL_ENV", "")
    spellings = list(_CONFIG_PATHS_BY_FAMILY.get(family, INDEX_SELECTION_CONFIG))
    explicit = env.get("PIP_CONFIG_FILE") or os.environ.get("PIP_CONFIG_FILE")
    if explicit and family in {"pip", "other"}:
        spellings.append(explicit)
    paths: list[tuple[str, Path]] = []
    for spelling in spellings:
        if "$VIRTUAL_ENV" in spelling and not virtualenv:
            # An unset VIRTUAL_ENV must not fabricate "/pip.conf" at the root.
            continue
        expanded = spelling.replace("$VIRTUAL_ENV", virtualenv).replace("~", home, 1)
        if "$" in expanded:
            # An unset VIRTUAL_ENV names no path; nothing to read.
            continue
        path = Path(expanded)
        if not path.is_absolute():
            path = (cwd or Path.cwd()) / path
        paths.append((spelling, path))
    return paths


def _config_index_values(path: Path) -> list[str] | None:
    """Index/registry values assigned in a config file; ``None`` when unreadable.

    The key is matched on its last ``:``-segment so an npm auth line
    (``//registry.npmjs.org/:_authToken=…``) is not mistaken for a registry
    assignment: only ``index-url``/``index_url``/``registry`` are index keys.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    values: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped[0] in "#;[":  # comments and section headers
            continue
        key, separator, value = stripped.partition("=")
        if not separator:
            continue
        key_text = key.strip().lower().rsplit(":", 1)[-1].strip()
        if key_text in _INDEX_KEY_TOKENS:
            values.append(value.strip().strip("'\""))
    return values


def _config_evidence(
    env: dict[str, str], cwd: Path | None, family: str, repointed: bool
) -> tuple[list[str], bool]:
    """Record every present config path and decide whether it re-points.

    Presence is evidence and goes on ``index_tokens``. The contents decide the
    posture: an official index keeps the official class (AC-30's allow cell), a
    non-official one re-points, and a present-but-unreadable or key-less config
    re-points too — an unrecognised config is not an official one.
    """
    tokens: list[str] = []
    for spelling, path in _config_paths(env, cwd, family):
        if not path.is_file():
            continue
        tokens.append(spelling)
        values = _config_index_values(path)
        if not values:
            repointed = True
            continue
        if any(not _official_index_value(value) for value in values):
            repointed = True
    return tokens, repointed


def _declared_config_paths(env: dict[str, str], cwd: Path | None) -> frozenset[Path]:
    """Every declared config location, resolved, for the write-side channel (1c-2).

    Both managers' lists plus the explicit pointer, resolved the way a write
    destination is resolved, so equality is on the real path (a symlinked home
    still matches the ``~/.pip/pip.conf`` it stands for).
    """
    spellings: list[tuple[str, Path]] = []
    for family in _CONFIG_PATHS_BY_FAMILY:
        spellings.extend(_config_paths(env, cwd, family))
    spellings.extend(_config_paths(env, cwd, "other"))
    resolved: set[Path] = set()
    for _spelling, path in spellings:
        try:
            resolved.add(Path(os.path.realpath(path)))
        except OSError:
            continue
    return frozenset(resolved)


def _config_write_target(
    node: Any,
    argv: Sequence[str],
    env: dict[str, str],
    cwd: Path | None,
) -> ResolvedTarget | None:
    """The declared config location this member **writes**, if any (1c-2).

    The chain's first step is a write: a redirect, ``tee``, a copy destination or
    ``dd of=`` aimed at a config path is the config channel, so it classifies as
    an install carrying an ``other-url`` source and R5'' denies it *before* it
    persists. A write elsewhere is unaffected. ``~`` is expanded the way the
    shell would (the read side already expands it through ``HOME``); probing the
    literal tilde would look for ``./~/.pip/pip.conf`` and miss the channel.
    """
    declared = _declared_config_paths(env, cwd)
    if not declared:
        return None
    home = env.get("HOME") or os.environ.get("HOME") or str(Path.home())
    candidates: list[str] = []
    for part in _parts(node):
        if _kind(part) != "redirect" or str(getattr(part, "type", "")).startswith("<"):
            continue
        raw = _word_text(getattr(part, "output", None))
        if raw and raw not in {"-", "/dev/null"} and "$" not in raw and "`" not in raw:
            candidates.append(raw)
    base = _base_name(argv[0]) if argv else ""
    operands = [arg for arg in argv[1:] if not arg.startswith("-")]
    if base in _TEE_VERBS:
        candidates.extend(operands)
    elif base in _COPY_VERBS and len(operands) >= 2:
        candidates.append(operands[-1])
    elif base in _DD_VERBS:
        candidates.extend(arg[3:] for arg in operands if arg.startswith("of="))
    for raw in candidates:
        expanded = f"{home}{raw[1:]}" if raw == "~" or raw.startswith("~/") else raw
        probe = _probe(expanded, cwd)
        path = probe.resolved.path
        if path is not None and Path(os.path.realpath(path)) in declared:
            return probe.resolved
    return None


def _install_sources(
    argv: Sequence[str],
    config_write: ResolvedTarget | None,
    env: dict[str, str],
    cwd: Path | None,
    *,
    operator_approved: bool,
) -> tuple[list[ArtifactSource], tuple[str, ...]]:
    """Sources and index tokens for a PACKAGE_INSTALL member (C1 / 1c-2).

    Three entry paths, one posture: a write into a config location, a
    config-mutating command, or an ordinary install with its index evidence.
    """
    if config_write is not None:
        destination = str(config_write.path or config_write.raw)
        return (
            [ArtifactSource(raw=destination, kind=SourceKind.OTHER_URL, shape=SourceShape.UNKNOWN)],
            (destination,),
        )
    if _is_config_mutation(argv):
        source = _config_mutation_source(argv)
        return [source], tuple(token for token in (source.raw,) if token)
    index_tokens, index_repointed = _index_selection(argv, env, cwd)
    sources = _artifact_sources(
        argv,
        cwd,
        operator_approved=operator_approved,
        index_repointed=index_repointed,
    )
    return sources, index_tokens


def _index_selection(
    argv: Sequence[str], env: dict[str, str], cwd: Path | None
) -> tuple[tuple[str, ...], bool]:
    """Every index-selection token found, and whether the resolver is re-pointed."""
    family = _install_family(argv)
    tokens: list[str] = []
    repointed = False
    for token, value in _flag_values(argv):
        tokens.append(token)
        if value and "=" not in token:
            tokens.append(value)
        if not _official_index_value(value):
            repointed = True
    for name, value in env.items():
        if name not in INDEX_SELECTION_ENV:
            continue
        if family == "pip" and name in _NPM_INDEX_ENV:
            continue
        if family == "npm" and name in _PIP_INDEX_ENV:
            continue
        tokens.append(f"{name}={value}")
        if name != "PIP_CONFIG_FILE" and not _official_index_value(value):
            # PIP_CONFIG_FILE's value is a path; its contents decide below.
            repointed = True
    config_tokens, repointed = _config_evidence(env, cwd, family, repointed)
    tokens.extend(config_tokens)
    return tuple(tokens), repointed


def _is_config_mutation(argv: Sequence[str]) -> bool:
    """True when this member assigns an index key through ``<manager> config set``."""
    if not argv:
        return False
    manager = _base_name(argv[0])
    if _is_pip_module_member(argv):
        manager = "pip"
    if manager not in _CONFIG_MUTATING_MANAGERS:
        return False
    rest = list(argv[1:])
    if "config" not in rest or "set" not in rest:
        return False
    return any(
        _INDEX_KEY_TOKENS[0] in token.lower()
        or _INDEX_KEY_TOKENS[1] in token.lower()
        or token.lower().endswith(_INDEX_KEY_TOKENS[2])
        for token in rest
    )


def _config_mutation_source(argv: Sequence[str]) -> ArtifactSource:
    """The ``other-url`` source a config-mutating command carries (1c-2).

    The re-point is not a per-value property: ``pip config set global.index-url
    …`` rewrites where every later install resolves, so the member is an install
    with an unsafe source and R5'' denies it before it persists.
    """
    assigned = ""
    for position, token in enumerate(argv[1:], start=1):
        lowered = token.lower()
        if (
            _INDEX_KEY_TOKENS[0] in lowered
            or _INDEX_KEY_TOKENS[1] in lowered
            or lowered.endswith(_INDEX_KEY_TOKENS[2])
        ) and position + 1 < len(argv):
            assigned = argv[position + 1]
            break
    raw = assigned or " ".join(argv)
    return ArtifactSource(raw=raw, kind=SourceKind.OTHER_URL, shape=_suffix_shape(raw))


# ---------------------------------------------------------------------------
# Artifact sources (C1).
# ---------------------------------------------------------------------------


def _artifact_sources(
    argv: Sequence[str],
    cwd: Path | None,
    *,
    operator_approved: bool,
    index_repointed: bool = False,
) -> list[ArtifactSource]:
    """Artifact sources of an install member (C1 derivation table).

    The index-selection evidence (1c-2) decides the *posture*: once the resolver
    is re-pointed, every non-local source of this install derives ``other-url``,
    because re-pointing is not a per-source property. A local path stays local
    (the table's row is unconditional).
    """
    sources: list[ArtifactSource] = []
    skip_next = False
    for arg in _unfuse_flags(_source_tokens(argv)):
        if skip_next:
            skip_next = False
            continue
        if arg in _INSTALL_VALUE_FLAGS:
            skip_next = True
            continue
        if arg in _INSTALL_SOURCE_FLAGS:
            # The operand is a fetched source (C1), never a skipped value: a
            # local reqs/project path is ``local``, a URL takes its host class.
            continue
        if arg.startswith("-") or not arg:
            continue
        source = _derive_source(
            arg, cwd, operator_approved=operator_approved, index_repointed=index_repointed
        )
        if source is not None:
            sources.append(source)
    return sources


def _derive_source(
    arg: str,
    cwd: Path | None,
    *,
    operator_approved: bool,
    index_repointed: bool = False,
) -> ArtifactSource | None:
    """One C1 source derivation: URL => host class, path-shaped => local, name => index."""
    shape = _suffix_shape(arg)
    if _looks_like_url(arg):
        kind = SourceKind.OPERATOR_APPROVED if operator_approved else _classify_url(arg)
        if index_repointed and kind is not SourceKind.OPERATOR_APPROVED:
            kind = SourceKind.OTHER_URL
        return ArtifactSource(raw=arg, kind=kind, shape=shape)
    if "/" in arg or arg in {".", ".."} or arg.startswith("~") or shape is not SourceShape.UNKNOWN:
        probe = _probe(arg, cwd)
        return ArtifactSource(raw=arg, kind=SourceKind.LOCAL, shape=shape, target=probe.resolved)
    if operator_approved:
        kind = SourceKind.OPERATOR_APPROVED
    elif index_repointed:
        kind = SourceKind.OTHER_URL
    else:
        kind = SourceKind.OFFICIAL_INDEX
    return ArtifactSource(raw=arg, kind=kind, shape=SourceShape.UNKNOWN)


def _unfuse_flags(tokens: Sequence[str]) -> list[str]:
    """Split the fused spellings of declared source/value flags.

    ``--requirement=X`` and ``-rX`` are the same option as ``-r X`` to pip's
    option parser; matching only the bare spelling dropped the operand.
    """
    declared = _INSTALL_SOURCE_FLAGS | _INSTALL_VALUE_FLAGS
    short = {flag for flag in declared if len(flag) == 2 and flag[0] == "-" and flag[1] != "-"}
    out: list[str] = []
    for token in tokens:
        if token.startswith("--") and "=" in token:
            flag, _sep, value = token.partition("=")
            if flag in declared:
                out.extend((flag, value))
                continue
        elif token[:2] in short and len(token) > 2 and not token.startswith("--"):
            out.extend((token[:2], token[2:]))
            continue
        out.append(token)
    return out


def _source_tokens(argv: Sequence[str]) -> list[str]:
    """The tokens of an install member that can name an artifact source.

    Drops the manager head, ``python* -m pip``'s module selector, and the verb
    itself, so ``install``/``wheel``/``exec`` never become a bare official-index
    ``source`` (which would spuriously arm R5‴).
    """
    start = 1
    if _is_pip_module_member(argv):
        start = 3
    tokens = list(argv[start:])
    return [token for token in tokens if token not in _INSTALL_VERBS]


# ---------------------------------------------------------------------------
# Quarantine references (2.4).
# ---------------------------------------------------------------------------


def _references_quarantine_text(text: str, cwd: Path | None) -> bool:
    """Raw-text quarantine reference: the canonical spelling appears verbatim.

    A textual match is compared against the configured quarantine spelling, never
    against an arbitrary expansion (the substrate catches string-constructed
    spellings). ``cwd`` under quarantine counts too.
    """
    if cwd is not None and is_quarantine_path(cwd):
        return True
    root = str(QUARANTINE_DIR).rstrip("/")
    return bool(root) and root in text


def _source_quarantine(source: ArtifactSource) -> bool:
    target = source.target
    return target is not None and target.path is not None and is_quarantine_path(target.path)


def _under_quarantine(target: ResolvedTarget) -> bool:
    return target.path is not None and is_quarantine_path(target.path)


def _dedupe(targets: Iterable[ResolvedTarget]) -> tuple[ResolvedTarget, ...]:
    seen: set[tuple[str, str]] = set()
    ordered: list[ResolvedTarget] = []
    for target in targets:
        key = (target.raw, str(target.path))
        if key in seen:
            continue
        seen.add(key)
        ordered.append(target)
    return tuple(ordered)


# ---------------------------------------------------------------------------
# Parsed fragments (1c-1).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Fragment:
    """One member's source text plus the context that does not survive re-parsing.

    ``substitution`` records a substitution body; ``piped`` records a command on
    the right of a ``|`` — the pipeline feeds its stdin (R3.8). ``cwd`` is the
    directory a preceding ``cd``/``pushd`` in the same command establishes.
    """

    text: str
    substitution: bool = False
    piped: bool = False
    descended: bool = False
    cwd: Path | None = None


@dataclass(frozen=True, slots=True)
class _Context:
    cwd: Path | None
    operator_approved: bool
    env: dict[str, str] = field(default_factory=dict)
    module_roots: tuple[Path, ...] = ()


class _Classifier:
    """One classification pass. Holds the parser and caches body parses."""

    def __init__(self, parser: Parser) -> None:
        self._parser = parser
        self._cache: dict[str, list[Any] | None] = {}
        self._functions: dict[str, list[_Fragment]] = {}
        self._used_functions: set[str] = set()

    def classify(self, command: str, context: _Context) -> Action:
        try:
            ast = self._parser.parse(command)
        except ParseError:
            return _unresolved_action(command, context)
        _mark_piped(ast)
        fragments = self._fragments(
            ast, command, context=context, substitution=False, fell_piped=False, inherited_cwd=None
        )
        if not fragments:
            # Only a command-free AST (a bare builtin keyword form) may land empty;
            # an AST that holds a command node but yielded no member is a
            # construct this walker does not model, so refuse it (2.3).
            if any(_kind(node) == "command" for tree in ast for node in _visit(tree)):
                return _unresolved_action(command, context)
            return _empty_action(command, context)
        fragments = self._expand_calls(fragments)
        actions = [self._member(fragment, context) for fragment in fragments]
        primary, rest = actions[0], actions[1:]
        return primary.model_copy(
            update={
                "members": (*primary.members, *rest),
                "command": command,
                # MINOR-2: the composite is the union over every member, so a
                # later member's quarantine reference is not hidden on the parent.
                "references_quarantine": any(a.references_quarantine for a in actions),
                "executes_quarantine": any(a.executes_quarantine for a in actions),
            }
        )

    # -- fragments ----------------------------------------------------------

    def _fragments(
        self,
        nodes: Iterable[Any],
        text: str,
        *,
        context: _Context,
        substitution: bool,
        fell_piped: bool,
        inherited_cwd: Path | None,
    ) -> list[_Fragment]:
        fragments: list[_Fragment] = []
        for node in nodes:
            fragments.extend(
                self._node_fragments(
                    node,
                    text,
                    context=context,
                    substitution=substitution,
                    fell_piped=fell_piped,
                    inherited_cwd=inherited_cwd,
                )
            )
        return fragments

    def _node_fragments(  # noqa: PLR0911 - one return per AST node shape
        self,
        node: Any,
        text: str,
        *,
        context: _Context,
        substitution: bool,
        fell_piped: bool,
        inherited_cwd: Path | None,
    ) -> list[_Fragment]:
        kind = _kind(node)
        if kind in {"list", "pipeline", "compound", "function", "if", "for", "while", "until"}:
            # ``compound`` keeps its body under ``list`` (subshell, brace group,
            # if/for/while): both slots are walked, or the body is silently lost.
            children = [*_parts(node), *_list_parts(node)]
            if kind == "function" and children:
                self._register_function(node, children, text)
                return []
            if kind in {"list", "pipeline", "compound"}:
                # Thread pipeline-stdin and preceding-``cd`` state across the
                # children: a ``cd`` earlier in the list changes the cwd of the
                # commands that follow it (MAJOR-2). A child of a pipeline
                # already carries ``fell_piped`` from its parent.
                children, inherited_cwd = _track_shell_state(
                    children, fell_piped=fell_piped, inherited_cwd=inherited_cwd
                )
                if kind == "pipeline":
                    # Only a stage to the RIGHT of a ``|`` reads the pipe: the first
                    # stage keeps the outer state (``python3 x.py | head`` does not
                    # feed python3's stdin; ``echo x | (sh)`` feeds the subshell).
                    staged: list[_Fragment] = []
                    seen_pipe = False
                    for child in children:
                        if _kind(child) == "pipe":
                            seen_pipe = True
                            continue
                        staged.extend(
                            self._node_fragments(
                                child,
                                text,
                                context=context,
                                substitution=substitution,
                                fell_piped=fell_piped or seen_pipe,
                                inherited_cwd=inherited_cwd,
                            )
                        )
                    # Every stage of a real pipeline is executed context (1c-12): a
                    # quarantine reference feeding ``| sh`` is an executed operand.
                    return [replace(fragment, descended=True) for fragment in staged]
            return self._fragments(
                children,
                text,
                context=context,
                substitution=substitution,
                fell_piped=fell_piped,
                inherited_cwd=inherited_cwd,
            )
        if kind in {"operator", "pipe", "reservedword"}:
            return []
        if kind == "command":
            local_piped = fell_piped or bool(getattr(node, "_piped", False))
            return [
                _Fragment(
                    _span(node, text),
                    substitution,
                    local_piped,
                    fell_piped,
                    inherited_cwd,
                )
            ]
        if kind in {"word", "assignment"}:
            return self._substitutions(
                node, text, context=context, fell_piped=fell_piped, inherited_cwd=inherited_cwd
            )
        return self._fragments(
            [*_parts(node), *_list_parts(node)],
            text,
            context=context,
            substitution=substitution,
            fell_piped=fell_piped,
            inherited_cwd=inherited_cwd,
        )

    def _substitutions(
        self,
        node: Any,
        text: str,
        *,
        context: _Context,
        fell_piped: bool,
        inherited_cwd: Path | None,
    ) -> list[_Fragment]:
        fragments: list[_Fragment] = []
        for part in _visit(node):
            if _kind(part) not in {"commandsubstitution", "processsubstitution"}:
                continue
            command = getattr(part, "command", None)
            if command is not None:
                fragments.extend(
                    self._node_fragments(
                        command,
                        text,
                        context=context,
                        substitution=True,
                        fell_piped=fell_piped,
                        inherited_cwd=inherited_cwd,
                    )
                )
        return fragments

    def _register_function(self, node: Any, children: list[Any], text: str) -> None:
        """Record a function body defined in the same command (1c-1).

        ``name(){ sh; }`` is not executed at definition, but a later member may
        call it; its body is walked when named so a piped/cd-context call is not
        lost. The body is flattened to its command fragments (any operator between
        them is dropped, so definition-time word text is not re-executed). The
        function node's span is re-parsed in place of the whole command so member
        spans resolve against the right source text.
        """
        name_node, body_nodes = _function_parts(children)
        name = _word_text(name_node) if name_node is not None else ""
        if not name or not body_nodes:
            return
        # bashlex positions are absolute in the text that was parsed, so body
        # members are spanned against ``text`` itself — slicing a body-local copy
        # with absolute positions emptied every definition not at offset 0.
        body_text = _span(node, text)
        fragments: list[_Fragment] = []
        for body in body_nodes:
            fragments.extend(
                self._node_fragments(
                    body,
                    text,
                    context=_Context(cwd=None, operator_approved=False),
                    substitution=False,
                    fell_piped=False,
                    inherited_cwd=None,
                )
            )
        if not fragments or any(not fragment.text.strip() for fragment in fragments):
            # A body this walker cannot span is refused, never silently empty.
            fragments = [_Fragment(body_text, descended=True)]
        self._functions[name] = fragments

    # -- one member ---------------------------------------------------------

    def _member(self, fragment: _Fragment, context: _Context) -> Action:
        ast = self._parse_body(fragment.text)
        if ast is None:
            return _unresolved_action(fragment.text, context)
        commands = list(_walk_commands(ast))
        if len(commands) != 1:
            # A substitution body that is itself a compound or unparseable: the
            # member is refused, never reduced to a guess (2.3).
            return _unresolved_action(fragment.text, context)
        # A member lifted out of a pipeline loses its ``|`` when re-parsed, so the
        # carried flag is authoritative for it; a pipe inside the body is already
        # marked on the node by ``_mark_piped``.
        piped = fragment.piped or bool(getattr(commands[0], "_piped", False))
        return self._command(fragment, commands[0], context, piped=piped)

    def _command(self, fragment: _Fragment, node: Any, context: _Context, *, piped: bool) -> Action:
        words = [_word_text(part) for part in _word_nodes(node)]
        local_env, argv = _split_assignments(words)
        env = {**context.env, **local_env}
        head = argv[0] if argv else ""
        # MAJOR-2: a preceding literal-absolute ``cd`` re-bases this member's
        # relative operands; when no cd is literal the caller cwd is used as-is.
        member_context = context
        if fragment.cwd is not None:
            member_context = _Context(
                cwd=fragment.cwd,
                operator_approved=context.operator_approved,
                env=context.env,
                module_roots=context.module_roots,
            )
        cwd = member_context.cwd
        # BLOCKER-3/MAJOR-1: an exec wrapper's operand is the effective head
        # (``command sh …``, ``exec ./bin``, ``busybox sh …``), so kind and probes
        # see what actually runs.
        effective_head, effective_argv = _head_after_wrappers(argv)
        install = _install_member(head, argv) or _install_member(effective_head, effective_argv)
        kind_head, kind_argv = (effective_head, effective_argv) if effective_head else (head, argv)
        redirect_probes, redirects_host = _redirect_probes(node, cwd)
        kind = _derive_kind(
            kind_head, kind_argv, redirects_host=redirects_host, install=install, cwd=cwd
        )
        # 1c-2 write side: a write aimed at a declared config location is the
        # config channel, not an ordinary write — the re-point is denied before
        # it can persist (config write → install read → R5'' rejection).
        config_write = _config_write_target(node, argv, env, cwd)
        if config_write is not None and kind in {
            ActionKind.EXECUTE,
            ActionKind.WRITE_HOST_MOUNT,
        }:
            kind = ActionKind.PACKAGE_INSTALL

        members = self._contained(fragment, node, member_context)
        synthetic = (
            _bare_body(node, piped=piped)
            if _has_body(effective_head or head) and not members
            else None
        )
        targets: list[ResolvedTarget] = []
        interpreter_input: list[ResolvedTarget] = []
        sources: list[ArtifactSource] = []
        index_tokens: tuple[str, ...] = ()
        input_probes = _input_redirect_probes(node, cwd)

        if kind is ActionKind.PACKAGE_INSTALL:
            sources, index_tokens = _install_sources(
                argv,
                config_write,
                env,
                cwd,
                operator_approved=context.operator_approved,
            )
        elif head:
            probes = self._probes(head, argv, env, piped=piped, cwd=cwd)
            if kind is ActionKind.CHMOD_EXEC:
                # N9 carve-out: chmod operands are targets regardless of current
                # mode — a chmod target is by nature not yet executable.
                carve_out = [
                    _probe(arg, cwd)
                    for arg in argv[1:]
                    if not arg.startswith("-") and not _is_exec_mode_token(arg)
                ]
                targets = [*(t.resolved for t in carve_out), *_exec_targets(probes)]
            else:
                targets = _exec_targets(probes)
            interpreter_input = self._interpreter_input(
                # The carrier keys on the effective head — the same unwrapping
                # the kind derivation uses. A raw-head read let ``exec sh`` /
                # ``command sh`` reach a REPL with a clean R9 allow (round 27).
                effective_head or head,
                effective_argv if effective_head else argv,
                piped=piped,
                cwd=cwd,
            )
            # A here-document never survives as a node the walker models: the
            # parsed forms reach the fail-closed shape, and a compound member
            # (``true && bash <<EOF``) arrives with the body already dropped. The
            # carrier is therefore read from the member's own text, once, for
            # every member — the only place the body is still visible.
            heredoc_head = _heredoc_interpreter_text(fragment.text)
            if heredoc_head is not None:
                interpreter_input = [
                    *interpreter_input,
                    _unresolved(f"<heredoc>:{heredoc_head}"),
                ]
            if _is_interpreter(head) or _is_interpreter(effective_head):
                # A5(b): an argument to a declared interpreter is exec-bearing.
                targets = [*targets, *interpreter_input]
            if _is_interpreter(effective_head):
                # BLOCKER-2: a file fed to an interpreter via stdin redirect /
                # here-string is an executed operand, so R1/R3.8 compute from it.
                input_targets = [probe.resolved for probe in input_probes]
                interpreter_input = [*interpreter_input, *input_targets]
                if not _is_interpreter(head):
                    targets = [*targets, *input_targets]
            # N8: assignment-carried operands are this member's shell state, so
            # they are probed for every head — not only for wrappers.
            targets = [*targets, *_exec_targets(_env_flag_targets(env, cwd))]
            # R12: ``python -m <module>`` resolves under site-packages, never cwd.
            module = _module_operand(head, argv) or _module_operand(effective_head, effective_argv)
            if module is not None:
                targets.append(_resolve_module(module[1], context.module_roots))
        if synthetic is not None:
            # A bare synthetic shell body: unattributable, R8's degraded class
            # carrying the command text — never a silent allow (N4).
            targets.append(_unresolved(synthetic))

        return _build_action(
            kind=kind,
            command=fragment.text,
            context=member_context,
            members=members,
            redirect_probes=redirect_probes,
            input_probes=input_probes,
            targets=targets,
            interpreter_input=interpreter_input,
            named_paths=[probe.resolved for probe in _named_path_probes(argv, cwd)],
            head=effective_head or head,
            interpreter_allowlisted=_is_interpreter(effective_head or head),
            sources=sources,
            index_tokens=index_tokens,
            install=install,
            scripts_disabled=_scripts_disabled(argv),
            executed_context=fragment.descended or fragment.piped,
        )

    def _probes(  # noqa: PLR0912 - one branch per exec-bearing shape in A5
        self,
        head: str,
        argv: Sequence[str],
        env: dict[str, str],
        *,
        piped: bool,
        cwd: Path | None,
    ) -> list[_Probe]:
        """Every exec-bearing probe for this member (A5(a)/(b)/(c)).

        The head resolves on ``$PATH`` when bare and against ``cwd`` when it
        carries a path separator. Operands resolve against the same ``cwd`` —
        the caller's perspective, never the process's.
        """
        probes: list[_Probe] = []
        base = _base_name(head)
        applet = _busybox_applet_argv(argv)
        if applet is not None:
            # The applet is the executed head; probe it and its operands as such.
            return self._probes(applet[0], applet, env, piped=piped, cwd=cwd)
        # A declared interpreter's operand is exec-bearing whether or not it
        # carries its own mode (A5(b)); the same holds for an exec operand
        # (``exec ./credman``, ``command sh script``) and a sourced file.
        operands_descend = (
            _is_interpreter(head) or base in _PROBE_OPERAND_BUILTINS or base in _SOURCE_BUILTINS
        )
        if base in _PROBE_OPERAND_BUILTINS:
            # ``exec``/``command``/``builtin`` run their operand: probe it like a
            # wrapper (``exec ./credman``, ``command sh Q/pl.sh``).
            # The operand is the executed head itself, so it is probed exactly as a
            # head would be (and its own operands as that head's would be).
            inner = _strip_leading_flags(argv[1:])
            if inner:
                return self._probes(inner[0], inner, env, piped=piped, cwd=cwd)
            return _env_flag_targets(env, cwd)
        if base in _SOURCE_BUILTINS:
            # ``source``/``.`` execute the file operand, no exec bit required.
            for arg in argv[1:]:
                if arg.startswith("-") or not arg:
                    continue
                if "$" in arg or "`" in arg:
                    probes.append(_Probe(_unresolved(arg), exists=False, executable=False))
                else:
                    probes.append(_probe(arg, cwd))
            probes.extend(_env_flag_targets(env, cwd))
            return probes
        if base in SHELL_BUILTINS:
            # A builtin has no disk identity and its operands are not exec targets.
            return _env_flag_targets(env, cwd)
        if not _is_interpreter(head):
            if "/" in head:
                probes.append(_probe(head, cwd))
            else:
                found = _on_path(head)
                probes.append(found if found is not None else _probe(head, cwd))
        if _is_wrapper(head):
            probes.extend(
                _interpreter_operands(head, argv, cwd, piped=piped, descend_body=_has_body(head))
            )
            probes.extend(_env_flag_targets(env, cwd))
        else:
            # (a) an argv word that resolves to an existing executable file.
            # (C7) a command-taking flag's string argument is an exec-bearing
            # candidate with ``UNRESOLVED`` resolution — a command, not a path.
            pending_command = False
            for arg in argv[1:]:
                if pending_command:
                    probes.append(_Probe(_unresolved(arg), exists=False, executable=False))
                    pending_command = False
                    continue
                if arg in _COMMAND_FLAGS:
                    pending_command = True
                    continue
                if arg.startswith(("-", "$")) or "`" in arg:
                    continue
                probe = _probe(arg, cwd)
                if probe.executable or operands_descend:
                    probes.append(probe)
        return probes

    def _interpreter_input(
        self,
        head: str,
        argv: Sequence[str],
        *,
        piped: bool,
        cwd: Path | None,
    ) -> list[ResolvedTarget]:
        """An interpreter's stdin/source operands (N4 source taxonomy)."""
        applet = _busybox_applet_argv(argv)
        if applet is not None:
            return self._interpreter_input(applet[0], applet, piped=piped, cwd=cwd)
        if not _is_interpreter(head):
            return []
        inputs: list[ResolvedTarget] = []
        module = _module_operand(head, argv)
        module_index = module[0] if module is not None else None
        shell_body = _base_name(head) in _SHELL_INTERPRETERS
        body_seen = False
        index = 1
        while index < len(argv):
            arg = argv[index]
            index += 1
            if index - 1 == module_index:
                continue
            if arg in _COMMAND_FLAGS:
                # A ``-c``/``-e``/``-r`` payload is a command string, never a path.
                # A shell body descends as a member (1c-1); a non-shell body stays
                # a synthetic unobserved operand (R3.8). When that opaque body
                # interpolates a substitution, the operand reaching the
                # interpreter is unobserved through it, so R3.8 fires (AC-33).
                body_seen = True
                if index < len(argv):
                    payload = argv[index]
                    if not shell_body and _has_substitution(payload):
                        inputs.append(_unresolved(f"<substitution>:{_base_name(head)}"))
                    index += 1
                continue
            if arg.startswith(("-", "<", ">", "|")):
                continue
            if "$" in arg or "`" in arg:
                inputs.append(_unresolved(arg))
                continue
            inputs.append(_probe(arg, cwd).resolved)
        if piped:
            inputs.append(_unresolved(f"<stdin>:{_base_name(head)}"))
        elif not inputs and not body_seen and module is None and _interprets_stdin_as_code(head):
            # A bare code interpreter with no operand, body or pipe is a REPL: its
            # stdin is the operand, and the shell toolset ships a feeder
            # (write_stdin). R3.8 denies it; a script/``-c``/``-m`` form is not
            # bare and keeps its own treatment.
            inputs.append(_unresolved(f"<stdin>:{_base_name(head)}"))
        return inputs

    def _contained(self, fragment: _Fragment, node: Any, context: _Context) -> list[Action]:
        """Substitution, ``-c`` and ``eval``/``trap`` body members (1c-1, C8)."""
        members: list[Action] = []
        words = _word_nodes(node)
        body_word = _interpreter_body_word(words)
        string_body = _string_body_word(words)
        function_body = self._function_fragments(node, fragment, context)
        for part in _visit(node):
            kind = _kind(part)
            if kind in {"commandsubstitution", "processsubstitution"}:
                command = getattr(part, "command", None)
                if command is not None:
                    nested = self._nested(_span(command, fragment.text), context, substitution=True)
                    members.extend(nested)
                    self._absorb_function_calls(nested)
            elif kind == "word" and part is body_word and _body_descends(part):
                members.extend(self._nested(_word_text(part), context, substitution=False))
            elif kind == "word" and part is string_body:
                members.extend(self._string_body(_word_text(part), context))
        members.extend(function_body)
        return members

    def _string_body(self, body: str, context: _Context) -> list[Action]:
        """Decompose an ``eval``/``trap`` string body as a substitution-like body.

        A body that cannot be parsed is the refusing shape (2.3), never a guess.
        """
        nested = self._nested(body, context, substitution=True)
        self._absorb_function_calls(nested)
        return nested

    def _function_fragments(
        self, node: Any, fragment: _Fragment, context: _Context
    ) -> list[Action]:
        """Members of a function defined in this command and called by this member."""
        words = [_word_text(part) for part in _word_nodes(node)]
        _env, argv = _split_assignments(words)
        inner = _strip_leading_flags(argv[1:]) if argv else []
        called = next(
            (arg for arg in inner if arg in self._functions and arg not in self._used_functions),
            None,
        )
        if called is None:
            return []
        self._used_functions.add(called)
        inherited = fragment.cwd or context.cwd
        members: list[Action] = []
        for body_fragment in self._functions[called]:
            carried = _Fragment(
                body_fragment.text,
                substitution=body_fragment.substitution,
                piped=fragment.piped or body_fragment.piped,
                descended=True,
                cwd=inherited,
            )
            members.append(self._member(carried, context))
        return members

    def _absorb_function_calls(self, members: list[Action]) -> None:
        """A function called inside a ``-c``/substitution/eval body is walked too."""
        for member in members:
            if member.command.strip() in self._functions:
                self._used_functions.add(member.command.strip())

    def _nested(self, body: str, context: _Context, *, substitution: bool) -> list[Action]:
        ast = self._parse_body(body)
        if ast is None:
            return [_unresolved_action(body, context)]
        fragments = self._fragments(
            ast,
            body,
            context=context,
            substitution=substitution,
            fell_piped=False,
            inherited_cwd=None,
        )
        # A ``-c``/substitution/eval body is executed context (1c-12).
        fragments = [
            replace(fragment, descended=True) for fragment in self._expand_calls(fragments)
        ]
        return [self._member(fragment, context) for fragment in fragments]

    def _expand_calls(self, fragments: list[_Fragment]) -> list[_Fragment]:
        """Replace a call to a function defined in this command by its body.

        The call site's pipe and ``cd`` state carry into every body member, so
        ``reader(){ sh; }; echo x | reader`` decides ``sh`` as piped (R3.8). A
        recursive call is expanded once; a second visit stays the bare call,
        whose unresolvable head fails closed.
        """
        expanded: list[_Fragment] = []
        for fragment in fragments:
            words = fragment.text.split()
            name = words[0] if words else ""
            if name in self._functions and name not in self._used_functions:
                self._used_functions.add(name)
                expanded.extend(
                    _Fragment(
                        body.text,
                        substitution=body.substitution,
                        piped=fragment.piped or body.piped,
                        descended=True,
                        cwd=body.cwd or fragment.cwd,
                    )
                    for body in self._expand_calls(list(self._functions[name]))
                )
                self._used_functions.discard(name)
            else:
                expanded.append(fragment)
        return expanded

    def _parse_body(self, body: str) -> list[Any] | None:
        if body not in self._cache:
            try:
                ast = self._parser.parse(body)
            except ParseError:
                ast = None
            _mark_piped(ast)
            self._cache[body] = ast
        return self._cache[body]


def _busybox_applet_argv(argv: Sequence[str]) -> tuple[str, ...] | None:
    """The applet invocation a ``busybox`` member selects positionally (1c-7).

    ``busybox sh script`` is ``sh script``: the applet is a command word, not a
    file operand. Returning the unwrapped argv lets target extraction treat it
    exactly like the head it is, instead of probing ``sh`` as a cwd-relative
    path and inventing a provenance miss.
    """
    if not argv or _base_name(argv[0]) != "busybox":
        return None
    rest = _strip_leading_flags(argv[1:])
    return tuple(rest) if rest else None


def _strip_leading_flags(args: Sequence[str]) -> list[str]:
    """Drop a wrapper builtin's leading options (``command -p``, ``builtin --``)."""
    rest = list(args)
    while rest and (rest[0].startswith("-") or rest[0] == "--"):
        rest = rest[1:]
    return rest


def _function_parts(children: list[Any]) -> tuple[Any, list[Any]]:
    """Split a ``function`` node's parts into its name word and body nodes."""
    name_node: Any = None
    body: list[Any] = []
    for child in children:
        kind = _kind(child)
        if name_node is None and kind == "word":
            name_node = child
        elif kind in {"compound", "reservedword", "list", "command", "pipeline"}:
            body.append(child)
    return name_node, body


def _cd_target(node: Any) -> Path | None:
    """The literal absolute directory a ``cd``/``pushd`` command establishes."""
    words = [_word_text(part) for part in _word_nodes(node)]
    _env, argv = _split_assignments(words)
    if not argv or _base_name(argv[0]) not in {"cd", "pushd"}:
        return None
    target = next((arg for arg in argv[1:] if not arg.startswith("-")), None)
    if target is None or "$" in target or "`" in target:
        return None
    candidate = Path(target)
    # Only literal absolute targets are inherited; a relative ``cd`` stays a
    # caller-relative guess and must not silently re-base the member.
    if not candidate.is_absolute():
        return None
    return candidate


def _track_shell_state(
    children: list[Any],
    *,
    fell_piped: bool,  # noqa: ARG001 - kept for call-site symmetry; pipes are staged by the caller
    inherited_cwd: Path | None,
) -> tuple[list[Any], Path | None]:
    """Thread pipeline-stdin and preceding-``cd`` state across a compound's children.

    ``fell_piped`` is True inside the right side of a ``|``: the whole compound
    body inherits it (``echo x | (sh)``). A ``cd``/``pushd`` command updates the
    inherited cwd for the commands that follow it in the same list.
    """
    current = inherited_cwd
    for child in children:
        kind = _kind(child)
        if kind == "pipe":
            # ``fell_piped`` is already authoritative for every child of this
            # node; only a ``cd`` updates state here.
            continue
        if kind == "command":
            target = _cd_target(child)
            if target is not None:
                current = target
    return children, current


def _mark_piped(ast: list[Any] | None) -> None:
    """Mark every command sitting on the right of a pipe (R3.8's operand source)."""
    if ast is None:
        return
    for node in _walk_nodes(ast):
        if _kind(node) != "pipeline":
            continue
        seen_pipe = False
        for part in _parts(node):
            if _kind(part) == "pipe":
                seen_pipe = True
                continue
            if seen_pipe and _kind(part) == "command":
                part._piped = True


def _walk_nodes(nodes: Iterable[Any]) -> Iterable[Any]:
    for node in nodes:
        yield node
        yield from _walk_nodes([*_parts(node), *_list_parts(node)])


def _exec_targets(probes: Sequence[_Probe]) -> list[ResolvedTarget]:
    """Executable files plus unresolved words.

    A declared interpreter's existing operand is a target whether or not it is
    executable (A5(b)); every unresolved candidate is carried so R8/R3.5 see it.
    """
    return [
        probe.resolved
        for probe in probes
        if probe.executable
        or probe.resolved.resolution is Resolution.UNRESOLVED
        or probe.resolved.path is not None
    ]


def _walk_commands(ast: Iterable[Any]) -> Iterable[Any]:
    for node in ast:
        kind = _kind(node)
        if kind == "command":
            yield node
        elif kind in {"operator", "pipe", "reservedword"}:
            continue
        else:
            yield from _walk_commands([*_parts(node), *_list_parts(node)])


def _has_substitution(text: str) -> bool:
    """True when a command-flag payload interpolates a substitution."""
    return "$(" in text or "`" in text


def _interprets_stdin_as_code(head: str) -> bool:
    """True for interpreters whose stdin is executed as code (the feeder classes)."""
    base = _base_name(head)
    return _is_python(head) or base in _CODE_INTERPRETERS or base in _SHELL_INTERPRETERS


def _has_heredoc(node: Any) -> bool:
    """True when the node carries a here-document redirect (``<<``/``<<-``)."""
    return any(
        _kind(part) == "redirect" and str(getattr(part, "type", "")) in {"<<", "<<-"}
        for part in _parts(node)
    )


def _heredoc_interpreter_text(command: str) -> str | None:
    """The interpreter a parse-resistant here-document feeds, when that is the shape.

    ``bashlex`` parses ``<<EOF`` but fails on a quoted delimiter (``<<'EOF'``), and
    the fail-closed shape would otherwise carry only an unresolved command — leaving
    the body to execute inside the interpreter with no R3.8 entry. The head is read
    syntactically (first line, ``VAR=value`` prefixes and quotes stripped, exec
    wrappers unwrapped — the same effective-head model the parses use); ``<<`` must
    be present, so this is a shell-syntax check, not a word denylist.
    """
    if "<<" not in command:
        return None
    first = command.strip().splitlines()[0] if command.strip() else ""
    tokens = [_strip_quotes(token) for token in re.findall(r"\S+", first)]
    if not tokens:
        return None
    head, _rest = _head_after_wrappers(tokens)
    if not head:
        return None
    head = _base_name(head)
    return head if _interprets_stdin_as_code(head) or _is_interpreter(head) else None


def _strip_quotes(token: str) -> str:
    """A raw-text token without one matching pair of surrounding quotes."""
    if len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'}:
        return token[1:-1]
    return token


def _has_body(head: str) -> bool:
    """True for a shell interpreter whose command-flag payload descends as a member."""
    return _base_name(head) in _SHELL_INTERPRETERS


def _bare_body(node: Any, *, piped: bool) -> str | None:
    """The ``-c`` payload word of a shell interpreter, when it does not descend."""
    words = _word_nodes(node)
    body = _interpreter_body_word(words)
    if body is None or _body_descends(body, piped=piped):
        return None
    return _word_text(body)


def _body_descends(word: Any, *, piped: bool = False) -> bool:
    """A shell ``-c`` body descends when it is a compound or feeds an interpreter.

    A bare synthetic body (`bash -c 'echo hi'`) is R8's degraded class carrying
    the command text, not a silently allowed sub-action (N4 source taxonomy).
    A body that the pipeline feeds (``echo x | bash -c 'sh'``) descends too: the
    piped stdin is the executed operand, so a bare body must not swallow it.
    """
    text = _word_text(word)
    if piped:
        return True
    if any(token in text for token in (";", "&&", "||", "|", "$(", "`", "(", ")")):
        return True
    try:
        ast = bashlex.parse(text)
    except (bashlex.errors.ParsingError, NotImplementedError):
        return True
    commands = list(_walk_commands(ast))
    if len(commands) != 1:
        return True
    words = [_word_text(part) for part in _word_nodes(commands[0])]
    _env, argv = _split_assignments(words)
    # The body descends when its **effective** head is a wrapper: the raw first
    # token let ``sh -c 'exec sh'`` stay opaque (R8 degraded allow) while the
    # same body without the ``exec`` prefix descended and denied — the round-27
    # raw-vs-effective head mistake, one nesting deeper (round-28 blocker).
    head, _rest = _head_after_wrappers(argv)
    return bool(head) and _is_wrapper(head)


def _interpreter_body_word(words: list[Any]) -> Any | None:
    """The ``word`` node holding a shell interpreter's ``-c`` payload, if any.

    The interpreter is found through its **effective** head: ``command sh -c …``
    and ``exec bash -c …`` feed the same body as ``sh -c …``, and a raw-first-word
    read missed them entirely — the body was never found, never descended, and the
    compound took a clean allow (round-28's second spelling of the blocker).
    """
    if not words:
        return None
    raw = [_word_text(word) for word in words]
    _env, argv = _split_assignments(raw)
    head, _rest = _head_after_wrappers(argv)
    if not head or not _is_interpreter(head):
        return None
    if _base_name(head) not in _SHELL_INTERPRETERS:
        return None
    for index, candidate in enumerate(words[:-1]):
        if _word_text(candidate) in _COMMAND_FLAGS:
            return words[index + 1]
    return None


def _string_body_word(words: list[Any]) -> Any | None:
    """The shell-code string argument of ``eval``/``trap``, if any.

    ``eval`` runs its whole argument list as a body; its first non-flag word is
    the body. ``trap`` runs its first non-flag word as the action. Both are a
    substitution-like body (C8), decomposed or refused — never skipped.
    """
    if not words or _base_name(_word_text(words[0])) not in _STRING_BODY_BUILTINS:
        return None
    if _base_name(_word_text(words[0])) == "trap" and any(
        _word_text(word).startswith("-") for word in words[1:]
    ):
        # ``trap -l``/``-p`` list state; they execute nothing.
        return None
    for candidate in words[1:]:
        text = _word_text(candidate)
        if text.startswith("-") or not text:
            continue
        return candidate
    return None


def _input_redirect_probes(node: Any, cwd: Path | None) -> list[_Probe]:
    """File operands of stdin redirects (``<``, ``<<<``) — an interpreter's input.

    BLOCKER-2: a script fed to an interpreter through stdin is an executed
    operand, so the file it names (a here-string payload) is probed here and the
    caller adds it to ``interpreter_input``/``targets`` for R1/R3.8. A heredoc
    (``<<``) is inline content, not a file, and is not probed.
    """
    probes: list[_Probe] = []
    for part in _parts(node):
        if _kind(part) != "redirect":
            continue
        if str(getattr(part, "type", "")) not in {"<", "<<<"}:
            continue
        raw = _word_text(getattr(part, "output", None))
        if not raw or "$" in raw or "`" in raw:
            continue
        probes.append(_probe(raw, cwd))
    return probes


# ---------------------------------------------------------------------------
# Action assembly.
# ---------------------------------------------------------------------------


def _build_action(
    *,
    kind: ActionKind,
    command: str,
    context: _Context,
    members: list[Action],
    redirect_probes: list[_Probe],
    input_probes: list[_Probe],
    targets: list[ResolvedTarget],
    interpreter_input: list[ResolvedTarget],
    named_paths: list[ResolvedTarget],
    head: str,
    interpreter_allowlisted: bool,
    sources: list[ArtifactSource],
    index_tokens: tuple[str, ...],
    install: bool,
    scripts_disabled: bool,
    executed_context: bool,
) -> Action:
    references = _references_quarantine_text(command, context.cwd) or any(
        _under_quarantine(target)
        for target in (
            *targets,
            *interpreter_input,
            *(probe.resolved for probe in redirect_probes),
            *(probe.resolved for probe in input_probes),
        )
    )
    references = references or any(_source_quarantine(source) for source in sources)
    executes = any(
        _under_quarantine(target)
        for target in (
            *targets,
            *interpreter_input,
            *(probe.resolved for probe in input_probes),
        )
    )
    executes = executes or (install and any(_source_quarantine(source) for source in sources))
    # 1c-12: a member lifted from a descended body (``-c``/substitution) or fed by
    # a pipeline is executed context. A textual quarantine reference there is an
    # executed operand even when its path is not itself exec-bearing (``cat
    # QUAR/x | sh``), so R1's trigger fires; a plain fetch destination
    # (``curl -o QUAR/x``) is not in executed context and stays a write (A2).
    executes = executes or (executed_context and references)
    return Action(
        kind=kind,
        command=command,
        members=tuple(members),
        targets=_dedupe(targets),
        interpreter_input=_dedupe(interpreter_input),
        named_paths=_dedupe(named_paths),
        head=head,
        interpreter_allowlisted=interpreter_allowlisted,
        artifact_sources=tuple(sources),
        index_tokens=index_tokens,
        cwd=context.cwd,
        scripts_disabled=scripts_disabled,
        references_quarantine=references,
        executes_quarantine=executes,
        operator_approved=context.operator_approved,
    )


def _unresolved_action(command: str, context: _Context) -> Action:
    """The fail-closed shape: an EXECUTE with one unresolved target (2.3).

    A parse-resistant here-document fed to an interpreter also carries an
    ``<heredoc>:<interp>`` entry, so R3.8 sees the executed body instead of R8
    treating the whole construct as merely unresolved.
    """
    heredoc_head = _heredoc_interpreter_text(command)
    interpreter_input = (_unresolved(f"<heredoc>:{heredoc_head}"),) if heredoc_head else ()
    return Action(
        kind=ActionKind.EXECUTE,
        command=command,
        targets=(_unresolved(command),),
        interpreter_input=interpreter_input,
        cwd=context.cwd,
        references_quarantine=_references_quarantine_text(command, context.cwd),
        operator_approved=context.operator_approved,
    )


def _empty_action(command: str, context: _Context) -> Action:
    """A builtin-only command (``cd /workspace``): EXECUTE, decided at R9."""
    return Action(
        kind=ActionKind.EXECUTE,
        command=command,
        cwd=context.cwd,
        references_quarantine=_references_quarantine_text(command, context.cwd),
        operator_approved=context.operator_approved,
    )


# ---------------------------------------------------------------------------
# Entry point.
# ---------------------------------------------------------------------------


def _default_module_roots() -> tuple[Path, ...]:
    """The interpreter's recorded site-packages roots (R12's resolution base)."""
    roots: list[Path] = []
    for entry in sys.path:
        if not entry:
            continue
        path = Path(entry)
        if "site-packages" in path.parts or "dist-packages" in path.parts:
            roots.append(path)
    return tuple(roots)


def classify(
    command: str,
    cwd: Path | None = None,
    *,
    operator_approved: bool = False,
    parser: Parser | None = None,
    module_roots: Sequence[Path] | None = None,
) -> Action:
    """Classify a shell ``command`` into a deny-dominant :class:`Action`.

    ``cwd`` is the perspective relative paths resolve against. A command whose
    parse fails is ``UNRESOLVED`` ``EXECUTE`` — the gate then denies it if it
    references quarantine and allows it with a degraded audit otherwise.
    ``module_roots`` overrides the site-packages roots R12 resolves ``-m``
    selectors against (defaults to the running interpreter's recorded roots).
    """
    active = parser or BashlexParser()
    context = _Context(
        cwd=cwd,
        operator_approved=operator_approved,
        module_roots=tuple(module_roots) if module_roots is not None else _default_module_roots(),
    )
    return _Classifier(active).classify(command, context)


__all__ = [
    "BUSYBOX_APPLETS",
    "BUSYBOX_EXEC_WRAPPER_APPLETS",
    "BUSYBOX_INTERPRETER_APPLETS",
    "EXEC_BEARING_WRAPPERS",
    "INDEX_SELECTION_CONFIG",
    "INDEX_SELECTION_ENV",
    "INDEX_SELECTION_FLAGS",
    "INTERPRETER_CLASS",
    "SHELL_BUILTINS",
    "BashlexParser",
    "ParseError",
    "Parser",
    "classify",
    "host_of",
    "merged_interpreter_class",
]
