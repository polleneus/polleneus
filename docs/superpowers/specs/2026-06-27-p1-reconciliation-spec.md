# polleneus — P1: Rateless set reconciliation (spec + sim cost model)

**Version:** v0.3 — 2026-06-27 (design-review rounds 1–2 folded in) · **Roadmap:** P1
**Parent design:** [polleneus v0.5 §8](2026-06-25-polleneus-design.md#8-transport--gossip--beating-the-airtime-wall)
· **Builds on:** the P0 airtime apparatus ([`docs/airtime-budget-table.md`](../../airtime-budget-table.md)).

> **Status:** spec for CTO/CEO sign-off. Scope: the *transport reconciliation* layer and how the
> simulator models its airtime cost. The **pairing / trust-UX** half of roadmap P1 (§13) is a separate
> sibling spec — client surface, gated behind the B1 audit (no client build here).

**Notation (fixed once):** `d_size = ||A|−|B||` (set-size difference, each side knows its own size);
`Δ` = symmetric difference (the inv-4-sensitive quantity — what we must NOT reveal on the wire);
`ρ` = locally-observed density (neighbor count in range — a public quantity each node measures itself);
`S(ρ)` = scheduled cell count (the padded wire schedule); `cap(ρ)` = the difference-elements `S(ρ)` can
recover.

## 1. Problem & why this is P1

The binding scale constraint is **airtime, not storage** (P0). Two neighbors re-sharing blobs must move
**minimal bytes**, or contention eats the budget. Today the **simulator models set-reconciliation
overhead as exactly zero** (`sim/README.md` fidelity table). Every P0 circulation number is an upper
bound partly *because* reconciliation is free in the model. P1 (a) specifies the real protocol and (b)
replaces the zero-overhead abstraction with a **conservative cost model**, then **re-measures** the
circulation haircut.

**The honest headline (sharpened by review):** rateless reconciliation is a strict win on
**decode/compute, trial-decrypt cost, and battery**. It is **NOT** a "cost ∝ difference" airtime win for
polleneus: **uniformity (inv 4) forbids the wire from revealing the difference size**, so we pay a
**flat, density-scheduled airtime floor on every contact** (§2.2). Erlay's "cost ∝ difference" survives
only as a *compute* benefit. So P1 is **"a strict win on compute/battery; on airtime it trades the
fictitious free-reconciliation credit for an honest density-scheduled floor."** Not "zero-tradeoff."

## 2. The protocol (parent §8, made concrete and prior-art-correct)

A contact reconciles two neighbors' sets of 256-bit blob IDs.

### 2.1 Sketch scheme — minisketch (all-or-nothing), IBLT/RIBLT as a sensitivity preset
We model **minisketch (BCH/PinSketch) over 64-bit short IDs** as the primary cost (Erlay/BIP-330 lineage;
cheapest defensible upper bound): cell ≈ one field element (**8 B/cell**, overhead ≈ 1.0), decode
**all-or-nothing at capacity**. **(R)IBLT** is a **named sensitivity preset** (larger cell = sum +
checksum + count, overhead 1.35–10×, supports peeling) — the two differ on **both** cell-size and
overhead and **must not be mixed**.

**Correction to the parent §8 "rateless ⇒ partial progress in a 2 s brush":** false for minisketch — a
decode below capacity recovers **nothing**, and minisketch capacity-extension is **peer-specific** (a
sketch grows *your* set against *one* peer's reconciliation; it is **not** a cross-peer head-start). True
mid-stream partial recovery is a **Rateless IBLT** property (Yang et al., NSDI 2024). So a brush that
fails to reach `cap(ρ)` recovers **nothing this episode** and relies on the soup's redundancy + future
contacts; **no across-contact/cross-peer prefix-carry is claimed or modeled.**

### 2.2 Wire = flat, density-scheduled traffic shaping (invariant 4 — the central constraint)
A naive rateless exchange sends "just enough" cells for the realized difference — but **cell count and
stream duration then leak Δ and set size**, an activity + anonymity-set fingerprint (inv 4 breach). So:

- On **every funded contact**, both sides emit a **fixed schedule of `S(ρ)` cells** (sketch, any Bloom
  fallback, **and** seen-nullifier entries, §2.5), **count and cadence a pure function of `ρ` only** —
  a **public** quantity each node measures from its own neighbor count — **padded with dummy cells**.
  **`S(ρ)` depends on neither `Δ` nor the exact set sizes** (`|A|`,`|B|`,`d_size`): scheduling on set
  size would leak set size, so any soup-size influence must come from a **coarse, gossiped, public**
  soup-size estimate, not exchanged exact sizes. Entering Bloom fallback is emitted on the **same
  schedule/padding** → the mode switch is **on-wire indistinguishable**.
- **Consequence (the key design fact):** the **airtime cost of reconciliation is `S(ρ)`,
  difference-independent**. If realized `Δ > cap(ρ)`, the episode recovers only `cap(ρ)` elements; the
  rest **waits for a future contact** — this shows up as **reduced circulation (the haircut), never as
  extra bytes.** Uniformity converts "large difference" from an *airtime* cost into a *latency/throughput*
  cost. This makes the cost model **simpler and strictly more conservative** than difference-proportional.

### 2.3 Difference transfer + poisoning defense (ephemeral key only)
Connect only for the recovered difference. **Bound decode attempts per contact** to resist
sketch-poisoning; a never-decoding peer is fast-droppable. The counter MUST be keyed **only to the
ephemeral live session** (the BLE connection handle), **discarded on disconnect — never a
PHY/MAC/persistent-token key** — capped by §9.5's per-PHY-radio-session slot cap. (Dropping a peer costs
it only its ephemeral session, no identity.)

### 2.4 Connectionless first
Exchange the `S(ρ)` schedule + proof-prefix over advertising/scan-response; connect only for the tiny
recovered difference.

### 2.5 Seen-nullifier co-tenancy (inherit §9.3 explicitly)
Seen-nf entries **ride the identical `S(ρ)`-scheduled, fixed-size, ID-free frames** as sketch/blob-ID
cells, **on-wire indistinguishable**, and inherit §9.3 ("opaque hashes, no routing metadata"; nf =
H("nf"‖s) per-token, lifetime-stable, **not** per-device → no new linkage).

### 2.6 Platform reality (carried from §8)
iOS background cannot emit a generic ID-free blob → **iOS is an accelerator, not a symmetric peer**;
surfaced. The sim is platform-agnostic; that asymmetry is a **named optimistic modeling gap**.

## 3. The sim cost model (the measurable deliverable)

Replace "overhead = 0" with a per-episode **flat density-scheduled byte cost**, billed against the
airtime ledger competing for the **same per-link goodput as blob transfers** (NB: the 3 advertising
channels are **redundant rebroadcast, not 3× capacity** — `budget.py effective_goodput` removed the
`/n_channels` divisor; do **not** re-introduce it).

Per **funded contact-episode** at locally-observed density `ρ`:

```
recon_overhead_bytes(ρ) = recon_cell_bytes · S(ρ)        # flat, density-scheduled; NO Δ, NO set-size term
S(ρ)  = c0 + ceil(k · ρ)                                  # per-episode floor c0 + density-scaled cells
cap(ρ) = floor(S(ρ) / overhead) − c0_reserve             # difference-elements recoverable this episode
```

- **Flat & difference-independent (inv 4):** `recon_overhead_bytes` is a pure function of public `ρ` —
  it does **not** depend on realized `Δ`, on `d_size`, or on exact set sizes. The per-episode **floor
  `c0`** is the dominant, conservative term in the **synced-dense regime** that dominates the airtime
  sweep (`Δ≈0`): a difference-proportional model would bill ~0 there (optimistic, forbidden). This
  **resolves the round-2 contradiction**: there is **no `max(est,realized)` and no Δ-triggered fallback
  surcharge** — overflow is modeled as a *throughput cap*, not extra bytes.
- **Overflow → circulation cap, not bytes:** if the realized symmetric difference exceeds `cap(ρ)`, the
  episode reconciles at most `cap(ρ)` novel blobs; the remainder carries to future contacts. This caps
  per-episode novel transfers and **reduces circulation** (the measured haircut). `recon_capped=True` is
  recorded as an internal metric (it does **not** change wire bytes).
- **Billed on EVERY funded episode, even when zero blobs move** (the `Δ≈0` synced regime is exactly
  where `c0` must still be paid) — the engine must bill `recon_overhead_bytes(ρ)` per contact
  **regardless of whether any blob moves** (not gated behind `if moved:`), else the optimism silently
  returns.
- **Billing order:** `recon_overhead_bytes(ρ)` consumes the episode's airtime budget **before** blob
  transfers are billed, so it genuinely reduces the airtime available to move blobs (and cannot push
  utilization > 1.0).
- **Parameters cited, not calibrated:** `recon_cell_bytes` (8 B minisketch / preset for IBLT), `c0`,
  `k`. Swept as a band (§4); never presented as measured.

**Determinism & bit-identity:** new fields default to **off** (`recon_cell_bytes=0`), and the recon-off
path makes **zero RNG draws** (no branch consumes `self.rng` before its conditional, mirroring the
existing `_mixing_on`-style guards) — so every existing slice-1/2/3/4 number stays **bit-identical**.
Recon-on is an opt-in flag/preset on the P0 airtime sweep. The overflow cap is **deterministic**
(a function of `Δ` vs `cap(ρ)`), not sampled — no new variance source, mirroring how `p_fail` is applied
as a deterministic mean.

## 4. What we measure

Bounded re-run (low reps, capped density — the engine is super-linear in crowd size) with reconciliation
**ON vs OFF**:

- **Circulation haircut:** circ/min(on)/circ/min(off) vs density — two effects compose: the airtime the
  flat `S(ρ)` schedule consumes, **plus** the per-episode `cap(ρ)` throttle when differences exceed the
  schedule. *How much of the P0 optimistic budget was free reconciliation?*
- **Capped-episode rate:** fraction of episodes hitting `cap(ρ)` vs density / schedule.
- **2-parameter sensitivity band:** sweep **both** uncalibrated axes (`recon_cell_bytes` × `k`), OR
  report the haircut as **linear in `recon_cell_bytes`** for rescaling — β-knee discipline applied to
  **both** uncalibrated params.
- **Monotonicity sanity gate:** at every swept density **circ/min(on) ≤ circ/min(off)** within CI, and
  the α=0 / cap=∞·ttl=∞ control arms' qualitative behavior is unchanged. A violation is a **billing
  bug**, not a finding — guaranteeing by test (not assertion) the §5 "can only shrink the budget" claim.

Updates the P0 airtime doc with a recon-on column/note and flips the fidelity-table row to *"overhead
modeled (cited, uncalibrated, flat density-scheduled floor)."*

## 5. Invariant & honesty check

- **Inv 2/3:** sketch + seen-nf carry **opaque IDs/hashes only**; no addressing/sender/recipient. ✔
- **Inv 4:** the wire is a **flat density-scheduled padded schedule** keyed to public `ρ` only —
  **independent of `Δ`, `d_size`, and exact set sizes** (§2.2/§3). A difference- or set-size-adaptive
  wire is explicitly forbidden. Spec obligation (the sim bills `S(ρ)` but does not model wire framing).
- **Poisoning defense** keyed to ephemeral session only — no per-device identity hook.
- **Strictly conservative, by test:** the cost is `Δ`-independent and only ever *added* to airtime /
  *subtracted* from per-episode novel transfers; the monotonicity gate (§4) guarantees it can only make
  the budget **smaller/more honest**. Every number stays an UPPER BOUND (cited-not-calibrated; iOS
  asymmetry + no-prefix-carry are named optimistic gaps).

## 6. Out of scope / deferred

- **Real minisketch/IBLT implementation** — this is a *cost model*; byte costs cited from literature,
  on-radio number owed (like B2).
- **Across-contact / cross-peer prefix-carry** — invalid for minisketch (peer-specific); not modeled.
- **Pairing / trust-UX + honest send/trust states (§13)** — sibling spec; client surface, B1-gated.
- **Calibrated `recon_cell_bytes` / `c0` / `k`** — uncalibrated bands only.

## 7. Plan sketch (for the writing-plans step)

1. Add reconciliation-cost config fields (default-inert; **zero RNG draws when off**) + validation; unit
   test cross-slice bit-identity when off.
2. Bill `recon_overhead_bytes(ρ)` **per funded episode (even when zero blobs move), before** blob
   transfer; apply the `cap(ρ)` novel-transfer throttle (deterministic); expose `recon_capped`;
   unit-test billing is strictly additive (no reclassification of unmet-blob bins) and never pushes
   utilization > 1.
3. Scenario: recon-on vs recon-off sweep + **2-D sensitivity band** + **monotonicity gate**; CSV columns.
4. Bounded re-measure (low reps, capped density); update the P0 doc + fidelity-table row.
5. Fan-out code+security review; PR; merge.
