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
- **`clock_trusted` is an EXPLICIT input (build-review round 1).** In the sim it is a configured operating
  mode (`blackout` ⇒ untrusted; default trusted) — when untrusted a node **drops the sender-TTL path and
  relies on `H`** (which clears regardless). Clearance never depends on a clock-trust *estimate*.
- **Gossip-median mesh clock + creation-ts future-clamp — DEFERRED (open problem; NOT shipped as working).**
  *Build review round 1 found the obvious passive estimator is structurally non-functional: a
  trimmed-median of observed `created_at` tracks the center-of-mass of message **ages**, not wall-clock
  "now", so `|local_now − median|` grows with elapsed time and flags even a perfect clock as untrusted; and
  the max/freshest `created_at` is forgeable.* A robust **passive** clock-trust signal from the sealed
  `created_at` stream is therefore an **open problem**, deferred to a later PR. It is gated OFF and not
  relied upon; **the clearance guarantee (`H`) does not need it.** (A real client still needs *some*
  clock-trust signal to decide `clock_trusted` — flagged as the open follow-up, not solved here.)
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
  premature deletion from a backdated ts / fast clock is **not fixed** here and is stated; (4) `clock_trusted`
  is an explicit operating-mode input — a working **passive** clock-trust estimator is **DEFERRED as an open
  problem** (the median-of-`created_at` approach is non-functional; clearance does not depend on it); (5) the
  future-clamp is likewise deferred (it depended on the median) — forged-future on a *trusted* clock is a
  residual that `H` still clears.
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

---

# P3 — PR-2: density-adaptive hold-budget (load-adaptive clearance)

**Version:** v0.1 — 2026-06-28 · **Roadmap:** P3 — PR-2 (the §6/line-142 "density-adaptive retention
knobs beyond hop-energy" deferred from PR-1) · **Builds on:** PR-1 (local hold-budget `H`).

## P2.1 Problem

PR-1 ships a **fixed** hold-budget `H`. But the mission spans two regimes a single fixed `H` cannot both
serve: a **thin** blackout network (few nodes, sparse contacts) needs a **long** hold so a blob reaches the
component before it is dropped (delivery floor); a **dense** crowd fills the bounded buffer and needs a
**short** hold so the soup sheds load before it sits saturated at `cap` (constant eviction churn → honest mail
force-evicted; and before an injection flood is amplified). **No single constant `H` is good in both regimes
at once** — pick `H` small and the sparse network under-delivers; pick `H` large and the dense buffer stays
saturated. PR-2 makes `H` **load-adaptive** so each node self-regulates from local load without per-venue
hand-tuning. (The hard `cap` + eviction make literal overflow impossible; "overflow" throughout means
*sustained saturation*, not exceeding `cap`.)

## P2.2 Mechanism (default-inert)

A held blob at node *i* is dropped once `local_now − local_receipt_time ≥ H_eff_i(t)`, where the effective
hold-budget shrinks with **local buffer occupancy** (a clock-free, locally-observable load signal):

```
occ_i(t) = len(buffer_i) / buffer_cap            ∈ [0, 1]
H_eff_i(t) = H_min + (H_max − H_min) · (1 − occ_i^k)        (k ≥ 1, shape; default k = 1)
```

- **Empty buffer (`occ→0`) ⇒ `H_eff→H_max`** — hold long, protect delivery exactly when the network is
  thin. **Full buffer (`occ→1`) ⇒ `H_eff→H_min`** — shed fast, protect against overflow when dense.
- `k = 1` is linear in occupancy; `k > 1` **holds near `H_max` until the buffer is nearly full, then sheds
  sharply** (shed late — don't pay delivery cost until storage is actually pressured). Monotone ↓ in `occ`.
- **New config (all default-inert):** `hold_budget_adaptive` (bool, default `False`), `hold_budget_min`
  (`H_min`), `hold_budget_max` (`H_max`), `hold_budget_shape_k` (default 1). Off ⇒ PR-1's fixed `H`
  (`hold_budget`) is used unchanged ⇒ **bit-identical** to PR-1/legacy. When on, `hold_budget` is ignored.

## P2.3 Invariants preserved (must verify, not assert)

- **Offset-invariance preserved (the PR-1 crown jewel).** `H_eff` is still compared against
  **elapsed-since-receipt**, and `occ_i` is a count, not a clock — so a constant RTC skew still cancels.
  A behind-clock node (offset −1e6) must still clear under adaptive `H`. (Re-run the PR-1 behind-clock test
  with adaptive on.)
- **Bounded clearance.** `H_min ≤ H_eff ≤ H_max` always ⇒ realized honest lifetime ∈ `[H_min, H_max]`
  (replaces PR-1's clean `≤ H`; the monotonicity gate becomes a **band**, stated honestly).
- **Monotone load-shedding.** `occ ↑ ⇒ H_eff ↓` (unit-test the curve) ⇒ occupancy is self-limiting:
  the fuller the buffer, the faster it drains, so it spends **less time saturated at `cap`**. NB the hard
  `cap` + oldest-by-creation eviction **already make instantaneous overflow impossible** — what adaptive
  reduces is *sustained saturation* (the buffer sitting at `cap` → constant eviction churn → honest mail
  force-evicted). The win runs through **interior** `H_eff` values (the feedback loop equilibrates occupancy
  below `cap` at an interior `H_eff`), not a pinned endpoint — that is what makes the curve (and `k`) earn it.
- **Blackout clearance preserved.** `H_eff ≤ H_max < ∞` ⇒ the soup still clears in a blackout (untrusted
  clock, future-dated ts) — adaptivity only ever shortens vs `H_max`.

## P2.4 Honest caveat (the load-shedding attack — state it, don't hide it)

Load-adaptive shedding is **adversary-inducible**: an attacker who inflates a victim's buffer occupancy
(by injecting blobs) shrinks that node's `H_eff` and can force **premature drop of honest mail**. This is a
real, disclosed trade — adaptive `H` buys sustained-saturation/eviction-churn resistance at the cost of an
injection-driven early-drop. The **only** thing bounding the attack is the **P2 token rate-limit** (how fast
an adversary can inject). Honest framing: **graceful degradation under load, bounded against adversarial
inflation only as well as the P2 token gate bounds injection.** A pure flood with no admission control would
let an attacker weaponize the shedding — so PR-2 is only sound *on top of* P2's token gate.
- **Damage outlasts the burst (newly adversary-triggerable in PR-2).** An `H`-forced drop writes the
  seen-record (`seen[bid]=now`), so a blob dropped early via a shrunken `H_eff` is **seen-locked at that node
  for ~`seen_window` (≈`H_max`)** — long after the injection burst ends and `occ` recovers. So the token gate
  bounds the *rate* of forced drops, **not their duration**: a rate-limited attacker still accumulates
  persistent honest-mail exclusions. (PR-1's fixed `H` could not be shrunk on demand; this lever is new to
  PR-2.) Disclosed here, in the README fidelity row, and tracked — not buried.

## P2.5 What we measure (bounded — low reps, capped density)

The **honest headline (a TRADE, not strict dominance)**: compare three arms — fixed-`H_min`, fixed-`H_max`,
and adaptive — on two regimes:
- **(a) dense storage** — **time-averaged held** over the run (storage-*time* pressure, since the hard `cap`
  makes instantaneous occupancy meaningless), with a **finite** `H_max` (no `H_max=∞` saturation tautology).
  Adaptive's time-avg held is **far below** fixed-`H_max`'s and only **slightly above** fixed-`H_min`'s (which
  holds ~nothing) — so adaptive **captures most of `H_min`'s storage hygiene**, and the win runs through
  **interior** `H_eff` (measured), not a pinned endpoint.
- **(b) sparse delivery** — `ttl = window` (so the cohort is fair-chance), `H` binding. Adaptive **matches
  fixed-`H_max`** delivery (occ≈0 ⇒ `H_eff`≈`H_max` locally) while fixed-`H_min` loses it.

**The honest conclusion: no single GLOBAL fixed `H` is good in both regimes — `H_min` starves sparse
delivery, `H_max` saturates dense storage — and adaptive captures the favorable end of EACH from LOCAL
occupancy, without a global pre-commit.** It does **NOT strictly dominate**: a node holds slightly more than
fixed-`H_min` would (the residual storage cost of staying responsive). The full per-node benefit is realized
in a **heterogeneous / time-varying** network where nodes face different loads at once; an end-to-end
heterogeneous-network win is a **noted follow-up** (the bounded tests demonstrate the per-node mechanism, the
interior-`H_eff` dynamics, and the two single-regime trades — not a heterogeneous-network end-to-end result).

## P2.6 Tests

Default-inert bit-identity (adaptive off ⇒ PR-1 exact, full `run_one` result); `H_eff` monotone in `occ`
and bounded in `[H_min,H_max]` (+ `k>1` holds nearer `H_max` at mid-occupancy); **offset-invariance through
the adaptive ENGINE** (forced −1e6 offset AND engine-drawn `clock_skew_sigma=1e5`, blackout ⇒ clears to 0 —
not a buffer-literal); blackout clears with adaptive on; the **trade headline** (dense time-avg held:
`H_min ≤ adaptive < H_max` with adaptive ≪ `H_max`, AND `H_eff` provably **interior** during the run;
sparse delivery: `adaptive ≈ H_max > H_min`); determinism.

## P2.7 Out of scope (PR-2)

- Youngest-by-real-age eviction-policy redesign (design §16) — needs its own injection-adversary model;
  deferred to a follow-up (current oldest-by-creation eviction is unchanged here).
- Price/token-discount adaptivity (the "price knobs" half of §16) — P2/P5 territory, not retention.
- A robust *adversarial* occupancy signal — PR-2 uses raw local occupancy; hardening it against the
  load-shedding attack beyond the P2 token gate is out of scope (disclosed in P2.4).
