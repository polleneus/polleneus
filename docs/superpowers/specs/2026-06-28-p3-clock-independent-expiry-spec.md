# polleneus — P3: Clock-independent expiry (hop-energy + gossip-median mesh clock)

**Version:** v0.3 — 2026-06-28 (design-review rounds 1-2 folded in: local hold-budget = clearance; hop-energy = anti-amplification) · **Roadmap:** P3 — PR-1
**Parent design:** [polleneus v0.5 §6](2026-06-25-polleneus-design.md#6-lifetime--retention)

> **Why this serves the mission.** polleneus is for *when things go down* — and in a blackout there is
> **no NTP, RTCs drift, and the sender-signed `creation-ts` is forgeable.** The authoritative expiry test
> `local_clock ≥ creation-ts + TTL` is then untrustworthy. The dangerous failure is **immortality** — the
> soup never clears — which arises from a **future-dated `creation-ts`** and/or a **receiver clock running
> behind true time** (NOT a backdated ts or a fast clock — those cause *premature deletion*, a separate
> problem neither backstop fixes). §6 names two backstops; the sim models neither. This PR makes them real
> and measures that **honest soup still clears under untrusted time.**

## 1. Problem & current state

The sim models absolute TTL, bounded-buffer eviction (oldest-by-creation), and the sliding-window
seen-record (`W = ttl + margin`). But **`Blob.hop_energy` is carried-but-never-read** (`blob.py:12`,
no reads in engine/buffer/scenario), and there is **no clock model** — every node uses true global time.
So the sim cannot exhibit the blackout immortality failure or its fix. P3 PR-1 closes that gap.

## 2. The mechanisms (parent §6, corrected after two review rounds)

The clearance guarantee must rest on something a node can trust **without a trusted absolute clock**. The
key insight: a node's **elapsed time since it received a blob is offset-invariant** — a constant RTC skew
cancels in `(local_now − local_receipt_time)` — so a *local hold-budget* survives clock skew, whereas the
absolute test `local_now ≥ creation-ts+TTL` does not. So we separate **two genuinely independent budgets**
(this resolves the v0.2 "single B vs two budgets" contradiction):

- **(R1) Hop-energy — anti-amplification spread cap (§6's "loses 1 per re-share").** A receiver stores the
  copy with `energy = sender_energy − 1`; a copy that would arrive at energy 0 is not stored. This bounds
  the spread *radius/amplification* to ~`B` hops. **It is NOT the clearance mechanism** — in the
  store-carry-forward engine there is no "re-broadcast" event to decrement a *held* copy, so a
  saturated/frontier copy at residual energy would persist; hop-energy alone does not clear the soup.
  (This is the round-2 finding: hop-energy is a spread bound, not an expiry.)
- **(R2) Local hold-budget `H` — the clock-independent expiry that actually clears the soup (the
  headline).** Each node drops a held blob once **`local_now − local_receipt_time ≥ H`**, regardless of
  the absolute clock or `creation-ts`. Because elapsed-since-receipt is **offset-invariant**, this fires
  correctly even on a badly-skewed / behind clock — so it is exactly the blackout backstop. Drop **writes
  the seen-record** (`seen[bid]=now`, like expire/evict). `H` is sized so a blob reaches the component
  before it expires (delivery preserved) yet `H ≤` a sane maximum hold (clearance bounded). `created_at`
  is never touched; eviction/`expires_at` math unchanged.
- **Honest scope of R1+R2 (corrected — no false impossibility).** R1+R2 **clear HONEST soup** and cannot
  make an honest node over-retain (an honest node drops by `H` no matter what). They are **best-effort
  availability backstops, NOT authenticated expiry**: `hop_energy` is an unauthenticated, hop-mutable wire
  field, and in an *open flood* any holder can re-broadcast a blob indefinitely regardless of any field —
  so a **malicious relay keeping a blob alive is UNPREVENTABLE**. We do **not** claim "a relay cannot
  extend life" (the v0.1 claim was false). The honest claim: *honest soup clears; honest nodes cannot be
  made to over-retain; a malicious holder's life-extension is an unpreventable open-flood liveness attack.*
- **Sender-TTL path (respect the sender's intent when the clock is trustable).** When `clock_trusted`, a
  node also expires at `local_now ≥ creation-ts + TTL` (the sender's authoritative, ≤7 d limit). This is
  **in addition to** R2; the hold-budget `H` is the floor that holds when the clock is *not* trusted.
- **Gossip-median mesh clock — a clock-TRUST / premature-deletion guard (NOT a clearance mechanism).**
  Each phone estimates a **trimmed-median of `creation-ts` values observed in its own relay/trial-decrypt
  stream** (no origin oracle — sealed-sender exposes only per-blob `created_at`), and sets itself
  **`clock_untrusted` from the OBSERVABLE `|local_now − gossip_median| > clock_trust_threshold`** (never a
  ground-truth offset it cannot see). When untrusted it **drops the sender-TTL path and relies on `H`**
  (which clears regardless). It also drives the §5 ratchet clock. Clearance never depends on it.
- **Creation-ts future-clamp — a COARSE backstop against EXTREME future-dating only.** A node clamps a
  blob whose `creation-ts` is implausibly far ahead of its gossip-median (used only to stop a forged-far-
  future ts from defeating the *sender-TTL* path). It is deliberately **loose** (so a lagging-median /
  cold-start node never false-rejects honest-fresh mail); moderate forgery is bounded not by the clamp but
  by the clock-independent hold-budget `H`. Clamping is **admission control at `offer()`** (adjust/reject
  on receipt), **not** a per-step expiry condition.
- **Expiry predicate (R2 is the unconditional ceiling):**
  `expired = (local_now − local_receipt_time ≥ H) OR (clock_trusted AND local_now ≥ creation-ts+TTL)`.
  The hold-budget `H` fires regardless of clock; the sender-TTL path only when trusted. Both only ever
  *shorten* an honest blob's life.

## 3. The sim model (the measurable deliverable)

All **default-inert** (existing slices bit-identical): `hop_energy_init=None`, `clock_skew_sigma=0`,
clamp/median off ⇒ perfect global clock + carried-but-ignored energy = today. Clock offsets draw from a
**fresh disjoint RNG namespace** (`cfg.rng(10,i)`), gated on `sigma>0`.

- **Local hold-budget `H` (the clearance mechanism):** per-`(node,id)`, record `local_receipt_time`; drop
  when `local_now − local_receipt_time ≥ H` **and write `seen[bid]=now`**. Elapsed-since-receipt is
  offset-invariant ⇒ fires under any clock skew. `H` configurable (`hold_budget`, default `None`=off).
- **Hop-energy `B` (anti-amplification spread cap, independent knob):** per-`(node,id)`, receiver inherits
  `sender_energy−1`; a copy that would arrive at 0 is not stored (`hop_energy_init`, default `None`=off).
  Bounds spread radius; does NOT drive clearance.
- **Clock model (scoped to EXPIRY ONLY):** each node gets an RTC offset (`cfg.rng(10,i)`, gated `sigma>0`);
  its "now" = true time + offset. **The offset affects ONLY the expiry/ratchet comparison — never
  contact/causality/acquisition/measurement timing, which stay true global time** (else the delivery graph
  corrupts). Note the offset cancels in `H`'s elapsed-since-receipt (so `H` is skew-robust) but not in the
  absolute sender-TTL test (which is why we need `H`). A `blackout` flag allows **future-dated**
  `creation-ts` (own RNG namespace) and removes NTP/trusted clock.
- **Gossip-median + clamp:** trimmed-median over observed `created_at`; `clock_untrusted` from the
  observable `|local_now − median|`; the future-clamp is **admission-time** (adjust/reject on receipt),
  not an expiry branch, and is loose (no honest-fresh false-reject).
- **Seen-window sizing:** a blob's clearance lifetime is now bounded by `H` (not TTL), so size the
  seen-window to **`H` (+ margin)**, not `ttl + margin`, or the no-resurrection guarantee degrades to
  best-effort — **state which**. The pruning clock is the node's **local elapsed** time.

## 4. What we measure

- **Blackout soup-clearance (the headline):** future-dated `creation-ts` and/or behind-clocks, no trusted
  clock. Fraction of HONEST blobs still circulating at `t ≫ maxTTL`, **hold-budget `H` ON vs OFF**.
  Expectation: **OFF → immortal tail** (untrusted clock ⇒ sender-TTL never fires ⇒ held copies persist);
  **ON → clears by `H`** regardless of skew. *The headline: honest soup clears in a blackout iff the local
  hold-budget is binding — and because `H` is elapsed-since-receipt, it clears even on a behind clock.*
- **Delivery cost — the two independent budgets:** sweep `H` (temporal) for the delivery-preserving floor
  measured against the engine's **temporal hop-depth** (not static diameter), and separately sweep `B`
  (spatial spread cap); show a setting where delivery is preserved AND the soup clears.
- **Gossip-median + clamp:** median error vs true time using **only observed `created_at`**; a sweep over
  the **number of independent honest senders** + a **cold-start** case (the median is weakest in the sparse
  blackout the mission targets — document the minimum population and sub-population default). Threshold
  framed as a **minority of observed blob volume** (bounded only by the §9 token rate-limit, itself dented).
  Confirm the clamp blocks extreme forged-future on the *sender-TTL* path **without** false-rejecting
  honest-fresh on a lagging-median node.
- **Safety monotonicity gate (two-part, corrected):** (a) clearance — realized honest lifetime ≤ `H`
  **unconditionally** (any clock); (b) sender-TTL path (clock-trusted) — realized lifetime ≤
  trusted-TTL + `clock_trust_threshold` (a slow sub-threshold clock *can* extend up to the threshold — the
  bounded residual; not "never extends"). Net honest ceiling = `max(H, trusted-TTL + threshold)`.
- **Resurrection guard:** an `H`-dropped id, re-offered within the (`H`-sized) seen-window, is RejectedSeen
  and does **not** regain energy/lifetime (assert + test); the drop path writes the seen-record.

## 5. Invariant & honesty check

- **No invariant bent for honest nodes.** The hold-budget and hop-energy both shorten only; the clock is
  passive, derived from the opaque `created_at` stream (no new wire field, no routing metadata → inv 2/3/4
  hold). The clock offset is confined to the expiry/ratchet comparison; causality/measurement use true time.
- **Honest scoping (the review's core correction):** (1) `H`+`B` clear *honest* soup and cannot make honest
  nodes over-retain (drop by `H` regardless of clock), but a *malicious* holder keeping a blob alive is
  **unpreventable** in an open flood — claimed plainly, no false impossibility; (2) the sender-TTL path can
  *extend* an honest blob's life by up to `clock_trust_threshold` (bounded residual, not zero); (3)
  premature deletion from a backdated ts / fast clock is **not fixed** here and is stated; (4) the
  gossip-median is a *clock-trust/premature-deletion guard*, **not** the clearance mechanism (clearance is
  `H`, which needs no median); (5) the future-clamp is a *coarse* extreme-forgery backstop on the sender-TTL
  path only, deliberately loose.
- **Forward-looking honesty (for P5):** the clock this PR produces is **biasable toward the future**; the
  P5 time-ratchet **must bound forward jumps / require corroboration before deleting keys**, or a
  timestamp flood could destroy unread mail. Flagged now so P5 inherits the caveat.
- **Default-inert** verified as the first acceptance gate (bit-identity with energy off + sigma 0 + clamp
  off, disjoint RNG namespace).

## 6. Out of scope / deferred

- §5 time-ratchet / crypto deletion (P5) — this PR only supplies the clock; the forward-jump bound is P5's.
- Authenticated/forgery-proof `creation-ts` — out of scope (the point is to tolerate a forgeable ts).
- Robust clearance against a *majority-liar / Sybil* timestamp flood — out of scope (trimmed-median holds
  only for a minority; document the limit).
- Density-adaptive retention/price knobs beyond hop-energy — a later P3 PR.

## 7. Plan sketch (for writing-plans)

1. Config: `hold_budget` (H), `hop_energy_init` (B), `clock_skew_sigma`, `clock_trust_threshold`,
   `creation_ts_clamp`, `blackout` (all default-inert; clock offset + blackout future-dating from disjoint
   `cfg.rng(10,i)` / a separate namespace, gated on the relevant param > 0).
2. Engine/buffer: per-`(node,id)` `local_receipt_time` → drop when `local_now − receipt ≥ H` (write seen);
   per-`(node,id)` hop-energy spread cap (inherit −1, don't-store-at-0); per-node EXPIRY-ONLY clock offset;
   gossip-median over observed `created_at`; `clock_untrusted` from `|local_now−median|`; admission-time
   creation-ts future-clamp; expiry = `H-elapsed OR (clock_trusted AND past-sender-TTL)`. Seen-window sized
   to `H`+margin, pruned on local elapsed. Zero new RNG on the off path; contact/causality clocks untouched.
3. Scenario: blackout clearance sweep (`H` ON/OFF, future-dated ts / behind clocks) + `H` delivery floor vs
   temporal hop-depth + separate `B` spread sweep + gossip-median convergence vs #senders/cold-start + the
   two-part monotonicity gate + the resurrection-guard test.
4. Tests: default-inert bit-identity (first gate); immortal-without-`H` / clears-with (incl. a behind-clock
   node clears by `H`); delivery preserved above the `H` floor; median tracks under a liar minority
   (observed-ts only); clamp blocks extreme forged-future on the sender-TTL path WITHOUT false-rejecting
   honest-fresh on a lagging-median node; clock-trusted path lifetime ≤ TTL+threshold; `H`-drop writes seen
   + no resurrection within the `H`-window; determinism.
5. Bounded measure (low reps, capped density — engine super-linear); document; update README fidelity row
   (energy now binding; clock modeled; honest scope of what it does/doesn't prevent).
6. Fan-out code+security review; PR; merge.
