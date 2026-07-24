# Open Questions

> AI → Human. Answered questions are removed and their resolutions recorded in PROGRESS.md / ARCHITECTURAL_DECISIONS.md. Reconciled 2026-06-18; updated 2026-06-21 with S0-v2 pivot; updated 2026-06-21 with Part A funnel-completeness decision.

## 2026-06-21 · Funnel completeness for direct-filing disposers — operator decision required before E1
- **Context:** Part A vuln-side IDOR confirmed (evidence_class=diff), but `Funnel.json = []` because the agent used `auth_matrix` directly without calling `propose_vulnerability_investigation` first. Both funnel linkage paths (`_link_disposer_verdict_to_funnel`, `record_harness_run`) no-op without a pre-existing `ProposalRecord`. This is mechanically correct but E1-fatal: E1 measures Prec_gate/R_prop off ProposalRecords, and confirmed findings bypassing the proposal stage produce no funnel data.
- **Question:** Which approach to funnel completeness for direct-filing disposers (auth_matrix, and audit the others)?
- **Proposed options:**
  - **(i) Prompt/orchestration discipline** — drive the agent through `propose_vulnerability_investigation` before any disposer. Light, but soft (relies on agent compliance).
  - **(ii) Structural auto-registration** — direct-filing disposers auto-register a `ProposalRecord` when none matches, so every confirmed finding is funnel-complete by construction. Matches the paper's structural enforcement ethos, but revises an approved spec (loopback required); must stay gate-neutral (no new evidence_class, no disposition alteration).
  - **(iii) E1-by-construction protocol** — define E1's run protocol so the agent always proposes first; leave free-form scans as-is.
- **Impact:** E1 is entirely funnel-driven; unfixed = incomplete population or empty funnel for confirmed true-positives. PM leans toward (ii) — "the paper claims structural enforcement of the doctrine, and funnel completeness should be structural too, not prompt-dependent" — but it's an operator call since it revises an approved spec.
- **PM ruling:** finish the patch-side flip first, then address this as a formal decision with patch-side evidence in hand.

## 2026-06-21 · S0-v2 containment live-proof — when to schedule?
- **Context:** The PM's operator decision: no unattended/real-target runs until S0-v2 containment is live-proven. The coder-handoff sets the order (Part A bring-up → Part B egress gateway → live proof). The paper (E1–E4) can run on the dev image with enforcement off, but the operator said "containment must be live-proven before any paper/empirical/real-target run."
- **Question:** Does E1–E4 on the dev image (enforcement off, owned targets) proceed independently of the S0-v2 proof, or does the operator want to hold everything until S0-v2 passes? The PM says it does NOT gate the paper, but the handoff says "no data-collection runs until S0-v2 is proven" — clarify which interpretation holds.
- **Impact:** If E1–E4 can proceed on dev, the paper timeline is independent. If everything holds, the paper waits for Part A + Part B + live proof.

## 2026-06-21 · S3.1 poller→breaker wiring test — follow-up priority?
- **Context:** Verdict-11 flagged (non-blocking) that there's no direct test of the new feed path (poller → breaker; repeat_request 5xx/429 → breaker). The breaker unit tests pass but the S3.1 wiring is untested. PM recommended a focused test in a follow-up.
- **Question:** Is this a priority follow-up (before Part B), or does it defer until after S0-v2?
- **Impact:** A focused test would close the S3.1 validation gap before the gateway reuses target-health data. But Part A bring-up is more urgent.

## 2026-06-14 · TUI mypy debt (deferred — decision, not a blocker)
- **Context:** ~69 pre-existing `mypy --strict` errors in `strix/interface/tui/` (pygments import-untyped, missing generics, override issues, stale `type: ignore`). They predate Phase 0 and are unrelated to feature work.
- **Decision:** Burn down in a dedicated pass — ideally when the TUI is next modified — not inside a feature phase; TUI type changes risk rendering regressions.
- **Impact:** The standing gate definition is `mypy --strict` clean on the files a change touches (changed-files run), not whole-package. Whole-repo mypy clean is a separate, later milestone. Carried here as a known, accepted debt item until the operator schedules the pass.

## 2026-06-17 · Spec B harness-wiring approach — ✅ RESOLVED
- **Resolution:** Option 3 (centralized factory wrapper) chosen by operator, implemented in `strix/agents/funnel_emit.py`, merged via PR #18 (`cdcc75e`). Gate green (350→370 passed across Spec B milestones). `_link_disposer_verdict_to_funnel` demoted to link-only; wrapper is the sole per-run recorder.
- **Recorded in:** ARCH #9, PROGRESS.md 2026-06-18 entry.
