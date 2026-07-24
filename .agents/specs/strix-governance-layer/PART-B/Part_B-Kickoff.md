Part B kickoff 
Directive — S0-v2: out-of-container egress gateway. From: PM/Validator (opus-4.8-pm-auditor). Part A is closed (6aa8487); proceed to Part B.

Architecture (per pm-decision-s0-egress-gateway.md): move egress enforcement out of the agent's container. Agent container on an internal Docker network with no default internet route; a separate egress-gateway container runs the decision proxy and is the only path out; the agent's default route points at it. Scope is enforced in the gateway's netns, so the agent — even as root in its own container — cannot reach or flush the rules. This dissolves the entire PRE-3/run_as problem class.

Step 0 — design note first (before tearing anything out). Send me a short approach note covering the four riskiest wiring decisions, for review before implementation:

How docker_client.py creates the internal network + agent container with no default route, and sets the agent's default route to the gateway.
How the gateway container enforces in its own netns (iptables/proxy placement) such that the agent can't administer it.
Where scope.decide(), F1 DNS→IP + rebinding defense, the Caido decide() gate, and S3.1 target-health run inside the gateway (all reused, not rewritten).
What legitimate NET_ADMIN/NET_RAW + host-gateway behavior the agent still needs inside its own netns, preserved.
I review that, then you implement. Rationale: don't remove working-but-disabled enforcement until the replacement is designed.

Remove (retired): factory.py run_as="pentester"; in-container iptables in egress-enforcer.sh; docker_client.py user="root" exec juggling tied to enforcement.

Reuse (move into the gateway, logic unchanged): scope.py decide(); F1 DNS→IP allow-set + rebinding defense (egress_proxy.py); the Caido decide() gate (now belt-and-suspenders); S3.1 target-health (gateway sees every connection → feeds the breaker).

Order: design note (Step 0) → implement gateway image + internal-network wiring → remove the retired in-container mechanism → live containment proof → full suite + ruff.

Live containment proof (the operator's hard gate — this is what unblocks the paper): with the gateway active —

empty scope ⇒ the agent (shell tool or curl) reaches nothing (gateway denies);
in-scope host ⇒ reachable;
the agent cannot reach or flush the gateway's rules (different container);
and the engine still completes the scan + reports the IDOR.
Definition of Done: gateway architecture implemented; in-container iptables + run_as removed; live containment proof passes with pasted evidence; decide()/F1/Caido-gate/S3.1 reused with no logic regression (SP1/SP2/SP3/SP6/SP8 hold); uv run pytest tests/ -q green + ruff check . clean; completion report per VALIDATION_PROTOCOL §C.

Hard invariants: removal-upstream only. Never alter a disposition, add an evidence_class, or touch core/logic|proposals|oob|diff|race/. SGL stays gate-neutral.

Send me the Step-0 design note when the coder produces it — I'll review the containment architecture before they remove the old enforcer, so we don't open a window with no design. 