"""
pbt-properties.py — Strix Governance Layer (SGL)
Phase 4. Property-based test DEFINITIONS (Hypothesis / Python — matches the fork stack)
for the safety-critical invariants in spec.md.

These target the governance layer's enforcement seams, NOT the detection engine. `gov`
denotes SGL seams to be wired during S0-S8; `engine` denotes the (unmodified) propose-dispose
disposer used only by the gate-neutrality property.

Zero-tolerance (a single counterexample blocks release): SP1, SP2, SP3, SP6, SP8.
"""

from hypothesis import given, strategies as st
from sgl_seams import gov, engine  # decision service, enforcer, limiter, breaker, governor, memory, audit

# ---------------------------------------------------------------- generators
hosts = st.from_regex(r"[a-z0-9-]{1,20}\.(com|net|io|internal)", fullmatch=True)
action_classes = st.sampled_from(["recon", "port_scan", "fingerprint", "http", "exploit", "credential"])
egress_paths = st.sampled_from(["caido_http", "shell_curl", "shell_nmap", "shell_sqlmap", "browser", "dns"])
verdicts_non_allow = st.sampled_from(["DENY", "UNKNOWN", "EXPIRED", "ERROR", "NO_RULES"])
targets = st.builds(lambda h, c: gov.Target(host=h, action_class=c), hosts, action_classes)
HIGH_IMPACT = {"exploit", "credential"}


# ============================================================ SP1 scope soundness
# executed egress ⇒ decision was ALLOW
@given(targets)
def test_sp1_scope_soundness(t):
    result = gov.enforcer.attempt(t)          # routes through the egress enforcer
    if result.executed:
        assert gov.scope.decide(t).verdict == "ALLOW"


# ============================================================ SP2 fail-closed
# DENY/UNKNOWN/EXPIRED/ERROR/NO_RULES ⇒ never executes (flips the fork's fail-open default)
@given(targets, verdicts_non_allow)
def test_sp2_fail_closed(t, verdict):
    gov.scope._force(t, verdict)
    assert gov.enforcer.attempt(t).executed is False

# explicit no-rules case: empty scope ⇒ DENY (the audited fail-open bug)
@given(targets)
def test_sp2_no_rules_denies(t):
    gov.scope._load_rules([])                 # no rules loaded
    assert gov.enforcer.attempt(t).executed is False


# ============================================================ SP3 egress completeness  (KEY)
# no egress path bypasses the enforcer — shell tools, browser, DNS, Caido all gated
@given(targets, egress_paths)
def test_sp3_egress_completeness(t, path):
    gov.scope._force(t, "DENY")
    # whatever channel the agent uses, a DENY target must not leave the container
    assert gov.enforcer.send_via(path, t).reached_network is False


# ============================================================ SP4 rate / cred bound
@given(hosts, st.lists(action_classes, max_size=2000))
def test_sp4_rate_and_cred_bound(host, classes):
    lim = gov.limiter.fresh()
    admitted = cred = 0
    for c in classes:
        if lim.admit(gov.Target(host=host, action_class=c)):
            admitted += 1
            cred += (c == "credential")
    assert admitted <= gov.limiter.host_budget(host)
    assert cred <= gov.limiter.CRED_CAP


# ============================================================ SP5 ownership gating
@given(targets, st.floats(min_value=0, max_value=1))
def test_sp5_ownership_gating(t, conf):
    gov.ownership._set(t.host, conf)
    if conf < gov.ownership.THETA:            # default 0.80
        assert gov.scope.decide(t).verdict != "ALLOW"


# ============================================================ SP6 breaker / kill  (zero-tolerance)
@given(targets)
def test_sp6_breaker_halts(t):
    gov.scope._force(t, "ALLOW")
    gov.breaker._breach(t.host)               # health degradation
    assert gov.enforcer.attempt(t).executed is False

@given(st.lists(targets, max_size=500), st.integers(min_value=0, max_value=500))
def test_sp6_killswitch_no_action_after_trip(ts, trip_at):
    gov.breaker.fresh()
    for i, t in enumerate(ts):
        if i == trip_at:
            gov.breaker.kill_switch()
        gov.scope._force(t, "ALLOW")
        gov.enforcer.attempt(t)
    if gov.breaker.tripped():
        assert gov.breaker.actions_after_trip() == 0


# ============================================================ SP7 cost bound
@given(st.lists(targets, max_size=3000))
def test_sp7_cost_bound(ts):
    g = gov.governor.fresh()
    for t in ts:
        gov.scope._force(t, "ALLOW")
        gov.enforcer.attempt(t, governor=g)
    assert g.tokens() <= gov.governor.TOKEN_CEILING
    assert g.tool_calls() <= gov.governor.CALL_CEILING


# ============================================================ SP8 gate-neutrality  (KEY, zero-tolerance)
# for actions SGL allows, the disposer's confirmed set is identical with/without SGL.
# SGL must never add or remove a CONFIRMATION — only remove an ACTION upstream.
@given(st.lists(targets, max_size=200))
def test_sp8_gate_neutrality(ts):
    allowed = [t for t in ts if gov.scope.decide(t).verdict == "ALLOW"]
    with_sgl = engine.confirmed_set(allowed, sgl=True)
    without_sgl = engine.confirmed_set(allowed, sgl=False)
    assert with_sgl == without_sgl            # byte-identical dispositions
    # and SGL imported nothing from the engine packages (checked structurally too):
    assert gov.imports_from_engine() == set()


# ============================================================ SP9 memory sanitization
@given(st.fixed_dictionaries({
    "host": hosts,
    "secret": st.text(min_size=1),
    "technique": st.text(),
}))
def test_sp9_memory_sanitization(record):
    gov.memory.promote_to_shared(record)      # generalize a technique to the shared tier
    shared = gov.memory.shared_dump()
    assert record["host"] not in shared
    assert record["secret"] not in shared      # secret-free
    # only generalized technique text may survive


# ============================================================ SP10 audit completeness
@given(st.lists(targets, max_size=1000))
def test_sp10_audit_completeness(ts):
    gov.audit.reset()
    for t in ts:
        gov.scope._force(t, "ALLOW")
        gov.enforcer.attempt(t)
    # every decision (allow OR deny) produced an audit entry
    assert gov.audit.count() >= len(ts)


# ---------------------------------------------------------------- notes
# SP3 (egress completeness) and SP8 (gate-neutrality) are the two properties unique to
# putting SGL inside Strix: SP3 closes the shell-bypass the audit found; SP8 protects the
# propose-dispose paper from being contaminated by the hardening. Both are release-blocking.
