# Validation Upgrade — Adversarial Semantics for Precision-Owning Components

**Purpose.** Close the hole that let the BFLA/expired direction-inversion and the OOB timestamp bug pass a green Locus-1 validation. The hole is named but not closed in `VALIDATION_PROTOCOL.md` §I ("shared blind spot," "validator rubber-stamping") and §H ("test name and result is evidence"): a detection test that asserts the *wrong direction* still passes, so "test passes" confirms the wrong behavior.

**Root cause (corrected).** Lineage distinctness held — the validator (Claude) and producer (Kimi) are different dimensions. The failure was the **validation method**: the distinct validator checked gate-level evidence (tests/types/criteria-met) instead of re-deriving security semantics. The fix is method, not personnel.

**Decision on cross-lineage gating (C).** The standing cross-lineage validator (the PM/auditor interpreter, distinct from the coder) is the adversarial pass — this is built into the upgrade below, not delegated to an external tool. Third-lineage tools (e.g. Greptile) are an opportunistic extra net, read when present, never a required gate.

---

## Amendment 1 — SPEC_FORMAT: two-directional acceptance criteria for precision-owning components

**Scope.** Any component that *flags, detects, confirms, or disposes* — i.e. owns precision. In strix: the differential engine's candidate flagging, the OOB correlator's confirm/quarantine/expire decision, the race verdict, the reachability annotation, any future detector.

**Rule.** A precision-owning component's Acceptance Criteria MUST state **both directions** as separate criteria:

- **True-positive (sensitivity):** the genuine vulnerable/violating case → finding emitted (the right kind, with the right `evidence_class`).
- **True-negative (precision):** the *correct, secure* behavior → **NO finding**. This is the false-positive guard and is mandatory.

A detector spec that specifies only the true-positive direction is **under-specified** and returns to planning. The negative direction is not optional polish — it is where precision lives, and it is the direction that fails silently.

**Worked example (BFLA), as the criteria should read:**
- AC-n (TP): a lower-privilege identity that *succeeds* at an admin-gated endpoint → BFLA candidate emitted.
- AC-n+1 (TN): admin succeeds **and** the lower-privilege identity is correctly denied → **no candidate**. *(This is the case the shipped code gets wrong.)*

**Validator consequence.** If a precision-owning spec lacks a true-negative criterion, the validator records it as `major` (under-specified spec) and the spec returns to planning — the validator does not invent the missing criterion silently.

---

## Amendment 2 — pm-auditor v2.1: adversarial verification of verdict logic

Insert into the `pm-auditor` Process, Phase 2 (Independent Verification), after step 4.

### Step 4-bis — Adversarial re-derivation (precision-owning components only)

For every component that flags/detects/confirms/disposes:

1. **Re-derive the security meaning from first principles**, independent of how the spec or code frames it. State, in the validator's own words: *what is the violation, and what is the correct/secure behavior?* Do not copy the producer's framing — that framing may carry the bug.

2. **Construct the negative case yourself.** Build (or identify) the input where the component **must not** fire — the correctly-secured behavior. Do not rely on the producer's tests for this case.

3. **Trace the actual decision path** against that negative case — read the real branch/predicate that produces the verdict, not just the test result. Confirm the code returns *no finding* on the secure case and *a finding* on the vulnerable case.

4. **Do not accept "the producer's test passes" as confirmation of a detection criterion** unless **both** hold:
   a. a true-negative test exists (secure behavior → no finding), and
   b. the validator confirms each test asserts the **security semantics**, not merely the implementation's current behavior. A test that codifies the implementation's mistake passes; that is not evidence of correctness.

5. Record the finding per criterion as `confirmed` / `refuted` / `unverifiable`, citing the **branch traced** (file+line) and the **negative case constructed**, not just a passing test name.

> Evidence-standard addendum to §H: for a detection/verdict criterion, acceptable evidence is *the traced decision branch plus a true-negative case the validator constructed*. A passing producer test, alone, is **insufficient** evidence for a precision-owning criterion — it cannot distinguish correct logic from a test that encodes inverted logic.

### Self-Check addition (new item 11)

11. **Adversarial direction checked.** For every precision-owning component, the verdict cites a validator-constructed true-negative case and the traced decision branch — not only a passing producer test. The component fires on the vulnerable case and stays silent on the secure case.
    - If No: return to Step 4-bis and construct the negative case before issuing the verdict.

### Failure Mode addition

- **SEMANTIC_RUBBER_STAMP / DIRECTION_INVERSION** — a detection/verdict criterion was confirmed solely on a passing producer test, and the test asserts the implementation's behavior rather than the security semantics (e.g. it expects a finding on a correctly-gated endpoint). Action: refute the criterion, classify `blocker` (false positives/negatives in a precision-owning component), require the test be rewritten to security semantics, and log the drift in `ALIGNMENT_LOG.md` with category `semantic_rubber_stamp`.

---

## Why this is a coherent extension, not a bolt-on
- It closes §I's named "validator rubber-stamping" and "shared blind spot" at Locus 1 instead of deferring entirely to Locus 3 (deployment) — for the one component class (precision-owners) where a silent inversion is catastrophic and cheap to test the other direction.
- It tightens §H's evidence standard exactly where it was too permissive: "test result is evidence" becomes "test result is evidence *only if the test asserts the security semantics*," which a stranger arbiter can still reproduce (construct the negative case, trace the branch).
- It assigns the two halves correctly: the operator owns *what* (negative-direction acceptance criteria, Amendment 1); the validator owns *how* (adversarial re-derivation, Amendment 2). Neither requires a new participant.

## Retroactive application (the current backlog)
The `strix-main-correctness-fix-pass.md` already encodes Amendment 1 implicitly — every fix says "rewrite the test to security semantics, assert no-finding on the secure case." When that fix pass is validated, it is the first run under v2.1: the validator constructs the secure case (correct gating → no BFLA) and traces the branch, rather than re-running the (previously inverted) test.
