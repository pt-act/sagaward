# Coder Directive — Full Build & Deployment-Readiness for the Empirical Run

> From: PM/Validator (`opus-4.8-pm-auditor`) · To: Coder (CLI) · Re: strix bounty-grade engine, branch `propose-dispose-validation`
> Goal: take the engine from "partial dev build" to **deployment-ready**, then file a completion report so the PM can validate and run the E1–E4 empirical data gathering for the paper.
> Reference commit (merged-tree, validated green): branch `propose-dispose-validation` merged with `main` → `pytest tests/` = **370 passed, 4 skipped, 19 subtests**.

---

## 0. Current state (what's done, so you don't redo it)

- **Code:** phases 0–5 + correctness-fix-pass + Spec A instrumentation + Spec B M1/M2/M4 + Step-0 emit hook + harness wiring are implemented and validated. The precision-owning detectors (diff/BFLA/expired, OOB correlator, race verdict, logic gate) were adversarially re-derived — no direction inversion. M4 self-confirm is quarantined and off by default; gate neutrality `C ⊆ P` holds.
- **Build:** only a **partial** sandbox image exists (built on Mac with just enough to proceed; the heavy layers were skipped/timed out). The **fast toolchain self-check** image (`containers/Dockerfile.toolcheck`) is fine. The **full sandbox image** (`containers/Dockerfile`) has **not** been built end-to-end.
- **Not started (correctly — these are the PM's step, NOT yours):** the live E1–E4 experiments and empirical data gathering; the M0 live agent run.

Your job is **everything between those two** — the full build and the deployment-readiness gate. Do not run the experiments.

---

## 1. Merge PR #18 to main first

The validated tree is the merge of `propose-dispose-validation` + `main`. Land it before building so the image is built from the canonical commit.

- Resolve the 3 conflicts by taking the **branch** side (see `pr18-resolution/` — `state.py`, `test_proposals_assembler.py`, `test_proposals_disposer_wiring.py`; all `--ours`).
- **Squash-merge** (project convention; title `Propose-dispose validation (Spec B) (#18)`).
- **Verify:** on the merged `main`, `uv run pytest tests/ -q` → `370 passed, 4 skipped, 19 subtests`; `uv run ruff check . && uv run ruff format --check .` clean.
- Record the resulting `main` commit sha — **this sha is the build input and the paper's frozen reference.**

---

## 2. Build the FULL sandbox image (the main deliverable)

The full image is `containers/Dockerfile` (Kali + the complete tool surface), built via `scripts/docker.sh`. The partial build skipped the network-heavy layers below — these are the ones that must now complete.

**Build command:**
```bash
./scripts/docker.sh <tag>          # builds strix-sandbox:<tag> from containers/Dockerfile
# or explicitly, pinning platform for the deploy target:
docker build --platform linux/amd64 -f containers/Dockerfile -t strix-sandbox:<tag> .
```

**The layers the partial build almost certainly skipped — confirm each completes:**
- `nuclei -update-templates` (`Dockerfile:111`) — the known timeout culprit. Network + large download; allow time / retry. **This is the single most likely failure point.**
- `go install ...@latest` for httpx, katana, vulnx, gospider, interactsh-client/-server (`:104–109`). `interactsh-client v1.2.4` is pinned and is **load-bearing for the P2 OOB oracle** — confirm it lands.
- `apt-get install zaproxy wapiti` (`:171`), npm globals retire/eslint/ast-grep/tree-sitter/agent-browser (`:121–126`), tree-sitter parser clones (`:134–159`), pipx semgrep/bandit (`:175–176`), caido-cli `v0.56.0` (`:191–204`).

**Build-environment guidance:**
- Building Kali + Go + npm + nuclei on an arm64 Mac is slow and timeout-prone. Strongly prefer a **Linux x86_64 build host** (or `docker buildx --platform linux/amd64`) with good bandwidth; match the platform to where the empirical run will execute.
- The Dockerfile has arch-conditional fetches (gitleaks `:57–67`, caido `:192–204`) — they handle x86_64/arm64, but the chosen `--platform` must match your deploy host so the right binaries are baked in.
- `@latest` Go installs and the `git clone` tool-grabs (`:162–167`) are non-deterministic and network-dependent; if a clone/install flakes, re-run the layer. For paper-grade reproducibility, consider pinning these (see §5).

**Verify the build (these must all pass before you call it built):**
1. The Dockerfile's own pinned-toolchain self-check layer (`:71–76`, the `grep -F` version asserts) — it fails the build if a pin drifts, so a successful build already proves it.
2. Boot smoke test — the entrypoint must bring up the sidecars:
   ```bash
   docker run --rm --name strix-smoke strix-sandbox:<tag> &
   # expect in logs: "Started interactsh-client with PID ..." and "Caido API is ready"
   docker logs strix-smoke
   ```
3. Tool presence spot-check inside the image:
   ```bash
   docker run --rm strix-sandbox:<tag> bash -lc 'nuclei -version && interactsh-client -version && caido-cli --version && httpx -version && which semgrep trufflehog gitleaks trivy'
   ```

---

## 3. Reconcile the sandbox image reference (deployment gotcha)

The runtime **defaults to a different image than you are building**:
- `strix/config/settings.py:46` → `image: str = Field(default="ghcr.io/usestrix/strix-sandbox:1.0.0")`
- `scripts/docker.sh` tags `strix-sandbox:<tag>` (local, no registry).

If you do nothing, the empirical run will pull **upstream `usestrix` 1.0.0**, not your build — wrong/old pinned tool versions, and not reproducible for the paper. Pick one and make it explicit:
- **Option A (recommended for the run):** tag your build deterministically (e.g. `strix-sandbox:<main-sha>`), push to *your* registry, and set `runtime.image` to that exact ref (via settings/env). 
- **Option B (local-only run):** override `runtime.image` to the local tag `strix-sandbox:<tag>` for the run host.

**Verify:** `strix` (or `uv run strix ...`) resolves the sandbox image to *your* tag — check `_resolve_sandbox_image()` (`strix/interface/cli.py:29`) picks up the override and does not silently fall back to the ghcr default.

---

## 4. Build the B-V2P target images (the live experiment targets)

The experiments deploy the corpus apps live. Build them and verify the `VULN_MODE` switch flips behavior (so vuln vs. patch is real, not cosmetic):
```bash
docker build -t strix-bv2p-idor benchmarks/bv2p/idor_memories
docker build -t strix-bv2p-ssrf benchmarks/bv2p/ssrf_fetch
docker build -t strix-bl-fixture benchmarks/business_logic_fixture
```
**Verify each pair:**
- IDOR: `-e VULN_MODE=1` → cross-user `POST /api/v1/memories/{id}/update` returns 2xx; `VULN_MODE=0` → 403. (`benchmarks/bv2p/idor_memories/app.py`, `core.update_memory` ownership check.)
- SSRF: `VULN_MODE=1` → internal/metadata fetch allowed; `VULN_MODE=0` → blocked by `strix.core.net.is_internal_target`.
- All targets bind to `0.0.0.0:8080`, run sandboxed, **no third-party egress**.

> **Decision to flag to the operator/PM, not to silently resolve:** the corpus apps are *minimal faithful reproductions* sized for hermetic disposer checks (per `benchmarks/bv2p/README.md`). For paper-grade results you may need to **swap in the real upstream repos at the cited commits** (open-webui @ CVE-2024-7041; Flowise `3.0.12 → 3.0.13` for CVE-2026-31829). State clearly in your completion report which you used — minimal fixtures or real upstream — because it changes how the recall/precision numbers are interpreted.

---

## 5. Close the reproducibility/pinning gaps (from validation)

These don't block a local run but **do** affect the paper's "mechanically reproducible" claim and CI durability. Address or explicitly defer with rationale:
- **F-3 (major, reproducibility):** pin the **pyright** version in the dev toolchain (the gate `pyright strix/` was not reproducible across versions; only 8 benign inference findings touched new code, the rest are pre-existing). Pin it (and ideally add pyright to `.pre-commit-config.yaml` next to mypy) so "pyright clean" is a stranger-reproducible gate. mypy-strict is already clean.
- **F-1 (major, test coverage):** add a true-negative regression test for the OOB **expiry window** — mint with a short `window_seconds`, deliver a hit past `expires_at`, assert `correlator` status `expired` and tool `verdict == "unconfirmed"` with **no** callback report. The predicate (`strix/core/oob/correlator.py:57`) is direction-correct today but unguarded; this protects the "timestamp" half of the prior OOB bug class.
- **F-4 (minor, hygiene):** the suite is green in default order but order-dependent — a module-level, never-restored mock at `tests/test_identity_replay.py:34` (`_caido_api.view_request = AsyncMock(...)`) leaks across files. Convert module-level mock mutations to fixtures/teardown **before** enabling `pytest-xdist`/random-order CI.
- **F-2 (minor, semantics — note only):** the `_is_bfla` predicate flags privilege *inversion* (lower succeeds + admin denied), not canonical BFLA (lower succeeds where admin also succeeds). Precision-safe; recall is the proposer's domain; M0 seeds are IDOR/SSRF. **Do not "fix" it without a spec change** — just correct the misleading "true BFLA" test comment and leave a note for when BFLA corpus pairs are added.
- For paper-grade determinism, consider pinning the `@latest` Go installs and the tool `git clone`s in `containers/Dockerfile` (§2) to fixed versions/commits.

---

## 6. Pre-registration coordination (operator gate — surface it, don't decide it)

`E2-preregistration.md` (in the gitignored `.agents/specs/propose-dispose/specs/propose-dispose-validation/planning/`) is currently **`Status: DRAFT`**. It is the anti-p-hacking gate: E2 outcomes must not be read until it is **LOCKED** with the frozen corpus+harness commit recorded. This is the **operator's sign-off**, not yours — but in your completion report, record the build sha so the operator can lock against it. E1/E3/E4 and the M0 run may proceed before the lock; only reading E2 results is gated.

---

## 7. Definition of Done — attest each before handing back

Mark a spec is deployment-ready only when ALL of these hold (no partial "ready"):

- [ ] PR #18 squash-merged to `main`; merged-tree gate green (`370/4/19`, ruff/format/mypy clean); `main` sha recorded.
- [ ] Full sandbox image (`containers/Dockerfile`) builds **end-to-end with zero skipped layers**; the pinned-toolchain self-check layer passed; `nuclei`/`interactsh-client`/`caido-cli` and the rest verified present.
- [ ] Entrypoint boot smoke test passes (interactsh-client up; "Caido API is ready").
- [ ] Sandbox image tagged deterministically and `runtime.image` reconciled (§3) — the run resolves to *your* image, not ghcr `1.0.0`.
- [ ] B-V2P + business-logic target images build; `VULN_MODE` flip verified on each (vuln vs patch behaves differently); no egress.
- [ ] Corpus decision stated (minimal fixtures vs real upstream commits) in the report.
- [ ] F-3 pyright pinned (or deferred with rationale); F-1 OOB expiry test added (or deferred with rationale); F-4/F-2 addressed or noted.
- [ ] Completion report filed (stub below) with **per-item reproducible evidence** (commands + output / image digests), so the PM can independently re-verify.

---

## 8. Completion report stub (file this to hand back to the PM)

Path: `.agents/specs/propose-dispose/specs/propose-dispose-validation/validation/build-readiness-completion-report.md`. Follow VALIDATION_PROTOCOL.md §C — per-criterion **Claim + Evidence**, no "all done" without evidence (a malformed report is returned unread).

```markdown
# Completion Report — build & deployment readiness

## Header
producer: <interpreter id>
started / completed: <UTC>
main_commit (build input): <sha>

## Artifacts Produced
- strix-sandbox:<tag> (image digest: sha256:...)
- strix-bv2p-idor / strix-bv2p-ssrf / strix-bl-fixture (digests)

## Acceptance Criteria Self-Check   (one block per §7 checkbox)
- Criterion: Full sandbox image builds end-to-end
  - Claim: met
  - Evidence: <build log tail showing nuclei/go/caido layers complete + self-check pass; `docker run ... -version` outputs>
- Criterion: Entrypoint boot smoke test
  - Claim: met
  - Evidence: <docker logs excerpt: interactsh PID + "Caido API is ready">
- Criterion: image-ref reconciled
  - Claim: met
  - Evidence: <settings/env diff; _resolve_sandbox_image() resolves to your tag>
- Criterion: B-V2P VULN_MODE flip
  - Claim: met
  - Evidence: <curl outputs: 2xx on VULN_MODE=1, 403/blocked on 0, both pairs>
- Criterion: merged-tree gate green
  - Claim: met
  - Evidence: <pytest summary 370/4/19; ruff/format/mypy>
- Criterion: F-1 / F-3 (+ F-2/F-4 notes)
  - Claim: met | deferred
  - Evidence: <test name + pass; pinned pyright version; or deferral rationale>

## Known Deviations
<corpus = minimal fixtures vs real upstream; any layer pinned/not pinned; anything deferred>

## Handoff Notes
<host platform/arch the image was built for; registry/tag; how to point the runtime at it; anything the PM needs to reproduce the build before the empirical run>
```

---

## Out of scope (leave to the PM / operator)
- Running E1–E4 and gathering the empirical data (the PM does this after validating your build).
- Locking the E2 pre-registration (operator).
- Adding race/business-logic B-V2P pairs and their experiments (soft-edged, deferred).
- Any change to the disposer or new evidence classes (gate-neutrality invariant — forbidden).
- Exploitation beyond confirmation.

When §7 is fully checked and §8 is filed, hand back to the PM for validation + the empirical run.
