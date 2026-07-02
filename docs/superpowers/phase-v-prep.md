# Phase V prep — the verify + audit runway (X5 exit review)

**Status:** X5 exit deliverable (kickoff spec §6) · **Date:** 2026-07-02
**Purpose:** the honest list of what stands between the current client and the **B1 independent
security audit** (the gate on ALL shipping). Items are ordered by track; none are optional unless
marked. Nothing here weakens B1–B5.

## 1. What the audit gets (scope as of X5)

- `client/` — the full Android app: `mesh/crypto/Crypto.java` (X-Wing sealing, key-committing
  AEAD, commit-before-reveal pairing, PQ sender-auth; 13 JVM tests), `mesh/store/` (H4
  keystore-wrapped at-rest keys, wrap-key-first panic), `mesh/ble/PairingManager.kt` (SAS
  ceremony), `mesh/transport/` (content-addressed store-carry-forward flooding),
  `service/MeshService.kt` (FGS + keyguard-enforced discreet notification), the Compose UI with
  the honest-copy law enforced by `CopyLawTest`.
- `sim/` — the P0–P6 simulator whose gates justify the protocol parameters (upper bounds only).
- `docs/superpowers/specs/` — parent design (7 invariants, threat model) + per-phase specs.
- Known deliberate deviations from the spike port, each documented inline: `Locale.ROOT` SAS
  formatting (cross-locale glyph consistency), explicit API-28 StrongBox floor.

## 2. Engineering debts to close BEFORE handing to the auditor

| # | Debt | Why it blocks a clean audit |
|---|---|---|
| V1 | **Unify pairing + mesh onto one GATT service** (spike already does this; the client serializes them) | Two radio states = two security postures to review; the serialization dance is accidental complexity an auditor must otherwise reason about |
| V2 | **Port the duty cycler (pocket operation)** | The FGS keeps the process alive but screen-off discovery is degraded; the shipped behavior must match the audited behavior |
| V3 | **Contract amendment for a DEGRADED state** (bluetooth-off / permissions-revoked currently collapse into PAUSED with a home-tile hint) | The UI-facing contract should name every reachable radio state; collapsing hides a state transition from review |
| V4 | **Pairing retry-slot robustness** (responder `serverState` can block a re-pair COMMIT after a completed ceremony) | A flaky ceremony invites "just tap it again" habituation — exactly what a MITM wants |
| V5 | **Q2: pin the real payload cap** (2048 B placeholder in `maxPlaintextBytes`) | Wire-format bounds are audit surface |
| V6 | **Multi-hop re-demo on the client** (proven on the spike ferry; same store-carry-forward, not re-demonstrated in `client/`) | "Same code path" is a claim; the audit wants the demonstration |
| V7 | **Adversarial-eviction test** (P5 §10): a hostile flood must not evict legitimate carried blobs beyond the modeled bound | The eviction policy is a DoS surface; sim gates cover it, the client build must too |
| V8 | **Nearby-count decay** — `peersSeen` only grows on sightings (and BLE MAC rotation inflates it); a departed peer never decrements the count until restart | "Nearby: N devices" is a surfaced radio fact; a stale N overstates the mesh — an honesty defect, found at X5's Q6 measurement |

## 3. Verification work owed (not code)

- **Usability pass with outsiders** — X2–X5 validated mechanics with insiders (n=2). A moderated
  pass with people who have never seen the app is a **pre-pilot requirement** (kickoff §8): the
  SAS compare, the honesty gate, and panic must survive first contact.
- **TalkBack full audit** — X5 delivered the first pass (roles, states, labels on every custom
  control; screen-reader activation of destructive holds is a documented a11y-vs-friction
  decision for the auditor to revisit). Owed: full traversal-order review, contrast audit against
  final rendering, font-scaling behavior.
- **Battery A/B + M3/M5 characterization** (Phase T leftovers) — run in parallel; numbers feed
  the honest battery copy.
- **B2 field anonymity numbers** — USRP PHY device-linkability + real source-estimator; sim
  numbers are upper bounds and are labeled as such everywhere.
- **B3 copy review** — store text and any distribution copy quote the "what this protects"
  canonical wording; `CopyLawTest` is the floor, the human pass is the gate.

## 4. Standing constraints (unchanged)

- **B1 gates all shipping.** CI builds debug APKs only; no release artifacts exist anywhere.
- A persistent, device-fingerprinted author is **not protected** (architecturally final).
- Deletion is device-local; running the app is a detectable membership signal.
- All simulator numbers are upper bounds (RWP-optimistic).
