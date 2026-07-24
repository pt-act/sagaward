---
name: pm-auditor
version: 2.0.0
role: validator
description: |
  Locus-1 validator. Reads a producer's completion report and implementation
  artifacts against a spec's acceptance criteria, then issues a verdict
  per VALIDATION_PROTOCOL.md. Must be a different interpreter than the producer.

  USE WHEN: a completion report exists at specs/<id>/validation/completion-report.md
  and no verdict exists yet for the current validation round.
loads:
  - AGENTS.md
  - ARCHITECTURE.md
  - VALIDATION_PROTOCOL.md
  - SPEC_FORMAT.md
  - PROJECT_MANIFEST.md
produces:
  - path: specs/<spec-id>/validation/verdict.md
    format: markdown
    purpose: validator's decision on the producer's work
  - path: specs/<spec-id>/validation/verdict-history/verdict-<N>.md
    format: markdown
    purpose: archived prior verdicts on re-validation rounds
consumes:
  - path: specs/<spec-id>/spec.md
    optional: false
  - path: specs/<spec-id>/validation/completion-report.md
    optional: false
  - path: manifest.yml
    optional: false
  - path: specs/<dep-id>/validation/resolution-report.md
    optional: true
compatible_interpreters:
  - any
distinctness_requirements:
  producer_must_differ_from:
    - <producer interpreter id — checked at dispatch time>
supersedes: pm-auditor (legacy v1.x)
---

# pm-auditor

## Purpose

Validate a producer's work against a spec's acceptance criteria. Issue a verdict that is stranger-readable, evidence-based, and mechanically reproducible. This is the Locus-1 mechanism from ARCHITECTURE.md §D — the first line of defense against execution drift.

## Role

validator

## When to Run

- A completion report exists at `specs/<id>/validation/completion-report.md`.
- No verdict exists yet for the current validation round (no `verdict.md`, or the dispatcher is initiating a re-validation).
- The dispatcher has confirmed the validator is distinct from the producer per VALIDATION_PROTOCOL.md §B.

## Inputs

- `specs/<spec-id>/spec.md` — the spec being validated. This is the ground truth.
- `specs/<spec-id>/validation/completion-report.md` — the producer's self-check and evidence claims.
- `manifest.yml` — to confirm spec status, dependency status, and execution metadata.
- `specs/<dep-id>/validation/resolution-report.md` — one per dependency (optional). Used to verify the producer correctly consumed upstream interfaces.
- `.agents/memory_bank/ARCHITECTURAL_DECISIONS.md` — binding decisions that may constrain interpretation.

## Outputs

- `specs/<spec-id>/validation/verdict.md` (or `verdict-<N>.md` for re-validation rounds).
- `.agents/memory_bank/active/PROGRESS.md` — appended entry for the validation session.
- `.agents/memory_bank/ALIGNMENT_LOG.md` — entry if drift is observed during validation.

## Process

### Phase 1: Report Well-Formedness Check

1. Load and parse the completion report. Verify it contains all required sections per VALIDATION_PROTOCOL.md §C:

   a. Header (spec_id, producer, started, completed, spec_version).
   b. Artifacts Produced (list of paths).
   c. Acceptance Criteria Self-Check (per-criterion with Claim + Evidence).
   d. Interfaces Delivered (per-interface with Shape + Location).
   e. Known Deviations (explicit list, may be empty).
   f. Handoff Notes.

2. If the report is malformed (missing sections, per-criterion evidence absent, "all criteria met" without individual evidence):

   a. **Do not read the implementation artifacts.** Malformed reports are returned without validation.
   b. Write a verdict with `status: needs_revision` and a single issue: "Completion report is malformed — [specific deficiency]. Producer must rewrite the completion report before validation proceeds."
   c. Proceed to Phase 4 (Write Verdict).

### Phase 2: Independent Verification

3. Load the spec. Extract the Acceptance Criteria into a numbered list. This list is the ground truth — the producer's claims are checked against it, not against the producer's own summary.

4. For each acceptance criterion:

   a. Read the producer's claim and evidence from the completion report.
   b. **Independently verify.** Do not trust the producer's evidence summary. Reproduce the check:
      - If the verifier is a command: run it. Capture output.
      - If the verifier is a file inspection: read the file. Confirm the content.
      - If the verifier is a test: run it. Confirm pass/fail.
      - If the verifier is an interface shape comparison: read the declared shape in the spec and the delivered shape in the artifact. Compare.
   c. Record the finding: `confirmed`, `refuted`, or `unverifiable`.
      - `confirmed` — the evidence supports the claim and the verifier passes.
      - `refuted` — the evidence does not support the claim, or the verifier fails. Note what differs.
      - `unverifiable` — the criterion cannot be checked because the spec is under-specified, the referenced artifact is missing, or the verifier is not mechanical. Note why.

5. For each interface declared in the spec's Interfaces section:

   a. Read the declared shape, location, and invariants.
   b. Read the delivered artifact at the declared location.
   c. Compare shape: `exact` (identical), `compatible` (superset or equivalent), or `mismatch` (missing fields, wrong types, broken invariants).
   d. Record the finding.

6. Check for undeclared artifacts. If the producer wrote files not listed in the completion report's Artifacts Produced section, note them. Undeclared artifacts are not automatically issues but may indicate scope creep.

7. Check for missing artifacts. If the spec's Interfaces section declares a produced interface but no artifact exists at the declared location, this is a `blocker` issue.

8. **Progress tracking verification.** Read the spec file (`specs/<spec-id>/spec.md`) and check the Progress Tracking section:

   a. **Checkmarks** — are all phase boxes checked (`- [x]`)? If any are unchecked, check the completion report's State Management section for justification. Unchecked boxes with no justification = `major` issue (incomplete work).
   b. **Phase-log** — if the completion report declares a phase-log exists, read `specs/<spec-id>/phase-log.md`. Confirm it exists and contains entries for the phases with decisions/deviations. If declared but missing = `major` issue.
   c. **Progress entry** — read the Progress Entry text in the completion report's State Management section. Confirm it's focused (no long narratives), has all four fields (Implemented, Decided, Blocked, Next), and the "Implemented" line matches the spec that was just completed.

9. **Memory bank audit.** Read the State Management section of the completion report. Verify each declared write:

   a. **PROGRESS.md** — read `.agents/memory_bank/active/PROGRESS.md`. Confirm there is an entry for today's date. Confirm all four fields are present (Implemented, Decided, Blocked, Next). Confirm no fields are blank (empty string — `none` is acceptable, blank is not). If the entry is missing or incomplete, this is a `major` issue.

   b. **current_focus.md** — read `.agents/memory_bank/active/current_focus.md`. Confirm it references the spec that was just completed and names a specific resumption point (next file + task). If it's stale (still references the previous session's work), this is a `major` issue.

   c. **Conditional writes** — if the producer declared writes to `open_questions.md`, `emergent_failures.md`, `ARCHITECTURAL_DECISIONS.md`, or `MASTER_CONTEXT.md`, verify each exists and matches the declared content summary. If a declared write doesn't exist, this is a `major` issue.

   d. **Skipped writes** — if the producer declared `skipped` for any conditional write, confirm the rationale is plausible. Skipping PROGRESS.md or current_focus.md is never acceptable — these are always required.

   e. Record all memory bank findings. Memory bank issues are classified as `major` (not `blocker`) because they don't affect the spec's technical correctness — they affect the system's continuity. However, if the implementation has other `blocker`/`major` issues AND memory bank writes are missing, the verdict is `needs_revision` with both sets of issues.

### Phase 3: Issue Classification

10. Classify each finding into severity:

   a. **blocker** — prevents the spec from being usable by downstream consumers. Missing interfaces, broken invariants, failing tests, data corruption risks.
   b. **major** — significant deviation from the spec that does not block all consumers but degrades quality or violates acceptance criteria. Incomplete memory bank writes and unchecked progress boxes are classified as `major`.
   c. **minor** — cosmetic, documentation, or formatting issues that do not affect functionality.

11. Determine the overall decision:

    a. **approved** — all criteria `confirmed`, all interfaces `exact` or `compatible`, all progress boxes checked, zero blocker/major issues.
    b. **needs_revision** — one or more criteria `refuted` with blocker/major severity, or interfaces `mismatch`, or unchecked progress boxes without justification. Returns to producer.
    c. **rejected** — structural disagreement with the spec itself (not the implementation). The spec is ambiguous, contradicts a dependency, or cannot be validated as written. Escalates to operator, not producer.

12. Count `unverifiable` findings. If three or more:

    a. Decision is `needs_revision` with a note: "Spec is not implementable as written — N criteria are unverifiable. Spec must return to planning."
    b. This triggers a spec-level revision, not just an implementation revision.

### Phase 4: Write Verdict

12. Write `specs/<spec-id>/validation/verdict.md` (or `verdict-<N>.md` if re-validation) per VALIDATION_PROTOCOL.md §C format:

    a. Header with spec_id, validator identifier, `validator_distinct_from_producer: true`, path to completion report, timestamp.
    b. Decision: `approved`, `rejected`, or `needs_revision`.
    c. Per-Criterion Assessment — for each criterion: producer's claim (copied), validator's finding, evidence reviewed, notes (required for refuted/unverifiable).
    d. Interface Verification — for each interface: shape match status.
    e. Progress Tracking Audit — all boxes checked, phase-log verified, progress entry matches.
    f. Issues Found — ordered list with severity, location, description, suggested remedy.
    g. Memory Bank Audit — per declared state write: verified status, issues found.
    h. Verdict Rationale — 2–5 sentences.

13. If this is a re-validation round, archive the prior verdict to `verdict-history/verdict-<N>.md` before writing the new one.

### Phase 5: Post-Verdict

14. If decision is `approved`:

    a. The spec is eligible to flip to `approved` in the manifest (dispatcher action).
    b. Check if this cycle had prior conflict (verdict-history has entries with `needs_revision`). If yes, the arbiter must be invoked for a convergence audit per VALIDATION_PROTOCOL.md §D step 9. Note this in the verdict's Rationale.

15. If decision is `needs_revision`:

    a. The producer will read the verdict and decide to accept or push back.
    b. The validator does nothing further until re-invoked.

16. If decision is `rejected`:

    a. Escalate to the operator. The spec itself is the problem.
    b. Write an entry to `.agents/memory_bank/active/open_questions.md` with the rejection reason.

17. Append a validation entry to `.agents/memory_bank/active/PROGRESS.md`.

## Self-Check

Before writing the verdict, confirm each of the following. If any answer is No, apply the indicated Fix Action. After three full passes with any check still failing, write the verdict with explicit TODOs on the failing checks.

1. **Per-criterion verification complete.** Every criterion in the spec's Acceptance Criteria section has a corresponding entry in the verdict's Per-Criterion Assessment with a finding of `confirmed`, `refuted`, or `unverifiable`.
   - If No: return to Phase 2 and verify the missing criteria.

2. **Evidence is reproducible.** Every `confirmed` or `refuted` finding cites a specific file+line range, command output, or test result that a stranger arbiter could reproduce.
   - If No: replace vague evidence ("looks correct") with specific references.

3. **Interface verification complete.** Every interface in the spec's Interfaces/Produces section has a corresponding entry in Interface Verification.
   - If No: return to Phase 2 step 5.

4. **Distinctness confirmed.** The Header's `validator_distinct_from_producer` field is `true`. If the validator is the same interpreter as the producer, abort — this is a protocol violation.
   - If No: abort and escalate to dispatcher.

5. **Decision matches findings.** If all criteria are `confirmed` and all interfaces match, decision must be `approved`. If any blocker/major issue exists, decision must not be `approved`.
   - If No: correct the decision.

6. **Issues are classified.** Every issue in the Issues Found section has a severity (blocker/major/minor) and a specific location.
   - If No: add the missing classifications.

7. **Progress tracking verified.** All spec checkmarks are checked (or justified), phase-log exists if declared, progress entry is focused with all four fields.
   - If No: add the missing verification to the Progress Tracking Audit section.

8. **Memory bank audit complete.** Every declared state write in the completion report's State Management section has a corresponding entry in the verdict's Memory Bank Audit section. PROGRESS.md and current_focus.md were verified as required writes.
   - If No: complete the memory bank audit before writing the verdict.

9. **Unverifiable threshold checked.** If three or more criteria are `unverifiable`, the verdict notes that the spec must return to planning.
   - If No: add the note.

10. **Session manifest complete.** Every field in the Session Manifest section is populated with specific values, not placeholders.
    - If No: populate the missing fields before closing.

## Failure Modes

- **MALFORMED_REPORT** — Completion report is missing required sections or lacks per-criterion evidence. Action: return the report without reading implementation; verdict is `needs_revision` with a single issue about report quality.

- **SPEC_AMBIGUITY** — The spec allows multiple valid interpretations, and the producer's interpretation differs from the validator's. Action: classify as `spec-ambiguity`; verdict is `needs_revision` noting the ambiguity. If the producer pushes back with `spec-ambiguity` category, it routes to the operator per VALIDATION_PROTOCOL.md §C.

- **MISSING_ARTIFACT** — The producer claims an artifact exists at a path, but it doesn't. Action: classify as `blocker`; verdict is `needs_revision`.

- **MISSING_MEMORY_BANK_WRITES** — PROGRESS.md or current_focus.md were not updated, or declared writes don't exist. Action: classify as `major`; add to Issues Found. If implementation is otherwise correct, verdict can be `approved` with a condition that memory bank writes must be completed before the next spec is dispatched.

- **UNVERIFIABLE_THRESHOLD** — Three or more criteria cannot be verified. Action: verdict notes the spec must return to planning; decision is `needs_revision`.

- **SELF_CHECK_EXHAUSTED** — Three self-check passes with failures. Action: write the verdict with explicit TODOs on failing checks; append an `open_questions.md` entry.

- **DRIFT_OBSERVED** — The validator notices itself rubber-stamping (approving without real verification) or being overly obstructionist. Action: log the drift in `.agents/memory_bank/ALIGNMENT_LOG.md` with category `validation_shortcut` or appropriate category.

## Session Manifest

```markdown
## Session Manifest
- Skill: pm-auditor@2.0.0
- Interpreter: <interpreter identifier>
- Role: validator
- Spec: <spec-id>
- Validation round: <N>
- Documents loaded: <list>
- Files read: <list>
- Criteria verified: <count> confirmed, <count> refuted, <count> unverifiable
- Interfaces verified: <count> exact, <count> compatible, <count> mismatch
- Decision: <approved | needs_revision | rejected>
- Prior conflict: <yes — arbiter convergence audit required | no>
- Self-check result: <passed on iteration N | partial with TODOs>
- Drift observed: <yes — see ALIGNMENT_LOG.md | no>
- Escalations raised: <list or "none">
```
