"""Tool package.

Host-side SDK function tools live in ``<family>/tool[s].py`` and are
imported directly by :mod:`oriontrix.agents.factory`. The sandbox-bound
shell + filesystem tools are emitted by the SDK's ``Shell`` and
``Filesystem`` capabilities and bound to the live sandbox session
per-run.

Import deeply so ``import oriontrix.tools`` doesn't pull every submodule's
deps in eagerly.
"""
