# Current Focus

**Phase:** Strix S0-v2 Out-of-Container Egress Gateway (Part B)
**Status:** Step-0 design note revised per PM review (all 7 findings resolved). PM verdict: APPROVE-WITH-CONDITIONS. Two conditions to verify in live proof: (1) DNS residual adversarial test, (2) REDIRECT→proxy path verification. Awaiting PM bypass-clean confirmation before implementation.
**Branch:** `sgl-s3.1` @ `6aa8487` (HEAD, pushed to origin)
**Role:** PRODUCER (Opus routing — network/containment architecture)
**Updated:** 2026-06-22 (PM review resolved; revised note at `.agents/specs/Part_B-Step0-Design-Note.md`)

## Resumption Point
- **Immediate:** PM confirms revised note bypass-clean → green-light implementation.
- **Implementation order:** gateway image → docker_client.py wiring → teardown retired mechanism → live containment proof → full suite green + ruff clean.
- **Two conditions verified in live proof:** (1) root agent rewrites resolv.conf → DNS still resolved only through gateway; (2) REDIRECTed TCP/DNS actually lands on the proxy, ESTABLISHED/RELATED in FORWARD checked.
- **Before implementation:** do not remove working-but-disabled enforcement until the replacement is live-proven.
- **Hard invariant:** SGL stays removal-upstream only. Never alter a disposition, add an evidence_class, or touch core/logic|proposals|oob|diff|race/.

## M0 reproducible SHA
`6aa8487` on `sgl-s3.1` (auth_matrix registration committed, pushed to origin)

## LLM provider config
Provider: naraya | Model: naraya/minimax-m3 | Base: https://router.naraya.ai/v1 (key per `.agents/api.txt`, not recorded here)
