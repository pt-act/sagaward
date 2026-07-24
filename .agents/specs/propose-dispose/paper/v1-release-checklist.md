# v1 Release & Reproducibility Checklist (H1 preprint + open code/data)

> For the coordinated open release of **Propose–Dispose v1** (H1 result + the artifacts that
> let anyone re-run it). Built around the project's own glass-box principle: ship the data, not
> just the claim. Owner: operator/PM. Gate order matters — do not publish until the pre-release
> gates pass.

---

## A. Pre-release gates (all must pass before the repo goes public / the preprint posts)

- [ ] **HOLD LINE passed.** SGL-Core Gate 5 green, so v1 describes the *hardened* engine
      (0 bypass / 0 out-of-scope / 0 destructive; gate-neutrality confirmed). No public release of
      a known-incomplete egress enforcer.
- [ ] **⭐ Upstream security sweep #1 (the detach-safety gate).** One-time check of the upstream
      base before going public — *security/dependency fixes only, not features*:
      ```bash
      git fetch upstream            # keep the upstream remote wired up; don't track day-to-day
      git log --oneline <fork-point>..upstream/main
      ```
      Cherry-pick only genuine **security/CVE/sandbox/proxy/dependency** fixes in code you still
      share. Ignore feature work. Grab the `ollama_chat` routing fix **only if** you use local/
      Ollama models. Record what was reviewed + picked (or "nothing security-relevant") in the
      release notes. *(Today: 1 upstream commit, provider-routing — nothing to pick.)*
- [ ] **Pre-registration intact (no-peek).** Either E2 is **LOCKED** with the frozen corpus+harness
      sha recorded, or E2 results have **not been read inferentially**. v1 may contain E2 only as
      clearly-labeled *descriptive* preview, or omit it. The pre-registered McNemar stays for v2.
- [ ] **Full gate green** on the release commit (pytest / ruff / format / mypy / bandit; pyright
      pinned per F-3) and the commit sha recorded.

## B. Reproducibility package (ships *with* v1 — this is the whole point)

- [ ] **Pinned sandbox image**, tagged deterministically (`strix-sandbox:<release-sha>`), digest
      recorded; `runtime.image` documented (not ghcr `1.0.0`).
- [ ] **B-V2P corpus + harness** published: `benchmarks/bv2p/` fixtures + `strix/research/corpus.py`
      (the two M0 seeds, ground-truth labels, `power_check`).
- [ ] **The exact funnel artifacts behind every reported number** (the `funnel.json`(s) the figure
      and tables are computed from) — so a reader reproduces the plot, not trusts it.
- [ ] **Metrics + run code**: `strix/research/metrics.py` (read-only), the E1 sweep runner, the M4
      single-stage baseline, with the **exact commands** to regenerate the H1 figure + M0 table.
- [ ] **Determinism note**: seeds, model ids/versions, any non-determinism (LLM sampling) called
      out, with the run config that produced the published numbers.
- [ ] **One-command repro path** ("clone → build → run → regenerate Figure 1") in a `REPRODUCE.md`.

## C. Claim discipline (so community reproduction *builds* credibility)

- [ ] v1 claims **H1 only** (`Prec_gate` invariance as recall is pushed) + the M0 flip demos.
- [ ] **Limitations stated plainly**: H2a (gap-stratified McNemar) is pre-registered and
      forthcoming; corpus underpowered; recall-over-known + unknown-unknown caveat; C1–C8 is an
      LLM-as-judge artifact; small n / two primitives.
- [ ] No number in the paper lacks a traceable funnel artifact (claim→artifact pass).

## D. Corpus packaging for community contribution (feeds v2 power)

- [ ] Document the **B-V2P pair format** + a `CONTRIBUTING-corpus.md`: how to add a vuln/patch
      pair (minimal-diff, dockerized, ground-truth label, which disposer confirms it) and the
      check that the disposer flips across the pair. Goal: the community grows the small-gap
      corpus that powers v2's McNemar faster than you can alone.

## E. Legal / safety framing (responsible open release of a security tool)

- [ ] `LICENSE` (Apache-2.0) + `NOTICE` present; upstream attribution intact; `CHANGELOG.md`
      states the divergence.
- [ ] **Responsible-security framing visible**: the released B-V2P pairs target *already-public,
      patched* CVEs (open-webui CVE-2024-7041, Flowise CVE-2026-31829); the engine is fail-closed
      / authorized-scope-only post-SGL. The release reads as *measurement artifacts + a hardened,
      governed tool*, not weaponization.

## F. Release action + post-release

- [x] **Paper v1.0 camera-ready draft written** (`propose-dispose-paper-v1.0.md`, 2026-07-24).
      All experimental results (M0, E1–E4) incorporated verbatim. 12 sections + appendices.
      Primary result (H2a, χ²=8.100, p≈0.0044) and honest FN-arm limit prominently stated.
- [ ] Post **arXiv v1** (or chosen preprint host); link the repo release tag from the paper and
      vice-versa.
- [ ] Announce with the "verify, don't trust — here's the button" framing.
- [ ] **Bounty hunts can start now, in parallel** (gated by the HOLD LINE, not the paper).
- [ ] **⭐ Upstream security sweep #2** before the *first real bounty hunt* (same one-time
      security-only check as A.2 — the second and final scheduled look at upstream).
- [ ] Begin accumulating B-V2P pairs *from the hunts* toward the v2 powered corpus.

---

### Notes
- The two ⭐ upstream sweeps are the *only* remaining ties to the fork's origin: security-only,
  twice (pre-release, pre-hunt). Otherwise the project is detached from upstream.
- v2 (the pre-registered H2 study) is a later arXiv version or a full venue paper — it *adds* to
  v1 and retracts nothing.
