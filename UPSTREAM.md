# Upstream provenance — Sagaward

Sagaward is a derivative work of Strix, an open-source project by OmniSecure Inc.,
licensed under the Apache License, Version 2.0. This file records the upstream
relationship, the fork point, what changed, what was removed, and the provenance
use of the upstream name.

## The upstream

- **Project:** Strix
- **Repository:** https://github.com/usestrix/strix
- **License:** Apache-2.0; Copyright 2025 OmniSecure Inc. The `LICENSE` file is
  retained in this distribution.
- **Fork point:** commit `67536408` (2025-08-12, "Adding stop word param") — the
  merge base of Sagaward's line and `upstream/main`, verified with
  `git merge-base HEAD upstream/main`.
- **Fork repository:** https://github.com/pt-act/sagaward

## What the fork changed

Sagaward keeps the upstream detection engine and adds the Action Provenance
Fence plus the earlier research primitives:

- **The fence** (`sagaward/core/provenance`, `sagaward/core/isolation`,
  `sagaward/runtime/exec_guard.py`): the monotone taint ledger, the action gate
  (`classify → R-table → decide_action`), the observation channel, the
  install/reconcile path, the seed→gate→exec→reconcile loop, the capability
  profiles, and the quarantine mount.
- **The earlier research layers:** the impact gate, durable identity replay, the
  semantic differential engine, the self-hosted OOB oracle, the attack-surface
  inventory with reachability, the race harness, and the business-logic
  state-testing orchestrator. `CHANGELOG.md` carries the phase list.
- **The measurement track:** the propose–dispose funnel and the Behavioral-V2P
  corpus.
- **Selective upstream acquisitions** (each recorded in the project ledger): the
  brotli decoder CVE patch (`5580aa34`), the opengrep integration (`6168d422`),
  and the semantic-confusion coverage (`22b14b2f`).
- **The rename:** package `sagaward`, CLI `sagaward`, environment prefix
  `SAGAWARD_*` (with a one-time legacy `STRIX_*` compatibility shim), home
  directory `~/.sagaward`, and the container images under
  `ghcr.io/pt-act/sagaward-sandbox`.

## What the fork removed

- **The telemetry transports:** PostHog and Scarf, including the public PostHog
  project key, the Scarf endpoint, and their call sites. Sagaward is local-only
  and sends no telemetry.
- **The managed-cloud client and hosted-product surfaces:** the tree carries no
  cloud client, no `cloud login` verb, and no `STRIX_APP_URL`/`STRIX_API_TOKEN`
  configuration. The upstream hosted-product links in the UI were removed.
  Sagaward runs on the user's keys.
- **The Strix wordmark as the product name:** the lineage is carried by the
  GitHub fork mark, this file, and the README's first line. The product wordmark
  is Sagaward; the agent's name is Sága.

## The "Strix" name

"Strix" is used solely to identify the upstream work for provenance and
attribution, as permitted by Apache License 2.0 section 6. No trademark license
is granted. Sagaward is independent and is not affiliated with, nor endorsed by,
OmniSecure Inc. or the upstream Strix project.

## The names

- **Sagaward** is the harness: the ward that watches and writes — the runtime, the
  fence, the bring-up, the session management.
- **Sága** is the agent running inside: the seeress who sees (sjá) and says
  (segja), the guardian of the record. The name is prose in the prompts and the
  skills; there is no Sága package and no registry mark.
- **The genealogy:** the strīx (upstream's name) is the mother; this fork is her
  offspring. In the Greek myth the strīx bore Agrios and Oreios, and Oreios
  prefigures Orion-OS, the framework the fork was born into. The mother's name
  stays upstream; the harness and the agent carry their own.

## Licenses

- **Upstream:** Apache License 2.0, Copyright 2025 OmniSecure Inc. The full text
  is in `LICENSE`; the upstream copyright notice is retained.
- **Sagaward:** Apache License 2.0. The `NOTICE` file records the modifications
  required by section 4(b) of the license.

## Verification

- `git merge-base HEAD upstream/main` →
  `675364086bb68319b4f7ee170ed5ed84ea5528fd`.
- `git merge-base --is-ancestor 67536408 HEAD` → true.
- The removed surfaces are grep-verified against the tree: no `posthog`/`scarf`
  transport modules, no `strix.ai` UI links, and no `ghcr.io/usestrix` image
  references under `sagaward/`.
- The public prefix is `SAGAWARD_*`; the only `STRIX_` strings in the product
  tree are the compatibility shim's legacy-prefix reads and the historical
  research artifacts.
