# polleneus — P0–P6 campaign close-out (ratification + honest open ledger)

**Date:** 2026-06-28 · **Owner gate:** CTO/CEO · **Parent:** [polleneus v0.5 §16 roadmap](specs/2026-06-25-polleneus-design.md) · [release-blockers](release-blockers.md)

This ratifies the §16 P0–P6 simulator/spec campaign. It is an **honest ledger**, not a victory lap: it
records what is *sim-validated*, what is *deferred as an open problem*, and what still *needs a human*. The
mission — **a messenger that works when infrastructure is down** — is **validated in simulation**; a
shippable client remains gated by **B1 (independent security audit)**.

## Phase ratification (all on `main`)

| Phase | Delivered (honest headline) | PRs |
|---|---|---|
| **P0 — re-scope & measure** | airtime-budget table beside storage; "cost not a wall" flooding bound; no airtime knee in the operating range | #2,#4,#5,#7,#13,#14 |
| **P1 — highest-ROI wins** | rateless reconciliation cost model (honest non-monotone, not strict); pairing + truth-in-labeling UX | #15,#16,#17 |
| **P2 — anti-flood + anonymity** | token rate-limit (anchored nullifier + gossip-vs-spend race); origination defenses → **NULL** verdict; originator-anonymity **impossibility + reframe** (a disclosed bounded property, not a blocker) | #18,#19,#20 |
| **P3 — lifetime/storage hardening** | **the soup self-clears in a blackout via the local hold-budget `H`, even on a wildly-skewed clock** (offset-invariant); hop-energy spread cap; density-adaptive `H` (a *trade*, not dominance) | #22,#23 |
| **P4 — percolation + cold-start** | **mobility ferries messages below the static percolation threshold**, governed by the time-budget (= `H`), at a latency cost; the **bridge** lifts the island floor *only with purposeful routing* | #24,#25 |
| **P5 — serverless key-management** | v1 key-management **design-for-audit** + the **B4 on-device benchmark protocol** + the time-ratchet **forward-jump bound** (always-on closed; boot-reset open) — **UNAUDITED**, no crypto code | #26 |
| **P6 — continuous verification** | in-repo **offline-first guard** (runtime, common socket stack) + sim gates run via `pytest`; CI auto-run authored (pending token scope) | #27 |

**Recurring discipline that held throughout:** an in-loop adversarial review on every PR, which repeatedly
caught **false confidence** (oversold "dominance" in P3-PR2 and P4-PR1; the ergodic-saturation tautology in
P4-PR1; non-disconnected "islands" in P4-PR2; the FJB boot-reset gap and "EXACT w.p.1" overclaim in P5; the
"proof" vs "guard" wording in P6) — each retracted to an honest claim **before merge**. The deadliest failure
mode (a caveat reading as a guarantee) was the thing we fought hardest, by design.

## Honest open ledger (what is NOT done)

**Release blockers (see [release-blockers.md](release-blockers.md)):**
- **B1 — independent security audit: OPEN** (the hardest gate; gates every ship). Audit target + §10
  open-questions list now defined (P5).
- **B2 — field origination-identifiability: MEASURED-IN-SIM**; the USRP PHY + real source-estimator field
  numbers are **OWED** (hardware).
- **B3 — honest anonymity copy: OPEN→reframed** — cleared by truthful copy (P2 reframe), to be applied to
  onboarding/marketing when a client exists.
- **B4 — on-device spend/key-evolution benchmark: protocol DEFINED (P5 §9), run OWED** (real handset;
  thresholds TBD pending the B2 field-airtime anchor).
- **B5 — continuous-verification: sim gates + offline guard ENFORCED via `pytest`; GitHub-Actions auto-run
  PENDING token `workflow` scope; client-side conformance/eviction OPEN** (no client).

**Deferred open problems (documented, not solved):**
- Passive **clock-trust estimator** from the sealed `created_at` stream (P3) — the gossip-median is
  non-functional; **this is also the FJB boot-reset gap** (P5 §10.1), the load-bearing crypto-availability item.
- The **forward-secure / puncturable KEM** construction that makes time-ratchet deletion real with a stable
  address (P5 §10.2) — load-bearing for forward secrecy; unspecified, unaudited.
- **Youngest-by-real-age eviction** redesign (needs its own injection-adversary model).
- **Heterogeneous-network** end-to-end ferrying win (P4 follow-up); a long-range **NAN/LoRa sideband** bridge.

**Needs a human (cannot be done by the autonomous loop):**
1. **Grant the `polleneus-dev` PAT the `workflow` scope** (or add the two files manually) so the P6 CI
   auto-runs — the authored files are in the working tree and embedded in the Appendix below.
2. **Fix the repo default branch → `main`** (`gh api -X PATCH repos/polleneus/polleneus -f default_branch=main`,
   then delete the stray `chore/ways-of-working` branch). It is currently a near-empty stub; all 27 PRs of work
   live on `main`. Does not block development (every PR uses `--base main`), but a public clone gets the wrong
   branch.

## Mission status (plain language)

The protocol is **validated in simulation** for the core "works-when-things-go-down" properties: messages
deliver in a sparse/blackout network via mobility ferrying (P4), the soup self-clears without a trusted clock
(P3), anti-flooding holds the rate down (P2), and the honest privacy posture is documented (P2/B3). What is
**not** done and **must not be skipped**: the **security audit (B1)**, the **on-device benchmark (B4)**, the
**field anonymity numbers (B2)**, and **building the client** — none of which a simulator can close. polleneus
is, today, an honestly-measured research foundation with a clear, gated path to a shippable tool.

---

## Appendix — authored CI workflows (pending `workflow` token scope)

These are ready in the working tree at `.github/workflows/` but could not be committed by the `polleneus-dev`
token (missing `workflow` scope). Embedded here so they are version-controlled and recoverable; add them with
a token that has `workflow` scope.

### `.github/workflows/ci.yml`
```yaml
name: CI
on:
  push:
  pull_request:
defaults:
  run:
    working-directory: sim
jobs:
  test:
    name: gates (fast suite)
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev]"
      - run: pytest -q
  offline-first:
    name: internet-disabled (offline-first guard)
    runs-on: ubuntu-latest
    timeout-minutes: 20
    env: { POLLENEUS_OFFLINE_CI: "1" }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev]"
      - run: pytest -q
```

### `.github/workflows/gates-nightly.yml`
```yaml
name: gates-nightly
on:
  schedule:
    - cron: "0 4 * * *"
  workflow_dispatch: {}
defaults:
  run:
    working-directory: sim
jobs:
  gates-slow:
    name: gates (heavy end-to-end sweeps)
    runs-on: ubuntu-latest
    timeout-minutes: 45
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev]"
      - run: pytest -q -m slow
```
