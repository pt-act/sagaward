"""Oriontrix research apparatus — quarantined, NEVER part of the product DAG.

Everything under ``oriontrix.research`` is measurement-only scaffolding for the propose-dispose
validation study (Spec B). It must never be imported by the product agent factory
(``oriontrix.agents.factory``), the run entry (``oriontrix.core.runner``), or the product interface
(``oriontrix.interface``). In particular it hosts the **single-stage ablation mode** — the one
research baseline that lets a model self-confirm without the deterministic disposer — which is
a locus-1 failure if it ever reaches production. It is gated off by default and reachable only
via its own research entrypoint (``python -m oriontrix.research.ablation``).
"""

from __future__ import annotations
