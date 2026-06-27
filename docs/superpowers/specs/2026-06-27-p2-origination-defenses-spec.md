# polleneus — P2 PR-2: Effective origination defenses (venue-wide cover floor + probabilistic license)

**Version:** v0.4 — 2026-06-27 (design-review rounds 1-2 + build-review round 1: which-root adversary) · **Roadmap:** P2 — PR-2 of 3
**Parent design:** [polleneus v0.5 §10](2026-06-25-polleneus-design.md#10-anonymity-engineering--measured-not-assumed)
· **Builds on:** slice-3 PR-1 (source-localization apparatus) + PR-2 (the *cheap* defenses, measured **not credited**).

> **Two honest starting points.**
> 1. Slice-3 PR-2 measured the cheap defenses (mixing `λ=0.05`, gate `G=3`) as **not credited** — they
>    don't cut the ~30 % source-localization leak.
> 2. **Design-review round 1 corrected this spec's own first draft.** The v0.1 mechanism (a node emits
>    its own dummy roots from its own position before sending) is **content-hiding, not position-hiding**:
>    the slice-3 estimator localizes a **NODE by position**, and every root from node X — real or dummy —
>    points to node X. So self-dummies hide *which* blob is real, **not** *who threw the bottle*. v0.1's
>    headline metric `rank-1 → 1/(1+cover_count)` was literally **1/K — the cover-ratio §10 explicitly
>    BANS** as the in-app number. **That mechanism is removed.** v0.2 models what §10 actually sanctions.

## 1. Problem & why this PR

A passive receiver-grid adversary localizes the **originating NODE** of a flood (slice-3 PR-1: ~29 %
exact-catch, ~35× the 1/N floor) because the real blob is the **spatial seed** of its own spread,
against an **empty first-sighting background**. The only thing that makes an origination "one root among
many" *in the position sense* is **other nodes being plausible originators**. So the defense that can
work is a **non-empty background of OTHER nodes' roots** — supplied by a **venue-wide cover floor** — not
the originator's private dummies.

## 2. The mechanisms (parent §10, modeled FAITHFULLY)

- **Venue-wide, always-on, fixed-rate self-loop cover floor (the primary mechanism).** **Every** node
  continuously emits byte-uniform self-loop dummy roots **into the soup** at a fixed venue-wide Poisson
  rate (Loopix identical-rate precondition, §10). These dummies **propagate and are re-shared like any
  blob** (sealed to the emitter's own key; trial-decrypt fails for everyone else; real-vs-dummy hidden),
  so the first-sighting graph contains **roots from many distinct nodes at all times**. A real
  origination then appears as **one node among many plausible-originator nodes** — genuine **position**
  cover. *(Bends inv 3 — self-roots > relays — the §10/§19 pre-sanctioned bend; gated to sparse/cover
  mode, every root byte-uniform.)*
  - **Why this differs from the removed v1 mechanism:** the cover comes from **OTHER nodes'** roots, not
    the originator's own; it is **always-on at a fixed rate** (no pre-send burst → no fingerprint, no
    isolation-cadence tell); and the dummies **enter and spread through the soup** (a non-propagating
    self-loop that stays at the emitter gives *no* first-sighting cover).
- **Probabilistic, time-bounded origination license (liveness, not leak).** Origination probability
  rises with relayed/witnessed novelty, **floored > 0, ceiled at max latency T — never deadlocks**
  (unlike the v0.3 hard gate that self-deadlocked in sparse venues, whose "send anyway" fallback was
  itself a tell). **Honest scope:** this is measured for **deadlock-freedom + cadence-invariance**, NOT
  as a leak reducer — as a leak defense it is **strictly weaker than the already-null hard gate**, so we
  do not expect (or claim) a leak drop from it; its value is liveness and closing the isolation oracle.
- **Self-loops keep emitting when isolated** (UX lag/hysteresis) → an attacker jamming a target reads no
  cadence change (isolation-oracle closure) — measured as a **cadence-invariance** check, not a leak number.

## 3. The sim model (the measurable deliverable)

Extend the slice-3 anonymity apparatus, **default-inert**:

- **Cover-floor arm + the WHICH-ROOT adversary (round-3 fix — the metric must model §10's ACTUAL
  threat).** All nodes emit propagating byte-uniform dummy roots at rate `cover_rate`. *(Round 2's
  "mixed-graph" estimator was proven a denominator artifact: it still scored the **real blob's own
  hearings** and merely enlarged the candidate-node list, so a non-emitting padding null reproduced the
  whole "credit" — cover moved rank-1 by exactly 0. It did NOT do real-vs-dummy inference. Removed.)*
  The faithful adversary:
  - **Per-root emitter localization.** Each root (real or dummy) floods from its own emitter, so the
    adversary localizes **each root's emitter** from **that root's own** first-sighting hearings (not the
    real blob's). This is the only way dummies enter the metric on equal footing with the real root.
  - **Real-vs-dummy uncertainty under the STRONGEST realistic signal.** The adversary does **not** know
    which root is real, but — to avoid *over*-crediting cover — we model a **timing-aware** adversary
    (the conservative/strong direction): it knows the **approximate real-origination time** `t*` (a
    realistic out-of-band capability) and treats as *plausibly-real* only roots whose inferred
    origination time lies within a window `±Δt` of `t*`. Cover therefore helps **only** if *other*
    emitters' dummies genuinely coincide in time **and** space with the real send — real K-anonymity,
    not denominator padding.
  - **Metric = rank of the TRUE EMITTER among the distinct emitters of the *plausibly-real* root set**,
    at a **fixed, consistent denominator** for cover-OFF and cover-ON (the round-2 artifact was an
    inconsistent denominator). A floor that adds no temporally-and-spatially-coincident emitters near the
    true source gives **no** credit. **Not the banned 1/K** (that was content-rank among one node's own
    roots; this is the true *emitter's* rank among *distinct emitters* the adversary cannot rule out).
- **The swept variable is the COVER FLOOR rate / venue density.** The question: can a venue-wide floor of
  propagating roots produce **distinct emitter nodes whose roots are, to the timing-aware adversary,
  indistinguishable from the real origination** — putting the true source in a genuine K-anonymity set of
  emitters — or does the adversary still pin it (because few/no dummies coincide with the real send in
  time and space)?
- **License arm:** probabilistic time-bounded release; measured for deadlock-freedom (always fires by T,
  even sub-percolation) + cadence-invariance; its rank-1 reported but **not** expected to beat the null hard gate.
- **Credit gate = slice-3 PR-2 gate + the corrected controls (mandatory):**
  - must-localize (the which-root estimator must localize cover-OFF at the fixed denominator), same-detected-set
    intersection (survivorship), per-arm TTL=∞ control (a drop that dies there was message-dropping), cost
    (delivery + t50). **All retained.**
  - **FIXED DENOMINATOR + GROWN-CANDIDATE-NULL (replaces the round-2 control, which was proven inverted —
    it *required* the denominator growth that manufactured the artifact).** Cover-OFF and cover-ON are
    scored against the **same fixed candidate denominator**, and a **non-emitting padding null** (grow the
    candidate set with zero dummies) **must credit ~0**; the cover arm is credited **only for the rank-1
    increment above that null**. A credit requires the true emitter's rank to rise from **genuine
    temporally-and-spatially-coincident dummy emitters** (real K-anonymity), never from denominator size.
  - **Distinct-emitter + co-location guard (retained, necessary-not-sufficient):** an originator's own
    roots are never counted as distinct candidate emitters (rejects the v1 own-root 1/K trap).
- **Airtime cost (venue-wide):** the cover floor's dummies/min are billed against the §11 airtime budget
  (P0 apparatus) — a cover floor that floods is **not free** and competes with real delivery (a genuine
  second inv-1/§11 tension, reported, not hidden).

## 4. What we measure

- **Does a venue-wide cover floor cut the position leak? (measured by the which-root, timing-aware
  adversary.)** True emitter's rank-1 **among the distinct emitters of the plausibly-real root set**, vs
  `cover_rate` and density, at a **fixed denominator**, credited **only** through the gate. Falsifiable
  expectation: rank-1 falls **only if** the floor produces emitters whose roots coincide with the real
  send in **time AND space** — and **may NOT**, if the timing-aware adversary rules out most dummies.
  **Mandatory grown-candidate-null control (the round-2 lesson):** a non-emitting padding null (grow the
  candidate set with zero dummies) must credit **~0**; the cover arm is credited only for the increment
  **above** that null. The must-localize control runs the **same** estimator cover-OFF at the same fixed
  denominator. **A null result remains an honest, plausible (perhaps likely) outcome** — and is now a
  *real* test of §10 cover, immune to the denominator artifact.
- **The sparse-mode tension (honest):** §10 invokes cover for the sparse/cliff venue — but that is exactly
  where there are **fewest other nodes** to supply position-cover and where the airtime cost bites hardest.
  Measure and report rank-1 + cost across density, **including** the sparse regime where cover is weakest.
- **License:** deadlock-freedom (fires by T at all densities incl. sub-percolation) + cadence-invariance.
- **Cost honesty:** cover dummies/min vs the §11 ceiling; delivery + t50 for every arm.
- **The verdict per mechanism — credited or NULL — with the gate's reason and the cost.**

## 5. Invariant & honesty check

- **inv 2/3/4:** dummies are byte-uniform, sealed to the emitter's key, propagate like any blob → soup
  uniform; real-vs-dummy hidden. The venue-wide floor **bends inv 3** (self-roots > relays) — the
  **§10 (line 234) + §19 pre-sanctioned bend**; gated to sparse/cover mode. *No NEW bend is introduced*
  (the v0.1 originator-burst mechanism, which WAS a new fingerprint, is removed), so this stays within the
  parent design's existing approval — **noted, not re-escalated.**
- **The banned metric is gone.** The credited number is the **source-estimator node-rank** (§10's
  mandated measure), never the cover-ratio 1/K. The new distinct-node gate control makes a co-located
  artifact uncreditable by construction.
- **License is honestly scoped** as liveness/oracle-closure, NOT a leak reducer (it's weaker than the
  null hard gate) — no leak-drop claim.
- **Null results published.** Every credited gain is an **UPPER BOUND on protection** (single-event
  external-passive only; intersection = PR-3, insider deferred). PHY device-linkage ≈ 1.0 carried.

## 6. Out of scope / deferred

- **Intersection-resistance** of cover (does a floor survive multi-session intersection?) — P2 PR-3.
- **Insider / compromised-relay** adversary — deferred (§10 scope).
- Real PHY USRP device-linkability — owed (B2 / §16-P6).
- Exact license novelty/discount curve beyond floored-and-ceiled — research (§17).

## 7. Plan sketch (for writing-plans)

1. Config: `cover_rate` (venue-wide floor), license params, `cover_mode` gating to sparse — all default
   off → bit-identical; zero new RNG on the off path.
2. Overlay: all nodes emit propagating byte-uniform dummy roots at `cover_rate`; probabilistic
   time-bounded license release. Default-inert.
3. Adversary: the WHICH-ROOT timing-aware estimator — localize EACH root from ITS OWN hearings; rank the true emitter among distinct emitters of the plausibly-real (within ±Δt of t*) root set at a FIXED denominator. Plus a mandatory grown-candidate (non-emitting padding) NULL control crediting ~0.
   (real + dummies), NOT told which is real; output = rank of the true originator among the distinct
   emitter nodes. Reuse the slice-3 estimators (reachability/first-spy) over the union root-set.
4. Scenario: cover-floor + license arms scored by the mixed-graph estimator; the **distinct-node
   co-location gate control**; must-localize runs the SAME mixed-graph estimator on the defenses-off
   baseline; node-rank-1 vs `cover_rate`/density; deadlock-freedom + cadence-invariance; venue-wide
   airtime cost vs §11.
5. Tests: bit-identity off; the mixed-graph estimator localizes the true node cover-OFF (must-localize)
   and the metric MOVES with cover_rate (not structurally blind); the co-location control REJECTS an
   originator's own-root tie (pins the v1 trap); node-rank among distinct emitter nodes (never 1/K);
   license never deadlocks; cover airtime rises with `cover_rate`; gate refuses a message-dropping/
   co-located "gain"; determinism.
6. Bounded measure (low reps, capped coverage+density); document the **honest verdict** (credited or
   NULL, with cost + the sparse-mode tension); update the slice-3 README + B2/B3 notes.
7. Fan-out code+security review; PR; merge.
