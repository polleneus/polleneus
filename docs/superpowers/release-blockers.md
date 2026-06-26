# Polleneus — Release Blockers (v1)

**Status:** living tracking doc · **Created:** 2026-06-26 · **Owner gate:** CTO
**Parent design:** [polleneus v0.5](specs/2026-06-25-polleneus-design.md)

A release blocker is a condition that **must be cleared before any public/installable build ships**.
This doc consolidates the security constraints, the parent design's P5/P6 release gates, and the
measured findings from the simulator (slice 3) into one tracked list. Each blocker has a **status**:

- **OPEN** — not yet addressed; no work landed.
- **MEASURED-IN-SIM** — quantified in the simulator (an upper bound / model number), but the
  field/hardware number or the production mitigation is still owed.
- **ADDRESSED** — cleared, with the evidence linked.

The deadliest failure mode for this project is **false confidence** (parent §12.8): shipping while a
caveat reads as a guarantee. So a blocker is "cleared" only with linked evidence, never by assertion.

---

## B1 — No public/installable build before an independent security audit  ·  **OPEN**

No usable or installable artifact (APK/IPA/desktop) may be distributed before an independent,
adversarial security audit of the crypto, transport, and key-management stack. This is the
hardest gate and gates every other "ship" decision.

- **Why:** an offline-first anonymity tool that fails is worse than none — users act on a false
  promise in exactly the settings where exposure is dangerous.
- **Clear when:** a named external auditor signs off on the v1 stack (spend primitive, AEAD,
  key-evolution, transport) against a written threat model.
- **Now:** the codebase is a *simulator/research* tree, not a shippable client — so this is not
  yet imminent, but it must be formalized before any client work begins.

## B2 — Publish the realized sender-origin identifiability number  ·  **MEASURED-IN-SIM**

The parent design (§16-P6, P6) requires publishing the **realized origination-identifiability
probability** from an adversarial source-estimator audit + a USRP PHY self-audit — *before* any
"anonymous" claim. The simulator now provides the **model** number; the **field/USRP** number is owed.

- **Measured (sim, slice 3, all UPPER BOUNDS on anonymity):**
  - **PR-1** — single-event source localization against a passive receiver grid leaks the origin
    (rank-1 materially above the 1/N floor under realistic coverage). [`sim/` slice-3 PR-1]
  - **PR-2** — the cheap network-layer defenses (Poisson mixing λ=0.05, receive-before-originate
    gate G=3) do **NOT** materially cut that leak, and mixing costs delivery — the credit gate
    refuses both. [PR #9]
  - **PR-3** — **multi-session intersection deanonymizes a persistent sender**: fused rank-1 climbs
    ~0.09→0.72 over K=1→16 originations (decoy flat at 0.00, random floor ~1/N), crossing the
    exposure threshold — *under assumed device-linkage*. A single message ≈ anonymous; a persistent
    author is not. [PR #10]
- **Clear when:** the field/USRP device-linkability number is measured and published alongside the
  sim numbers, and the public-facing copy states the honest posture (below, B3).
- **Owed:** USRP PHY self-audit (real device-linkability, not assumed); a real-deployment source-
  estimator pass; clustered-mobility ("gathering") sweep (sim is RWP open-field only → optimistic).

## B3 — Honest anonymity posture in all user-facing copy  ·  **OPEN**

No unqualified "anonymous" claim. The honest, evidence-backed posture from slice 3:

- **Strong recipient anonymity** — pure flooding lands a message on ~everyone in the component, so
  receipt ≠ being the recipient.
- **Sender anonymity is best-effort and degrades against a resourceful, persistent, sensor-dense
  adversary** — single messages are roughly anonymous; persistent authors are deanonymizable under
  multi-session intersection + device fingerprinting (B2).
- **Existence of mesh traffic is detectable** — running the app is itself a membership signal in the
  most repressive settings (largely unavoidable for any radio protocol); blend toward ordinary BLE.
- **Clear when:** onboarding/marketing/docs carry this posture, reviewed against the B2 numbers; no
  surface implies sender-unlinkability or undetectability.

## B4 — v1 spend + key-evolution cost on low-end Android  ·  **OPEN**

Parent §P5 names this a release gate: benchmark the **v1 audited spend primitive (blind-RSA / BBS
show)** + time-ratcheted forward-secure key-evolution on low-end Android against BLE
MTU/fragmentation + battery. (The bespoke Fiat-Shamir ZK nullifier is correctly **deferred post-v1**
behind the §9.5 non-ZK fail-closed quota — not a v1 blocker.)

- **Clear when:** measured spend + key-evolution latency/battery on a low-end handset is within the
  budget that keeps the soup uniform and the UX usable.

## B5 — Continuous-verification gates green  ·  **OPEN**

Parent §P6: multi-OS transport conformance harness; adversarial-eviction CI gate; **internet-disabled
CI** (an offline-first tool must build/test with no network); the simulator's percolation +
airtime + anonymity gates kept green as the model evolves.

- **Status:** the simulator's own gates (percolation oracle, airtime publish-gate, anonymity
  must-localize/exposure/defense/intersection gates) are green in-repo. The **client-side** transport
  conformance + adversarial-eviction + internet-disabled CI are OPEN (no client yet).

---

## Deferred (explicitly NOT v1 blockers)
- **Bespoke Fiat-Shamir ZK-spend nullifier** — deferred post-v1 (parent §12.7); v1 ships the audited
  blind-RSA/BBS spend, bounded by the §9.5 non-ZK fail-closed quota.
- **Insider / compromised-node adversary**, **defenses-vs-intersection (sim PR-4)**, **clustered
  mobility** — named follow-ups; tracked under B2's "owed" list, not v1 ship gates on their own.

## Change log
- 2026-06-26 — created; B2 populated from slice-3 PR-1/PR-2/PR-3 (PRs #7–#10).
