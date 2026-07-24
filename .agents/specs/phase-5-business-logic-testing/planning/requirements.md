# Phase 5 — Business-Logic State Testing — Requirements (Planning)

> Spec-Architect PBT variant · Phase 5 of the strix bounty-grade engine.
> Primitives: **P1 + P2 + P3 + F3** (consumes every earlier primitive). Feature **F5** (business-logic state testing).
> **Terminal phase — highest ceiling, highest noise risk.** Comes last because it composes all earlier substrate. Source: `strix-bounty-roadmap.md` §Phase 5 (advice #4), §1.2, §6. Program index: `specs/README.md`.

---

## Problem / Intent

Business-logic flaws are the highest-value bounty class and the one strix cannot reach with scanner breadth: step-skipping a checkout, replaying a one-time coupon, double-spending a balance, paying a mismatched price, transitioning an object into a state the workflow forbids. They are *application-specific* — there is no generic signature. Finding them requires a **model** of the application's journeys, object lifecycles, trust boundaries, and monetary operations.

An LLM agent is uniquely good at *proposing* such a model and uniquely dangerous at *confirming* it. This is the roadmap's central anti-pattern (§6: "generic business-logic modeling frameworks produce plausible-but-wrong invariants") and its principle 2 ("**the agent proposes; deterministic harnesses dispose** — never let the model both invent and confirm an invariant; that is how agents produce confident nonsense"). A model that *invents* the invariant "a coupon can only be redeemed once" and then *narrates* "I redeemed it twice, therefore vulnerable" without ever executing a second redemption is exactly the confident nonsense Phase 5 must structurally prevent.

The intent of Phase 5 is to make that split concrete and non-bypassable:

- **The agent PROPOSES the model** — user journeys, object state machines, trust boundaries, monetary operations, and the high-value flows (approval / coupon / refund / credit / invite) — as a recorded, inspectable hypothesis, never a verdict.
- **DETERMINISTIC HARNESSES DISPOSE** — for each proposed invariant, a class-specific harness *executes* a violation attempt (step-skip, replay, double-spend, quantity/price mismatch, unauthorized state change) and reports the resulting application state.
- **Every reported violation MUST carry deterministic evidence** — a P2 differential, a P3 OOB callback, or a Phase-4 race result. A finding the harness cannot back with one of these three artifacts is *not reportable*. No narrative-only findings, ever. This is the impact gate, specialized for logic.

Phase 5 invents almost no new primitive: it is an **orchestrator** that turns an agent-proposed journey/state model into executable violation tests wired through P1 (replay as the right identity), P2 (differential evidence), P3 (callback evidence), the Phase-4 race harness (double-spend evidence), and the Phase-3 inventory (which surface/parameters to drive).

---

## Beneficiaries

| Beneficiary | Benefit |
|---|---|
| The strix LLM agent | Gets a structured way to apply its strongest skill (modeling an unfamiliar app) without being trusted to confirm — it proposes the model; harnesses decide. It composes existing primitives instead of inventing a logic engine it would hallucinate around. |
| The human bounty operator | Receives the rarest, highest-paying class of finding (logic/financial) backed by a concrete reproduction — a state the application should not allow — not a plausible story. The confirmation-bias failure mode is removed by construction. |
| Earlier phases | Their primitives gain their highest-leverage consumer: P1/P2 become the evidence channel for step-skip/unauthorized-transition, P3 for async/webhook logic, Phase-4 for double-spend, Phase-3 for the parameter classes (`amount`/`state`/`role`) that seed the model. |
| The report layer | Receives logic findings already evidence-gated: each `vulnerability_report` carries a diff, a callback, or a race result, so impact-gating (`strix/report/state.py`) holds for the noisiest class too. |

---

## Core Functionality

1. **Journey / state-model intake (agent-proposed schema).** A recorded, structured model the agent fills in: user journeys (ordered steps), object lifecycles (states + allowed transitions), trust boundaries (which identity may drive which step), monetary operations (amount/price/quantity fields and their relations), and named high-value flows (approval, coupon, refund, credit, invite). Stored as an **inspectable hypothesis** per target/engagement, every field tagged "agent-proposed", never auto-trusted. Parameters/endpoints are drawn from the Phase-3 inventory (param classes `amount`/`state`/`role`), not re-derived.
2. **Invariant catalog & violation-test library (deterministic).** A fixed catalog mapping each invariant *kind* to a deterministic violation test: **step-skip** (jump to step N without N-1), **replay** (re-submit a one-time action), **double-spend/race** (concurrent redemption — *reuses the Phase-4 race harness*), **quantity/price mismatch** (tamper amount/price/quantity, re-derive expected total), **unauthorized state change** (drive a transition the model marks forbidden, as a non-permitted identity via P1). The agent picks *which* invariant applies to a proposed flow; the *test* for that kind is deterministic and identical every run.
3. **Execution orchestrator (wires P1/P2/P3/P4).** For a chosen invariant+target flow, the orchestrator executes the violation sequence: replays steps as the modeled identity (**P1**), captures the before/after responses and diffs them (**P2**), launches the concurrent variant via the **Phase-4 race harness** for double-spend, mints/awaits a callback (**P3**) for async/webhook logic, and reads endpoints/params from the **Phase-3 inventory**. It records the executed sequence and the resulting state.
4. **Evidence gate (the hard control).** A proposed violation is promotable to a finding **iff** the orchestrator attached a deterministic artifact — a non-empty **P2 diff** ∨ a correlated **P3 callback** ∨ a **Phase-4 race result** — *and* the executed sequence demonstrably reached a state the agent's model declared impossible. No artifact ⇒ not reported (stays an unconfirmed hypothesis). The proposing model never supplies its own confirmation.
5. **Report integration (impact-gated).** A confirmed logic violation writes a `vulnerability_report` (`strix/report/state.py`) carrying: the violated invariant, the executed sequence (reproduction steps), and the backing artifact. The reproduction is re-runnable; re-running the harness reaches the same disallowed state.
6. **Agent tool surface (F5).** `@function_tool`s mirroring `strix/tools/proxy` conventions: submit/inspect a proposed journey-state model, list candidate invariants for a flow, run a chosen violation test (orchestrator), and read the gated result (confirmed-with-evidence or unconfirmed-hypothesis).

---

## User Stories

- **As the strix agent**, I want to record a proposed model of a checkout journey (steps, the coupon's one-time invariant, the price field), so the harness has a hypothesis to attack — and so my proposal is logged as a hypothesis, never a finding.
- **As the strix agent**, I want to ask the harness to *execute* a double-redemption of a coupon via the Phase-4 race harness, so a real double-spend state — not my narration — decides whether it is reportable.
- **As the strix agent**, I want to tamper a price field and have the orchestrator replay the order as the buyer (P1) and diff the charged total (P2), so a quantity/price mismatch is backed by a concrete diff.
- **As the strix agent**, I want to drive a forbidden state transition as an unauthorized identity and have it confirmed only by a P2 diff showing the transition succeeded, so I never report a transition the app actually blocked.
- **As the human operator**, I want every logic finding to carry an executed reproduction plus a diff / callback / race-result, so I can re-run it and see the disallowed state in seconds — no plausible-sounding narratives.
- **As the human operator**, I want the agent's *proposed* invariants kept visibly separate from *confirmed* violations, so I can trust that nothing was self-confirmed by the model.

---

## Constraints

- **Agent-proposes / harness-disposes is structural, not advisory.** The proposing model is *never* on the confirmation path. Confirmation comes only from a deterministic harness artifact. This is the primary mitigation for the confirmation-bias / plausible-but-wrong-invariant risk and is enforced by the evidence gate, not by prompting.
- **Evidence-gating is non-negotiable.** No P2 diff ∨ P3 callback ∨ Phase-4 race result ⇒ not reportable. A flagged violation must be an *executed* sequence reaching a model-declared-impossible state, never a static or narrative claim (roadmap §6: "promoting findings on static suspicion").
- **Reproducibility.** Every reported violation must re-run: re-executing the harness reproduces the disallowed state. Non-deterministic one-offs are not reportable as confirmed.
- **No generic logic-modeling framework.** The invariant catalog is a *fixed, small* set of violation-test kinds; the model is an agent-proposed hypothesis, not a learned/inferred engine (roadmap §6 anti-pattern). Phase 5 builds an orchestrator, not a general invariant solver.
- **Reuse, don't re-derive.** Race execution = Phase-4 harness. Identity/replay = P1. Diff = P2. Callback = P3. Surface/params = Phase-3 inventory. Phase 5 adds the model-intake, the catalog, the orchestrator, and the evidence gate — nothing those phases already own.
- **Per-engagement only.** The journey/state model and confirmed violations are per-engagement; no cross-target logic memory (program deferral, advice #14) — which would itself reintroduce confirmation bias.
- **WHAT, not HOW** in `spec.md`; no code bodies. **Estimates in iterations**, never time.
- **Glass-box.** The proposed model, the chosen invariant, the executed sequence, and the backing artifact are all recorded and inspectable; confirmation is never a black-box verdict.
- **Component size:** backend modules cohesive/single-responsibility; any TUI surface ≤ 400 lines.
- **Test budget:** 16–34 focused tests total; the evidence gate and no-self-confirmation invariants additionally get Tier-2 PBT.

---

## Reusable strix code (reuse before build)

| Module | What it gives us | Use in Phase 5 |
|---|---|---|
| `strix/tools/proxy/caido_api.py` | `parse_raw_request`, `apply_modifications`, `build_raw_request`, `replay_send_raw`, `parse_raw_response`, `full_url_from_components` | Drive each journey step / tamper amount/price/quantity / re-submit a replay. |
| `strix/tools/proxy/tools.py` | `@function_tool`, `_ctx_client`, `_to_tool_json`, `_err`, JSON-return conventions | Shape of the model-intake / list-invariants / run-violation tools. |
| `strix/report/state.py` | `add_vulnerability_report(...)`, `vulnerability_reports` | Impact-gating sink: attach the violated invariant + executed sequence + backing artifact. |
| `strix/core/sessions.py` | `SQLiteSession` durable per-id pattern | Mirror for the per-engagement journey/state-model + confirmed-violation store. |
| `strix/core/{paths,runner,inputs}.py` | run orchestration + path helpers | Durable model/violation store location and run wiring. |
| `strix/tools/{notes,todo,thinking,reporting}/` | `@function_tool` / JSON-return conventions | Tool surface conventions for the new F5 tools. |
| `tests/test_core_paths.py` | unittest + spec-loaded-module regression pattern | Mirror for Tier-1 tests. |

### Explicit reuse of earlier-phase primitives (hard dependencies)

| Primitive | Owning phase | What Phase 5 consumes | Phase-5 use |
|---|---|---|---|
| **P1 — identity store + replay-as-identity** | Phase 1 | Replay any captured request as a stored identity (incl. unauthorized identity) | Drive journey steps and forbidden transitions as the modeled / non-permitted identity. |
| **P2 — differential engine** | Phase 1 | Semantic before/after diff with volatile-field normalization | **Evidence type 1**: confirm step-skip / unauthorized-transition / price-mismatch via a non-empty diff. |
| **P3 — OOB oracle** | Phase 2 | Mint token → confirm correlated callback | **Evidence type 2**: confirm async / webhook / callback-driven logic (e.g. refund webhook). |
| **Phase-4 race harness** | Phase 4 | Concurrent replay with shared identity + state diff of resulting balances/orders | **Evidence type 3**: confirm double-spend / replay / multi-redeem; Phase 5 *invokes* it, never re-implements concurrency. |
| **Phase-3 inventory + param classes** | Phase 3 | Ranked surface map; params classified `amount` / `state` / `role` | Seed the model: which endpoints are state-changing, which params are monetary/state/role; where to drive each violation. |

---

## Risks / Assumptions

**Assumptions**
- Phases 1–4 are landed and expose their primitives as the spec references (P1 replay, P2 diff, P3 mint/confirm, Phase-4 race harness, Phase-3 inventory). Phase 5 is the terminal consumer and is not schedulable before them.
- The agent can produce a *useful* journey/state model for a given app from observed traffic + inventory; an imperfect model only costs missed findings, never false ones (the gate blocks unconfirmed proposals regardless).
- The target's flows are exercisable through replayed requests (the same assumption P1/Phase-4 already make).

**Risks**
- **Confirmation bias / plausible-but-wrong invariant (the defining risk).** The model proposes an invariant that does not actually hold, then "confirms" a violation by narration. → **Mitigated structurally** by the agent-proposes/harness-disposes split + the evidence gate: a proposal is never its own confirmation; only a deterministic P2/P3/P4 artifact promotes it, and the executed sequence must reach a model-declared-impossible state. A wrong invariant simply yields no artifact → no finding.
- **Self-confirmation leakage** (the model's reasoning sneaks onto the confirmation path). → The *no-self-confirmation* invariant (PBT'd): `confirmation(I)` originates only from a harness, never from the proposing model; the gate accepts only typed artifacts (diff / callback / race-result), not free-text rationale.
- **Non-reproducible "violation"** (a one-off timing/state fluke). → The *reproducibility* invariant: a reported violation must re-run to the same disallowed state; non-reproducible results stay unconfirmed.
- **Noise explosion** (highest-risk class). → Bounded invariant catalog (fixed small set of violation kinds), surface drawn from the ranked Phase-3 map, and the hard evidence gate together cap output to confirmed, reproducible findings.
- **Over-reach into a generic framework.** → Explicit out-of-scope: no generic invariant-modeling/inference engine; the catalog is fixed and the model is an agent hypothesis.
- **Double counting concurrency logic.** → Phase 5 *calls* the Phase-4 harness for double-spend; it does not re-implement races (avoids divergent, less-tested concurrency code).
- **Cross-target memory temptation** (reuse "this stack usually has coupon bugs"). → Hard out-of-scope; per-engagement only, to avoid chasing ghosts (roadmap §6).
