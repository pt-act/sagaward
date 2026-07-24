# VALIDATION_PROTOCOL.md — Cross-Interpreter Handshake Rules

The protocol every interpreter follows when producing, validating, or arbitrating work on a spec. `ARCHITECTURE.md` §D names the three validation loci and why they exist; this document defines the mechanics — the artifacts each role writes, the order in which they are written, the rules for disagreement, and the exit conditions that allow a spec to reach `approved`.

**Companion files:** `ARCHITECTURE.md` (the pattern), `AGENTS.md` (behavioral constitution), `PROJECT_MANIFEST.md` (manifest schema), `SPEC_FORMAT.md` (spec contract), `MEMORY_FORMATS.md` (memory bank state).

**When to load:** Any time an interpreter is acting as producer, validator, or arbiter on a spec. The document is small enough to load fully; there is no partial-context mode for validation work.

---

## §A · Purpose

Two problems this protocol exists to solve:

1. **Convergence under uncertainty.** When a producer says "done" and a validator says "not done," the system must reach a decision. It cannot loop forever, and it cannot default to either role's opinion.

2. **Collusion under reasoning.** When producer and validator agree, that agreement is only meaningful if they have not shared a blind spot. The protocol accounts for this directly and does not trust agreement by itself in the post-conflict case.

The protocol is a **file-based handshake**. No runtime coordination. Every step writes a file. Every role reads files written by prior steps. A fresh interpreter dropped into any phase can reconstruct the full state from the artifacts on disk.

---

## §B · Roles and Role Integrity

Four roles participate in validation. Their distinctness is a correctness property, not a convention.

### Producer

The interpreter executing the spec. Writes the implementation artifacts and a **completion report** declaring the work ready for validation.

### Stranger / Validator

An interpreter distinct from the producer. Reads the spec and the producer's artifacts as if they were left there by someone unknown, and issues a **verdict**. Must not share training lineage with the producer where avoidable (see `ARCHITECTURE.md` §E).

### Arbiter

A third interpreter, distinct from both producer and validator. Invoked when the producer and validator disagree and then subsequently converge, or when they deadlock beyond the bounded push-back rounds. Writes an **audit report**. Does not produce new implementation; audits reasoning.

### Operator

The human. Arbitrates only non-technical questions (scope, intent, priority) and captures deployment failures. Not invoked for technical validation disputes unless the arbiter explicitly escalates.

### Role distinctness rules

- **Producer ≠ Validator.** Enforced by the dispatcher (or by the operator when acting as dispatcher). Same-vendor, same-model pairs are rejected. Same-vendor, different-model pairs are allowed but flagged.
- **Arbiter ≠ Producer, Arbiter ≠ Validator.** A third-vendor interpreter is strongly preferred. If only two vendors are available, the arbiter must at minimum be a different model than both prior roles.
- **Role reassignment within a single validation loop is forbidden.** A model cannot "take over" validation after serving as producer on the same spec. The chain is logged in the manifest `execution` block.

---

## §C · Artifact Contracts

Every role communicates by writing a file. The filenames and locations are fixed; validators and arbiters look for them in known paths.

All validation artifacts for a given spec live under:

```
specs/<spec-id>/
├── spec.md                         # the spec itself (with Progress Tracking checkboxes)
├── phase-log.md                    # optional: decisions/deviations per phase (written by producer)
└── validation/
    ├── completion-report.md        # written by producer
    ├── verdict.md                  # written by validator (latest verdict only)
    ├── verdict-history/            # prior verdicts archived here on re-validation
    │   ├── verdict-01.md
    │   └── verdict-02.md
    ├── pushback.md                 # written by producer if contesting a verdict
    ├── pushback-history/
    ├── arbiter-audit.md            # written by arbiter when invoked
    └── resolution-report.md        # final resolution of the spec's validation cycle
```

The `validation/` directory is created by the producer when writing `completion-report.md`. Its presence signals the spec is in the validation phase. On final `approved` status, the directory is frozen (read-only by convention; history preserved).

The `phase-log.md` lives at the spec level (not inside `validation/`) because it's a working document the producer maintains during execution, not a validation artifact. It captures decisions and deviations per phase — not narration.

### Completion report — written by the producer

```markdown
# Completion Report — <spec-id>

## Header
spec_id: <id from manifest>
producer: <interpreter identifier, e.g., claude-sonnet-4.5>
started: <YYYY-MM-DD HH:MM UTC>
completed: <YYYY-MM-DD HH:MM UTC>
spec_version: <version from the spec's header block>

## Artifacts Produced
- <path>: <one-line purpose>
- <path>: <one-line purpose>

## Acceptance Criteria Self-Check
For each criterion in the spec's Acceptance Criteria section:
- Criterion: <verbatim>
  - Claim: met | partially met | not met
  - Evidence: <file path + line range, or command output, or test name>
  - Notes: <only if partially met or not met>

## Interfaces Delivered
For each interface declared in the spec's Interfaces section:
- Name: <from spec>
  - Shape: <delivered shape, verbatim or diff against declared>
  - Location: <file path>
  - Consumer-facing behavior: <one line>

## Known Deviations
Explicit list of any point where the implementation departs from the spec, with reason. Empty list is allowed; missing section is not.

## State Management
Every production run modifies project state beyond the spec's artifacts. This section declares what the producer wrote to the memory bank and manifest. The validator checks these writes mechanically.

### Progress Tracking
The spec's Progress Tracking section contains checkboxes for each phase. The producer checks them off during execution. At completion, declare the state:

- Spec file: `specs/<spec-id>/spec.md`
  - All boxes checked: yes | no
  - If no: which phases are incomplete and why
- Phase log: `specs/<spec-id>/phase-log.md`
  - Exists: yes | no
  - If yes: list phases with entries (decisions/deviations)
  - If no: "All phases straightforward — checkmarks sufficient"

The validator reads the spec file and verifies all boxes are checked. Unchecked boxes with no justification = incomplete spec.

### Memory Bank
For each state file the producer was expected to update:
- File: <path, e.g., `.agents/memory_bank/active/PROGRESS.md`>
  - Action: appended | updated | created | skipped
  - Content summary: <one line — what was written>
  - Rationale if skipped: <why no write was needed — only if action is `skipped`>

Required state writes for every production run:
1. `.agents/memory_bank/active/PROGRESS.md` — appended entry for today's date. The entry text is included in this completion report below (see Progress Entry). The validator reads PROGRESS.md and confirms the entry exists and matches.
2. `.agents/memory_bank/active/current_focus.md` — updated resumption point (MEMORY_FORMATS.md §G).

### Progress Entry
The actual text to be appended to PROGRESS.md for this production run. Focused — no long narratives. References the spec's checkmarks and phase-log for detail:

```markdown
### <YYYY-MM-DD>
- **Implemented:** <spec-id> — <one line: what was built>
- **Decided:** <key decisions, or "none">
- **Blocked:** <what's blocked, or "none">
- **Next:** <next spec or task, with dependency status>
```

Conditional state writes (when applicable):
3. `.agents/memory_bank/active/open_questions.md` — entries for any questions that blocked progress.
4. `.agents/memory_bank/emergent_failures.md` — entries for any deployment-like failures discovered during implementation.
5. `.agents/memory_bank/ARCHITECTURAL_DECISIONS.md` — entries for any non-obvious decisions made.
6. `.agents/memory_bank/MASTER_CONTEXT.md` — update only if the session changed project direction.

**Rule:** A producer that omits the State Management section has written a malformed report. The validator rejects malformed reports without reading the implementation.

## Handoff Notes
Information the validator needs that is not obvious from artifacts alone: e.g., seeded test data, non-obvious file locations, environmental preconditions. Terse.
```

**Rule:** A producer that writes "all criteria met" without per-criterion evidence has written a malformed report. The validator rejects malformed reports without reading the implementation — this is the single highest-leverage check in the protocol. No artifact inspection happens until the completion report is well-formed.

### Verdict — written by the validator

```markdown
# Verdict — <spec-id> — round <N>

## Header
spec_id: <id>
validator: <interpreter identifier>
validator_distinct_from_producer: true | false   # false is a protocol violation; abort
reviewed_completion_report: <path>
verdict_timestamp: <YYYY-MM-DD HH:MM UTC>

## Decision
status: approved | rejected | needs_revision

## Per-Criterion Assessment
For each criterion in the spec's Acceptance Criteria:
- Criterion: <verbatim>
  - Producer's claim: <copy from completion report>
  - Validator's finding: confirmed | refuted | unverifiable
  - Evidence reviewed: <file path + line range, command output run, or test re-executed>
  - Notes: <required when refuted or unverifiable>

## Interface Verification
For each interface declared:
- Name: <from spec>
  - Shape match: exact | compatible | mismatch
  - If mismatch: <what differs>

## Issues Found
Empty if decision is `approved`. Otherwise, an ordered list:
1. Severity: blocker | major | minor
   Location: <file path or conceptual location>
   Description: <what is wrong>
   Suggested remedy: <what should change — optional, advisory>

## Memory Bank Audit
The producer declared state writes in the completion report's State Management section. The validator verifies each declared write actually happened.

For each declared state write:
- File: <path>
  - Declared action: <from completion report>
  - Verified: yes | no | skipped (producer declared skip)
  - Verification method: <file exists, content matches summary, timestamp is post-completion>
  - If no: <what's missing or wrong>

Required checks:
1. `.agents/memory_bank/active/PROGRESS.md` — does it have an entry for today's date with all four fields (Implemented, Decided, Blocked, Next)? Are any fields blank (not `none`, but actually blank)?
2. `.agents/memory_bank/active/current_focus.md` — does it reference the spec that was just completed and name the next resumption point?

If any required write is missing or incomplete:
- Add to Issues Found as `major` severity.
- If the implementation is otherwise correct, the verdict can still be `approved` with a condition: "Memory bank writes must be completed before the next spec is dispatched."
- If the implementation has other issues AND memory bank writes are missing, the verdict is `needs_revision` with both sets of issues listed.

## Verdict Rationale
2–5 sentences. Why the overall decision was reached. References issues above by number.
```

**Decision semantics:**

- **approved** — all criteria confirmed, all interfaces match, zero blocker/major issues. Spec is eligible to flip to `approved` in the manifest.
- **rejected** — structural disagreement with the spec itself, not the implementation. E.g., the spec is ambiguous, contradicts a dependency, or cannot be validated as written. Escalates to the operator (not the producer). Does not trigger a push-back round.
- **needs_revision** — implementation does not satisfy the spec as written. Returns to the producer for another iteration. Triggers the push-back window if the producer contests.

### Push-back — written by the producer

The producer may contest a `needs_revision` verdict exactly once per validator round, under bounded conditions.

```markdown
# Push-back — <spec-id> — round <N>

## Header
spec_id: <id>
producer: <interpreter identifier>
contested_verdict: <path to verdict being contested>
pushback_timestamp: <YYYY-MM-DD HH:MM UTC>

## Contested Issues
For each issue in the verdict the producer contests:
- Issue number (from verdict): <N>
  - Validator's finding: <verbatim>
  - Producer's counter-finding: <what the producer believes to be true>
  - Evidence supporting the counter: <file path + line range, command output, or reference to spec section>
  - Category: factual | interpretive | spec-ambiguity
    - factual — validator's finding is wrong about what the code does
    - interpretive — both readings of the spec are plausible; spec is under-specified on this point
    - spec-ambiguity — the spec itself cannot be satisfied unambiguously; escalates to operator

## Uncontested Issues
List of issue numbers the producer accepts. These will be addressed in the next iteration regardless of the push-back outcome.

## Requested Outcome
- re-validate — ask the validator to reconsider with the new evidence
- escalate — route to the arbiter (only permitted for spec-ambiguity or after two push-back rounds)
```

**Push-back limits:** Two push-backs per spec maximum. A third attempted push-back is routed directly to the arbiter as a deadlock. This is a hard limit — unlimited re-validation loops defeat the purpose of validation.

### Arbiter audit — written by the arbiter

The arbiter is invoked in two cases. Its report format is identical; only the trigger differs.

**Trigger 1 — Post-conflict convergence.** The producer and validator disagreed, then agreed on a revised verdict. The arbiter audits whether the convergence reflects genuine correction or reasoning-based collusion (two interpreters talking themselves into the same wrong answer).

**Trigger 2 — Deadlock.** The bounded push-back window closed without convergence. The arbiter issues the binding verdict.

```markdown
# Arbiter Audit — <spec-id>

## Header
spec_id: <id>
arbiter: <interpreter identifier>
arbiter_distinct_from_producer: true
arbiter_distinct_from_validator: true
trigger: post_conflict_convergence | deadlock
audit_timestamp: <YYYY-MM-DD HH:MM UTC>
reviewed_artifacts:
  - completion-report.md
  - verdict-history/verdict-01.md
  - verdict-history/verdict-02.md
  - pushback-history/pushback-01.md
  - ...

## Independent Finding
The arbiter re-evaluates the spec's Acceptance Criteria against the artifacts **without consulting** the producer's or validator's latest claims. The finding is the arbiter's own.

For each criterion:
- Criterion: <verbatim>
  - Arbiter's finding: met | not met | unverifiable
  - Evidence: <file path + line range, or command output>

## Comparison to Prior Verdicts
- Agreement with final validator verdict: full | partial | none
- Agreement with producer's completion claim: full | partial | none
- Convergence assessment (for trigger=post_conflict_convergence):
  - Genuine correction — the revised verdict reflects a real fix the arbiter also confirms.
  - Drift — both interpreters converged on a view the arbiter does not share. Specify where they diverge from the arbiter's independent reading.
  - Inconclusive — the arbiter cannot tell whether the convergence is genuine. Escalates to operator.

## Binding Decision
status: approved | needs_revision | escalate_to_operator

If `needs_revision`, the arbiter lists the issues in the verdict format of §C. If `escalate_to_operator`, the arbiter states the question the operator must resolve — a question of spec intent, project priority, or resource boundary, not of implementation correctness.

## Rationale
3–6 sentences. The arbiter's reasoning, written to be stranger-readable.
```

The arbiter's decision is binding for technical questions. Operator escalation is reserved for non-technical questions the arbiter cannot resolve by reading artifacts.

### Resolution report — written at cycle close

Once a spec's validation cycle concludes (in any terminal state: `approved`, `escalated`, or `abandoned`), a resolution report summarizes the cycle. This is the handoff artifact downstream specs reference.

```markdown
# Resolution Report — <spec-id>

## Header
spec_id: <id>
final_status: approved | escalated | abandoned
cycle_started: <timestamp>
cycle_closed: <timestamp>
rounds: <number of producer-validator rounds>
arbiter_invoked: true | false

## Participants
- producer: <interpreter>
- validator: <interpreter>
- arbiter: <interpreter or "n/a">

## Outcome Summary
2–4 sentences. What was delivered. What, if anything, deviates from the original spec. Any operator escalations still open.

## Artifact Index
- Final completion report: <path>
- Final verdict: <path>
- Arbiter audit (if any): <path>
- Implementation artifacts: <list of paths>

## Lessons for Future Specs
Any patterns observed during this cycle worth encoding into future specs or into `emergent_failures.md`. Empty list allowed; missing section is not.
```

The resolution report is what the manifest `history` block references. Downstream specs consume the resolution report, not the full validation directory.

---

## §D · The Unit Validation Loop (Locus 1)

Step-by-step flow for validating a single spec. Each step produces a file; each file is the input to the next step.

```
┌─────────────┐
│  Producer   │  writes implementation + completion-report.md
│   round 1   │
└──────┬──────┘
       ▼
┌─────────────┐
│  Validator  │  writes verdict-01.md
│   round 1   │
└──────┬──────┘
       │
       ├── approved ──► resolution-report.md → manifest.status = approved
       │
       ├── rejected ──► operator escalation (spec-level issue, not implementation)
       │
       └── needs_revision
              │
              ├── producer accepts ──► next producer round
              │
              └── producer contests ──► pushback-01.md
                      │
                      ▼
              ┌──────────────┐
              │  Validator   │  re-reviews with new evidence → verdict-02.md
              │  (same one)  │
              └──────┬───────┘
                     │
                     ├── approved or needs_revision accepted ──► continue
                     │
                     └── second contest ──► pushback-02.md ──► arbiter
                                                                  │
                                                                  ▼
                                                          ┌───────────────┐
                                                          │    Arbiter    │  → arbiter-audit.md
                                                          │  (binding)    │
                                                          └───────────────┘
```

### Step-by-step

1. **Dispatch.** The dispatcher (or operator) reads `manifest.yml`, selects a spec whose `depends_on` entries are all `approved`, and assigns a producer interpreter. Assignment is recorded in the spec's manifest `execution.producer` field at this moment — the dispatcher commits a role before any work begins.

2. **Production.** The producer reads `AGENTS.md`, `ARCHITECTURE.md`, `SPEC_FORMAT.md`, the spec itself, dependency resolution reports, and any referenced memory bank files. It produces implementation artifacts, then writes `completion-report.md`. It does **not** signal completion any other way — no status flips, no manifest writes. Writing the completion report is the signal.

3. **Validator dispatch.** The dispatcher (or operator) checks the distinctness constraint and assigns a validator. The validator's identity is recorded in `execution.validator` at dispatch time, not at verdict time.

4. **Validation — round 1.** The validator loads `VALIDATION_PROTOCOL.md` (this file), the spec, and `completion-report.md`. It confirms the report is well-formed; if not, it returns the report to the producer without reading the implementation. If well-formed, it performs the per-criterion assessment and writes `verdict-01.md`.

5. **Verdict dispositions:**
   - `approved` → skip to step 10.
   - `rejected` → skip to operator escalation; spec itself is returned for revision in `planning` status.
   - `needs_revision` → continue to step 6.

6. **Producer response.** The producer reads the verdict. Two choices:
   - Accept the issues → archive the verdict to `verdict-history/`, begin producer round 2 addressing the issues, write a new `completion-report.md`.
   - Contest → write `pushback-01.md` with the structure in §C.

7. **Validator re-review.** On push-back, the validator re-reads the spec, the original artifacts, the contested verdict, and the push-back. Writes `verdict-02.md`. This verdict may converge with the producer (status flips, or severity reduces) or hold firm.

8. **Second contest window.** If the producer still disagrees with `verdict-02`, the producer writes `pushback-02.md`. This is the final permitted push-back. The arbiter is invoked next regardless of what the producer writes.

9. **Arbiter.** The arbiter follows §C's audit format. Its decision is binding.

10. **Resolution.** When the spec reaches a terminal state, a resolution report is written and `manifest.history` gets an entry (see `PROJECT_MANIFEST.md` history block). The spec's `status` field flips accordingly.

### Post-conflict convergence trigger

If the validator and producer disagreed in round 1 (`needs_revision` + contested), and subsequently agreed in round 2 (approved or the producer accepts revised verdict), the **arbiter is invoked anyway** for a convergence audit. This is the single most important rule in the protocol. Two interpreters reasoning together into the same conclusion, post-conflict, is exactly the failure mode the heterogeneous-LLM architecture is designed to catch.

The convergence audit is lighter than a deadlock arbitration — the arbiter is not breaking a tie but sanity-checking an agreement. The output is still binding: if the arbiter flags drift, the spec returns to `needs_revision` regardless of the producer-validator agreement.

**Exception:** Trivial revisions (single-line formatting fixes, whitespace corrections, documentation-only changes explicitly flagged as such in the push-back) do not trigger convergence audit. The producer declares the trivial scope in the push-back header; the validator confirms or rejects the triviality claim in the next verdict. Abuse of this exception — treating substantive changes as trivial — is a push-back-category violation that the arbiter flags on its next invocation.

---

## §E · Integration Validation (Locus 2)

Integration specs go through the same loop as unit specs, with three differences:

1. **Dependencies are completed unit specs.** The integration spec's `depends_on` list references approved unit specs. The producer composes those specs' artifacts; it does not re-implement them.

2. **Acceptance criteria are emergent.** They test properties that hold only when multiple specs compose: interface compatibility, shared-state invariants, concurrency behavior, transactional boundaries. A criterion phrased as "module X is correct" belongs in a unit spec, not an integration spec.

3. **The validator must exercise the composition.** Reading individual unit spec artifacts is not sufficient. The validator runs the composed system (or confirms the producer's composition harness runs correctly) and checks emergent behavior. Verdicts that only reference unit-level artifacts are malformed for integration specs.

No new artifact formats are introduced. The completion report, verdict, push-back, and arbiter audit all use the §C schemas; the content reflects integration-level concerns.

---

## §F · Deployment Feedback (Locus 3)

Deployment validation does not fit the producer-validator-arbiter mold because there is no "next spec" consuming the result — deployment is where the system meets reality. The protocol for deployment feedback is different and lives in `MEMORY_FORMATS.md` under `emergent_failures.md`.

Summary here for completeness:

- The operator (or a monitoring system) observes a failure in the real environment.
- An entry is appended to `emergent_failures.md` with: what failed, which spec pattern was vulnerable, root cause, and the check that would have caught it earlier.
- At the next planning time, the entry becomes an input to spec-architect — the next manifest's specs incorporate checks targeting this failure class.
- The deployment failure is not a validation of a specific spec; it is an input to **future** spec quality.

The feedback loop is eventual, not immediate. Locus 3 does not block a spec's approval — a spec is approved under Locus 1; Locus 3 is where we discover the approval was insufficient.

---

## §G · Shared-State Integrity

The filesystem is the shared medium. Concurrent interpreter execution on the same project is allowed but constrained.

### Manifest mutation rules

The `manifest.yml` file is the one mutable shared object in the project (besides the memory bank). Mutation is serialized by convention:

1. **Only the dispatcher writes the manifest** during execution. Producers, validators, and arbiters never modify `manifest.yml` directly. They write their artifacts into `specs/<id>/validation/`; the dispatcher reads those artifacts and reflects state into the manifest.

2. **Manifest writes are atomic.** The dispatcher reads, computes the new state, writes to `manifest.yml.tmp`, and renames over `manifest.yml`. Partial writes are not permitted.

3. **Each manifest change appends one history entry.** The history block is append-only. Squashing, editing, or deleting history entries is a protocol violation (the manifest becomes no longer audit-trustworthy).

### Spec directory locking

Only one producer works on a given spec at a time. The lock is expressed by the existence of `specs/<id>/validation/` and the spec's `execution.producer` field in the manifest. A dispatcher assigning a second producer to an already-active spec is a protocol violation.

A deadlocked spec (failed arbitration, awaiting operator) does not release its lock. The operator explicitly unlocks by transitioning the spec to `blocked` and, later, back to `planned`.

### Read-only artifacts

Completion reports, verdicts, push-backs, arbiter audits, and resolution reports are **write-once**. They are never edited after being written. A mistake in a verdict is corrected by writing a **new verdict** (the old one moves to `verdict-history/`); it is not edited in place. This preserves the reasoning trail that post-conflict audits depend on.

---

## §H · Verdict Semantics and Evidence Standards

### What counts as evidence

A verdict's per-criterion assessment requires evidence. Acceptable forms:

- **File reference with line range.** `src/auth/jwt.ts:42–67` — the validator confirms the code in those lines implements the behavior claimed. Producer must have named this location; validator confirms or refutes.
- **Command output.** The exact command and its output. `pytest tests/test_jwt.py::test_expiry — PASSED`. The command must be reproducible by the arbiter.
- **Test name and result.** Where a test exists and exercises the criterion, its name and pass/fail status is evidence. Validator may re-run.
- **Interface inspection.** For interface criteria, the declared shape in the spec compared against the delivered shape in code. `produces.token_payload` declared as `{sub: string, exp: number}`, delivered as `{sub: string, exp: number, iat: number}` — compatible extension, noted.

Not acceptable as evidence:

- "I reviewed the code and it looks correct."
- "The tests pass" without naming which tests.
- "The interface matches" without the shape comparison.

The standard is what a stranger arbiter could reproduce from the evidence alone. If the arbiter would need to re-investigate to check the claim, the evidence is insufficient.

### Unverifiable findings

A validator that cannot verify a criterion — because the spec is under-specified, because the producer's claim references unreachable code, or because the test harness does not exist — writes `unverifiable` with a reason. An unverifiable finding is **not** equivalent to `not met`; it is a flag that the validation loop itself is stuck.

Three or more `unverifiable` findings in a single verdict is a protocol condition that routes the spec back to `planning` status with operator notification. The spec is not implementable as written.

---

## §I · Failure Modes of This Protocol

Every layer has its own failure mode, per `ARCHITECTURE.md` §F. This protocol's failure modes:

- **Shared blind spot across all three interpreters.** Three LLMs from three vendors can still miss the same failure class if their training distributions overlap on the blind spot. The architectural answer is not more validators; it is the Locus-3 feedback loop. This protocol cannot catch what all available interpreters cannot see.

- **Push-back exhaustion.** A producer that contests every verdict in bad faith burns rounds until the arbiter fires. This is expensive but bounded: at most two push-backs per spec. Bad-faith push-back patterns are visible in the verdict history and should be surfaced to the operator for interpreter reassignment.

- **Validator rubber-stamping.** A validator that approves without exercising the per-criterion evidence requirement defeats the protocol silently. The protocol has one countermeasure: completion reports are compared against verdicts during the resolution phase; a verdict with no per-criterion evidence can be flagged by the dispatcher or by a sampling audit. This is an operator responsibility.

- **Spec ambiguity masquerading as implementation disagreement.** Producer and validator disagree, but the real issue is the spec is under-specified. The push-back protocol's `spec-ambiguity` category is the escape hatch. A push-back that invokes spec-ambiguity routes directly to the operator; no amount of re-validation will resolve an ambiguous spec.

- **Arbiter drift on convergence audits.** The arbiter may itself share the blind spot of the producer and validator. The protocol's final defense is Locus 3 — deployment. Arbiter drift is discoverable only when the deployed system fails; no machine layer catches it.

Stating these modes explicitly so the commitments of this protocol are auditable: it raises the probability of catching defects, it does not guarantee catching them.

---

## §J · Example: Full Loop Walkthrough

A condensed trace for spec `storage-schema` in the `short-url` project.

```
T+0    Dispatcher selects storage-schema (dependencies: none).
       manifest.yml: storage-schema.status = planned → in_progress
       manifest.yml: storage-schema.execution.producer = claude-sonnet-4.5

T+1    Producer (claude) reads spec, writes:
         - migrations/0001_create_links.sql
         - src/db/schema.ts
         - specs/storage-schema/validation/completion-report.md

T+2    Dispatcher selects validator (different vendor).
       manifest.yml: storage-schema.execution.validator = gpt-5

T+3    Validator (gpt) reads completion report — well-formed.
       Validator reviews per criterion. Finds two issues:
         - Issue 1 (minor): migrations/0001 uses SERIAL, spec declared BIGSERIAL.
         - Issue 2 (blocker): schema.ts omits the 'created_at' column entirely.
       Writes specs/storage-schema/validation/verdict-01.md
       Decision: needs_revision

T+4    Producer reads verdict.
       Accepts Issue 1 (minor type fix).
       Contests Issue 2: the 'created_at' column is in migrations/0001, not in schema.ts
       because schema.ts is hand-written types for application code and the timestamp
       is database-managed. Category: interpretive.
       Writes pushback-01.md. Requests re-validation.

T+5    Validator re-reads the spec's Interfaces section.
       The spec says schema.ts must reflect the table's public shape.
       Database-managed columns are part of the public shape if application
       code reads them. Application code in consumer spec 'url-repository'
       will read created_at.
       Writes verdict-02.md:
         - Issue 1 (minor): unchanged, must fix.
         - Issue 2 (blocker): confirmed — schema.ts must declare created_at.
       Decision: needs_revision.

T+6    Producer accepts both.
       Archives verdict-01 and verdict-02 to verdict-history/.
       Archives pushback-01 to pushback-history/.
       Writes:
         - migrations/0001_create_links.sql (BIGSERIAL fix)
         - src/db/schema.ts (adds created_at)
         - specs/storage-schema/validation/completion-report.md (replaces prior)

T+7    Validator (same gpt-5) re-reviews.
       All criteria met. Writes verdict-03.md. Decision: approved.

T+8    Arbiter check: the cycle included a conflict in T+3 and agreement by T+7.
       Post-conflict convergence → arbiter invoked.
       manifest.yml: storage-schema.execution.arbiter = gemini-2.0

T+9    Arbiter (gemini) reads all artifacts independently.
       Re-evaluates criteria against final artifacts.
       Finding: all criteria met. Convergence assessment: genuine correction —
       both issues were real, the revisions addressed them, no drift.
       Writes arbiter-audit.md. Decision: approved.

T+10   Dispatcher writes resolution-report.md.
       manifest.yml: storage-schema.status = in_review → approved
       manifest.history appends: {date, event: spec_approved, spec: storage-schema,
                                  rounds: 2, arbiter: gemini-2.0, outcome: approved}

T+11   Downstream specs (url-repository, id-generator) become dispatchable.
```

The trace is verbose here for illustration; in the actual manifest, each step produces a single file and a single manifest mutation. The reasoning trail is on disk and stranger-readable.

---

## §K · Protocol Commitments

The design choices in this protocol, stated so they are auditable:

1. **File-based handshake.** No runtime messaging. Every role communicates by writing a file.

2. **Write-once artifacts.** Reports, verdicts, push-backs, and audits are never edited after being written. History is preserved.

3. **Bounded push-back.** Two rounds maximum. Unlimited contest loops defeat validation.

4. **Post-conflict arbitration by default.** Any spec that went through a conflict-then-agreement path gets a third-interpreter audit before approval. Agreement is not trusted in that case.

5. **Deadlock escalation to arbiter, not operator.** Technical disputes resolve at the arbiter layer. The operator is invoked for intent and scope questions only.

6. **Evidence standard: reproducible by a stranger.** Verdicts without reproducible evidence are malformed.

7. **Role distinctness is a correctness property.** Same-model producer/validator pairs are rejected by the dispatcher. Distinctness of the arbiter from both prior roles is mandatory.

If a future extension violates any of these, it is not an extension of this protocol — it is a different protocol.

---

*End of VALIDATION_PROTOCOL.md v1.0*