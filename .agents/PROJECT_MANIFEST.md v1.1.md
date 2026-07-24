# PROJECT_MANIFEST.md — Manifest Schema

The project manifest is the DAG of specs that constitutes a project. It is the single source of truth for what the project is, what has been decided, what has been done, and what remains. Every interpreter operating on the project reads the manifest; every state change is reflected in the manifest.

The manifest and specs together are the program being executed. System reliability is bounded below by their quality. Invest conceptualization effort here; every downstream mechanism amplifies whatever the manifest encodes.

**File:** `manifest.yml` at project root.

---

## §A · What the Manifest Is

A machine-readable declaration of:

- **Project identity** — name, objective, status, role assignments.
- **The DAG** — every spec, its dependencies, its interface contracts.
- **Execution state** — which specs are planned, in-progress, under review, approved, blocked.
- **Audit trail** — append-only history of manifest changes.

It is **not**:

- A narrative project description (belongs in `README.md` or the human-facing diary)
- A detailed task list (belongs in individual spec files)
- A changelog for implementation (belongs in memory bank)

The manifest is the **index**; specs are the **chapters**; the memory bank is the **diary**.

---

## §B · File Format

YAML at `manifest.yml` in the project root. Human-editable, machine-parseable, git-diffable.

Top-level structure:

```yaml
project: {...}           # project identity
specs: [...]             # the DAG — array of spec entries
milestones: [...]        # optional groupings of specs
history: [...]           # append-only audit trail
```

### Project block

```yaml
project:
  name: <kebab-case identifier>
  objective: <one-sentence goal — what success looks like>
  created: <YYYY-MM-DD>
  status: planning | executing | paused | complete
  operator: <identifier of human or system>
```

### Spec entry

Every node in the DAG is a spec entry:

```yaml
- id: <kebab-case unique identifier>
  title: <human-readable title>
  type: unit | integration
  status: planned | in_progress | in_review | approved | blocked
  file: specs/<id>/spec.md
  depends_on: [<list of spec ids this spec requires>]
  produces:
    - name: <interface name>
      shape: <brief type/format description>
      consumers: [<list of spec ids that consume this>]
  consumes:
    - name: <interface name>
      from: <spec id that produces this>
```

The `produces` and `consumes` blocks are **interface summaries**. Full interface contracts live in the spec file itself (per `SPEC_FORMAT.md`). The manifest-level summary exists so the DAG can be traversed without reading every spec.

### Status values

- `planned` — defined in the manifest but not yet executed
- `in_progress` — producer is currently executing
- `in_review` — producer claims complete; validator running
- `approved` — validator passed; spec is locked, downstream specs may dispatch
- `blocked` — execution halted; `blocked_by` field explains why

Transitions are monotonic except `approved → in_progress` (only via explicit loopback event) and `blocked → planned/in_progress` (when blocker is resolved).

### Milestone block (optional)

```yaml
milestones:
  - name: <kebab-case>
    specs: [<list of spec ids>]
    status: not_started | in_progress | complete
```

Milestones group specs for reporting and deployment boundaries. They do not affect execution order — the DAG alone determines that.

### History block

Append-only. Every manifest write adds an entry. Never edit or delete existing entries.

```yaml
history:
  - timestamp: <ISO 8601>
    event: <spec_added | spec_started | spec_produced | spec_approved | spec_blocked | spec_loopback | spec_pushback | spec_arbitrated | manifest_locked | milestone_reached | ...>
    ref: <spec id or milestone name>
    by: <interpreter identifier or operator>
    note: <optional short context>
```

The history is the audit trail. Validators use it to verify provenance claims. Operators use it to reconstruct what happened.

---

## §C · DAG Invariants

A well-formed manifest satisfies:

1. **Unique ids.** Every spec has a unique `id`. No collisions.
2. **Acyclic dependencies.** `depends_on` edges form a DAG (no cycles).
3. **Interface closure.** Every entry in a spec's `consumes` references a spec that exists in the manifest AND has that interface in its `produces`.
4. **Integration coverage.** Every integration spec's `depends_on` includes at least two unit specs.
5. **Status consistency.** A spec's status cannot be `in_progress` or `approved` if any of its `depends_on` specs are not `approved`.
6. **History monotonicity.** Timestamps in the history block are non-decreasing.

Validation of these invariants should be automatic. A dispatcher (or a manifest-lint program) runs these checks on every manifest read. Any violation blocks dispatch until fixed.

---

## §D · Planning-Time Workflow

How a manifest is produced:

1. **Operator states objective.** One sentence, concrete, outcome-shaped.
2. **spec-architect decomposes.** With the operator, produces the initial DAG — unit specs for distinct components, integration specs for non-trivial compositions.
3. **Interfaces declared.** Every edge in the DAG corresponds to a `produces`/`consumes` pair. No magic glue.
4. **Acceptance criteria written.** Per spec, in the spec file (per `SPEC_FORMAT.md`). Summary only in manifest if needed.
5. **Invariants checked.** Automatic lint before the manifest is considered complete.
6. **Operator review.** Final conceptualization gate. Operator verifies the decomposition matches intent.
7. **Manifest locked.** Project status flips from `planning` to `executing`. History event `manifest_locked`. From this point, spec changes require explicit history entries.

Changes to the manifest after locking are legitimate but must be tracked:

- **Adding a spec** — new entry, status `planned`, history event `spec_added`.
- **Modifying a spec's acceptance criteria** — history event `spec_revised` with reason; if the spec was already `approved`, status flips to `planned` (loopback cascades to dependent specs).
- **Removing a spec** — history event `spec_removed`; downstream specs must be revised or removed before execution can resume.

---

## §E · Execution-Time Workflow

How the manifest evolves during execution:

1. **Dispatcher reads manifest.** Identifies specs whose `depends_on` are all `approved` and whose status is `planned`.
2. **Dispatches producer.** Producer interpreter is invoked with the spec as input. Status → `in_progress`. History event `spec_started`.
3. **Producer completes.** Artifacts written. Status → `in_review`. History event `spec_produced`.
4. **Dispatches validator.** A different interpreter reads artifacts, checks acceptance criteria, issues verdict per `VALIDATION_PROTOCOL.md`.
5. **Verdict processed:**
   - `APPROVE` → status → `approved`. History event `spec_approved`. Downstream specs may now dispatch.
   - `REQUEST-CHANGES` → status → `in_progress`. History event `spec_loopback`. Producer re-runs with validator's findings as context.
   - `BLOCKED` → status → `blocked`. History event `spec_blocked`. `blocked_by` populated. Operator notified.
History events `spec_pushback`, `spec_arbitrated`.
6. **Loop until all specs approved.** Project status → `complete`.

---

## §F · Worked Example

Minimal project: a URL shortener with link analytics.

```yaml
project:
  name: short-url
  objective: >
    Accept long URLs and return short codes; accept short codes and redirect to
    the original URL; track click counts per short code.
  created: 2026-01-15
  status: executing
  operator: human:operator-001

specs:
  - id: storage-schema
    title: URL storage schema
    type: unit
    status: approved
    file: specs/storage-schema/spec.md
    depends_on: []
    produces:
      - name: url_table
        shape: "table{short_code: string pk, long_url: string, created_at: timestamp}"
        consumers: [shortening-api, redirect-service, analytics-api]
      - name: click_log_table
        shape: "table{id: int pk, short_code: string fk→url_table, clicked_at: timestamp}"
        consumers: [redirect-service, analytics-api]
    consumes: []

  - id: shortening-api
    title: URL shortening endpoint
    type: unit
    status: approved
    file: specs/shortening-api/spec.md
    depends_on: [storage-schema]
    produces:
      - name: POST_/shorten
        shape: "request{long_url: string} → response{short_code: string} | error{400 invalid_url}"
        consumers: [integration-e2e]
    consumes:
      - name: url_table
        from: storage-schema

  - id: redirect-service
    title: Short-code redirect handler
    type: unit
    status: in_review
    file: specs/redirect-service/spec.md
    depends_on: [storage-schema]
    produces:
      - name: GET_/:short_code
        shape: "request{short_code: path} → response{302 redirect} | error{404 not_found}; side_effect{insert into click_log_table}"
        consumers: [integration-e2e, analytics-api]
    consumes:
      - name: url_table
        from: storage-schema
      - name: click_log_table
        from: storage-schema

  - id: analytics-api
    title: Click analytics endpoint
    type: unit
    status: planned
    file: specs/analytics-api/spec.md
    depends_on: [storage-schema, redirect-service]
    produces:
      - name: GET_/stats/:short_code
        shape: "request{short_code: path} → response{click_count: int, last_clicked: timestamp|null} | error{404 not_found}"
        consumers: [integration-e2e]
    consumes:
      - name: click_log_table
        from: storage-schema

  - id: integration-e2e
    title: End-to-end integration test
    type: integration
    status: planned
    file: specs/integration-e2e/spec.md
    depends_on: [shortening-api, redirect-service, analytics-api]
    produces:
      - name: e2e_verification_report
        shape: "report{all_scenarios_passed: bool, scenario_results: list, discovered_issues: list}"
        consumers: []
    consumes:
      - name: POST_/shorten
        from: shortening-api
      - name: GET_/:short_code
        from: redirect-service
      - name: GET_/stats/:short_code
        from: analytics-api

milestones:
  - name: mvp-ready
    specs: [storage-schema, shortening-api, redirect-service, integration-e2e]
    status: in_progress
  - name: analytics-complete
    specs: [analytics-api]
    status: not_started

history:
  - timestamp: 2026-01-15T09:00:00Z
    event: project_created
    by: operator-001
    note: initial conceptualization
  - timestamp: 2026-01-15T09:45:00Z
    event: manifest_locked
    by: operator-001
    note: "5 specs defined, 1 integration spec, DAG invariants validated"
  - timestamp: 2026-01-15T10:22:00Z
    event: spec_started
    ref: storage-schema
    by: claude-sonnet-4
  - timestamp: 2026-01-15T10:35:00Z
    event: spec_produced
    ref: storage-schema
    by: claude-sonnet-4
  - timestamp: 2026-01-15T10:41:00Z
    event: spec_approved
    ref: storage-schema
    by: gpt-5
  - timestamp: 2026-01-16T09:10:00Z
    event: spec_started
    ref: shortening-api
    by: claude-sonnet-4
  # ... further entries elided ...
```

Notes on the example:

- The DAG has clean structure: `storage-schema` is a root (no dependencies); `shortening-api` and `redirect-service` depend on it; `analytics-api` depends on both storage and redirect (because it reads the click log that redirect writes); `integration-e2e` depends on the three service specs.
- Interface summaries are terse but precise. Full type contracts live in the individual spec files.
- At this snapshot: two specs approved, one in review, two planned. The integration spec cannot dispatch yet because its dependencies aren't all approved.
- History shows the audit trail; every status change is logged. Append-only.
- Interpreters are distinct across producer, validator, and arbiter roles per the heterogeneity requirement.

---

## §G · Anti-Patterns

What a bad manifest looks like:

- **Implicit dependencies.** A spec consumes something from another spec but `depends_on` doesn't list it. Catchable by invariant 3.
- **Magic glue.** Two specs have a hidden interface that isn't declared in `produces`/`consumes`. Appears to work during development; breaks at integration.
- **Status lies.** A spec marked `approved` when `execution.validator` is null, or when validator equals producer. Catchable by invariants 5 and 6.
- **Orphan outputs.** A `produces` entry with no consumers and no deployment use. Usually means scope creep.
- **Mega-specs.** One spec covers what should be four. Detectable by an unusually high number of interfaces produced, or by acceptance criteria that span multiple concerns.
- **Missing integration specs.** Multiple unit specs compose at runtime but no integration spec exists. Locus-2 failures are guaranteed.
- **Historical edits.** Someone modified a past history entry. Breaks the audit trail. Detect via git diff on the history block.
- **Same-model validator.** Producer and validator are the same LLM. Catchable by invariant 6; undermines the entire locus-1 mechanism.
- **Unbounded scope in project.objective.** "Build a great app" is not an objective. Concrete, one-sentence, outcome-shaped — or reject the manifest.

---

## §H · Lifecycle Rules

- **Manifest is locked when project status is `executing`.** Spec additions or modifications after locking require explicit history events.
- **Manifest is append-only in history.** Never edit or delete a past history entry.
- **Manifest is canonical.** When the manifest and a spec file disagree, the manifest wins for DAG structure; the spec file wins for internal content. Conflicts are errors that must be resolved before dispatch.
- **Manifest is version-controlled.** Treat it as source. Diffs between commits show the evolution of the project's shape.
- **Manifest is read-locked during dispatch.** The dispatcher reads the manifest, decides, updates it atomically. No concurrent writes from multiple dispatchers.

---

*End of PROJECT_MANIFEST.md v1.0*