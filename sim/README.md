# soup_sim — polleneus uniform-soup simulator

Measures **delivery vs node density** (and airtime cost) for the polleneus pure-flooding
"uniform soup", validated against percolation ground truth. This is roadmap **P0**:
*measure, don't assume.*

> ⚠️ **Every number this simulator reports is an UPPER BOUND on real-world delivery.**
> It idealizes the radio (unit-disk links, single-snapshot contention), abstracts
> reconciliation as a byte budget, and treats "arrival == delivery". See *Caveats*.

## Setup
```bash
cd sim
python -m venv .venv
.venv/Scripts/python -m pip install -U numpy pytest        # + matplotlib (optional) for plots
```

## Run
```bash
.venv/Scripts/python -m pytest -q                          # full suite incl. the percolation gate
.venv/Scripts/python -m pytest -m slow -q                  # the heavier airtime end-to-end sweeps
.venv/Scripts/python run.py --preset static-cliff  --out out/cliff.csv   --plot out/cliff.png
.venv/Scripts/python run.py --preset airtime-knee --out out/airtime.csv --plot out/airtime.png
.venv/Scripts/python run.py --preset anonymity    --out out/anon.csv    --plot out/anon.png
.venv/Scripts/python run.py --preset anonymity-defenses --out out/anon_defense.csv  # PR-2: mixing+gate vs baseline
.venv/Scripts/python run.py --preset anonymity-intersection --out out/anon_intersection.csv  # PR-3: rank-1 vs K
.venv/Scripts/python run.py --preset cluster-delivery --out out/cluster.csv  # slice-4: delivery vs clustering
```
`run.py` sweeps mean degree and writes a CSV (with the **full parameter manifest** per row,
so any point is reproducible from the file). `static-cliff` writes the delivery curve;
`airtime-knee` writes the circulated-blobs/min curve and prints the saturation-knee, the
model-uncertainty band (collision vs linear), and the **publish-gate verdict**.

## What it measures (first slice)
The **static, component-reachability** delivery curve: the probability a uniform-random
src→dst pair is connected by some multi-hop path, over a Poisson torus ensemble. This is the
exact quantity the percolation gate validates.

### Headline measured result
- **Connectivity threshold d_c ≈ 4.51** (mean neighbours per radio-disk), recovered as the
  **susceptibility peak** — the test `test_susceptibility_peak_near_threshold_*` asserts the
  peak lands in [4.0, 5.2].
- **Delivery rises steeply through the threshold.** The delivery=0.5 crossing is measured at
  **mean-degree ≈ 4.4** (not the ~6–7 we *assumed* before building — 2D percolation's order
  parameter rises with a small exponent β≈5/36, so the giant component dominates pairs almost
  as soon as it appears). Below ~4 the network is shattered and offline delivery ≈ 0.
- **Takeaway for polleneus:** offline pure-flooding needs roughly **≥ ~5 app-using neighbours
  within radio range** to deliver at all — i.e. a genuinely dense gathering. Below that, the
  soup is disconnected and messages don't cross. (Mobility/airtime only *lower* this ceiling.)

## What it measures (slice 2: airtime & mobile delivery)
Whether BLE **airtime** — not storage — is the scale wall: does delivery saturate and turn
over as a gathering gets denser? The engine runs over **mobile (RWP)** nodes with a
collision-capable airtime model, and the sweep reports **circulated-blobs/min** (accepted
*novel* transfers only — duplicate/already-seen re-offers are not counted), **airtime
utilization**, **delivery ratio**, and a **censoring-aware T50** vs density.

- **Primary model = ALOHA collision:** per-link goodput `throughput·exp(−β·n/n_channels)` over
  `n_channels=3` shared advertising channels. Per-link goodput is monotone; the SYSTEM
  aggregate `n·goodput` has an interior maximum at `n* = 1/β` contenders — so
  circulation **turns over under the collision model**. **β is an UNCALIBRATED free parameter**,
  so `n*` is set by the chosen β, not measured: this apparatus demonstrates that it can *detect*
  a knee when one exists, it does **not** assert real BLE saturates at a specific density. The old
  `1/(1+α·n)` is kept as the **optimistic-bound sensitivity** case (system aggregate plateaus →
  no knee). The two are run side-by-side as a **model-uncertainty band**.
- **Falsifiable prediction (stated up front):** collision ⇒ a knee; linear ⇒ a plateau.
  `test_collision_knee_linear_plateau_distinguishable` (slow) pins it.
- **Contention ≠ connectivity:** `n_contenders` is the co-channel population over a
  carrier-sense radius (`cs_radius_mult·radius`), not the unit-disk degree.
- **Saturation-knee estimator** (`knee.py`): argmax of circulated/min with a local
  quadratic-in-log fit + bootstrap CI; returns **"no knee in range"** (never NaN) when the
  curve is monotone, merely plateaus (the post-peak minimum must fall ≥15% below the peak), or
  the local fit is not concave (no genuine interior max).
- **Binding publish-gate (the honesty guard):** the saturation figure publishes **only if**
  there is a knee AND ≥50% of *unmet* demand at the knee is **contention-bound** AND the
  **α=0** (airtime-free: β=0, α=0, t_setup_slope=0 → constant goodput, flat setup) control does
  **NOT** turn over (else the turn-down is connectivity-caused) AND the **cap=∞/ttl=∞** control
  **DOES still** turn over (the turn-down persisting when buffer/TTL are infinite is what rules
  out a buffer/TTL cause). Otherwise the curve is labelled connectivity/buffer/TTL-limited. This
  makes it impossible to mislabel a storage/connectivity effect as "airtime."
- **Censoring-aware latency:** TTL-expired messages are censored; we report **T50** (time to 50%
  of the fair-chance cohort delivered; `None` when <50% ever arrive) jointly with delivery
  ratio. Delivered-only mean latency is a LOWER bound (survivorship) and labelled as such.

## Airtime provenance (where the numbers come from — all conservative/UPPER-BOUND)
| Parameter | Value used | Source / rationale | Bias |
|---|---|---|---|
| `throughput_ideal` (goodput) | **~100 kbps** headline (12.5 kB/s) | BLE 4.x connection, no Data-Length-Extension; ~1.4 Mbps (BLE 5 2M PHY + DLE) is the optimistic upper sensitivity | conservative headline; report both |
| `t_setup` | 50 ms | BLE connection/handshake floor; short contacts move nothing | — |
| `t_setup_slope` | density-dependent | discovery latency grows with advertiser count (scan-window contention) | optimistic if slope under-set |
| `β` (collision steepness) | **uncalibrated free parameter** | predicted knee `n* = 1/β` reported up front (no `/n_channels`: BLE advertises on all 3 channels per event, so they don't triple capacity); sweep is run across the band | report knee as a function of β |
| `blob_size` | 256 B | one sealed message — sim's modeled size; parent §6 rounds to ~1 KB (circ/min scales ~inversely with blob size, so ~4× lower at 1 KB) | optimistic vs 1 KB |
| contact-duration distribution | RWP, open-field | report the empirical distribution; its tail is **optimistic** vs clustered human-contact traces | optimistic |

## What it measures (slice 3: anonymity / source-localization) — PR-1
Whether a passive **receiver-grid adversary** (covering a fraction f of the arena, the sweep
axis) can **localize who originated** a message under naked pure-flooding — the project's core
privacy promise at the network layer (crypto hides content/addressing, not the physical spread).

> ⚠️ **Every anonymity number is an UPPER BOUND on real anonymity** (a stronger adversary only
> localizes *better*) — never a floor or a guarantee. And this slice models a **single
> origination event against an external passive adversary ONLY**: the dominant real threat —
> a PHY-labeled persistent device under **multi-session intersection** — and **insider/compromised
> nodes** are NOT modeled (deferred). The scope tag travels with every emitted number.

- **Diffusion-source, not radio-triangulation:** the engine floods a component in one step and
  spreads via mobile holders, so localization is epidemic source-estimation. The strong
  estimator is a **reachability-likelihood** (rank candidates by how well their origination
  position + the observed spread explain receiver hear-times); first-spy is the weak reference;
  random-guess is the no-signal floor. Reported = best per message.
- **Capability gate (must-localize):** no exposure number publishes unless the **best**
  estimator demonstrably localizes a **slow-mobility** source under near-total coverage —
  beating the 1/N random floor by ≥10× AND pinning the source to within ~one radio-range (a
  *static* source floods instantly with zero gradient — unlocalizable by anyone). This prevents
  mistaking a weak attack for anonymity. (Empirically first-spy is the workhorse under dense
  coverage; the forward-reachability estimator is the principled diffusion-source variant.)
- **Exposure gate:** "flooding exposes the source" only if best detected rank-1 ≥ max(0.5,
  5×the 1/N random floor) with adequate sample size — a bare "beats random" is vacuous at 1/N.
- **Honesty:** chokepoint placement is the reported (stronger) arm; metrics are conditional on
  detection with the undetected fraction reported (censoring); estimator-quality error is at the
  first-hear position, with the origination-time error + the gap (mobility-cloaking) separate;
  anonymity-set size is always labelled an **upper bound** (never "K-anonymity").
## Anonymity defenses (slice 3 — PR-2)
Two network-layer defenses against the source-localization adversary above, measured at fixed
coverage (`--preset anonymity-defenses`, default f=0.7) and credited only when a drop is *real*:

- **Poisson mixing delay:** each holder waits `Exp(λ)` before it will *forward* a freshly-acquired
  blob, scrambling the hear-time gradient the reachability estimator rides.
- **Receive-before-originate gate:** a node's own origination is held back from forwarding until it
  has relayed ≥G *distinct foreign* messages — so a first-mover origination can't be the spatial
  seed of its own flood. Only the **measured** (gated) cohort is held; an un-gated background soup
  circulates so the network can't deadlock.

> ⚠️ **A defense's credited gain is an UPPER BOUND on its real protection** — it is measured against
> the *same single-event external-passive* adversary, NOT against multi-session intersection or an
> insider. The `defense_scope_tag` saying so travels on every emitted row.

**Why a naive "rank-1 dropped" claim is a trap, and how the gate avoids it:**
- **Same-detected-set intersection** — a defense that merely *slows* the spread shrinks the
  detected set inside the finite window, and a smaller set looks more anonymous purely by
  survivorship. So baseline vs defended rank-1 is compared **only on messages detected in the
  baseline, the defended arm, AND that arm's TTL=∞ control** (same seed → same cohort), with a
  `MIN_INTERSECTION_SIZE` floor below which the result is "inconclusive", not "protected".
- **TTL=∞ control, per defense** — either defense could cut rank-1 just by dropping messages: a
  mixing-delayed blob can hit TTL expiry, and a gate-held origination can expire before it is ever
  forwarded. So **each** arm has its own parallel **TTL=∞ control** (`timing_only` for mixing,
  `gate_timing_only` for the gate) that keeps every blob alive; the gain is credited only if it
  **survives** there (real timing-scramble / structural hiding), else it's labelled *message-dropping*,
  not anonymity.
- **Must-localize baseline (defenses OFF)** — a drop is meaningless if the attack couldn't localize
  the baseline in the first place; the PR-1 capability gate is measured on a **defenses-off** clone
  (not the defended source) and must pass first.
- **Relay-density check** — the gate arm is only trustworthy if nodes actually relayed enough
  foreign traffic (`MIN_RELAY_DENSITY`); a starved gate is an artifact, not a defense.
- **Cost is always reported** — every arm prints its delivery **and** median-latency (`t50`, `nan` =
  the cohort never reached 50% delivery) so a credited anonymity gain is read against what it costs in
  reach/latency. The gate is scored against a *stronger* adversary than the baseline (the
  `origin_vs_relay` estimator is added to the best-of for the gate arms) — the conservative direction,
  making the gate **harder** to credit, never easier.

**Measured result at the shipped defaults** (`mixing_lambda=0.05`, `G=3`, f=0.7): the must-localize
control passes on the defenses-off baseline (the attack *can* localize it), the same-detected-set
intersection clears the floor — and **neither defense is credited: defended rank-1 ≈ baseline, so at
these parameters mixing and the gate do not materially cut the ~30% leak.** Mixing also costs delivery
(~0.45) and latency; the gate is near-free but equally ineffective here. This apparatus is built to
*detect* a real drop and refuse an imagined one — not to assert protection exists. A genuine
defense (stronger λ, larger G, or a different mechanism) remains future work; the honest current
finding is "no credited gain at the cheap defaults."

Defaults ship **OFF** (`mixing_lambda=0`, `originate_gate_relays=0`): the baseline engine and every
PR-1 number are bit-identical unless a defense is explicitly enabled.

## Anonymity intersection (slice 3 — PR-3)
The dominant deferred threat PR-1/PR-2 named but did not model: a persistent device originates **K**
messages and the adversary, **assuming it can link them to one device**, fuses its per-message
rankings. A weak per-message signal sharpens as the true origin stays consistently plausible across
all K while innocent relays are only coincidentally plausible in some. `--preset
anonymity-intersection` sweeps K∈{1,2,4,8,16} at fixed coverage; one engine run per rep serves the
whole sweep (fuse prefixes of a K-message plan). Messages are **staggered in origination time** (each
is an independent geometric constraint), realized via future `created_at` + the engine's
acquisition-time causality.

- **Fusion — Borda (headline) + score-sum (sensitivity):** Borda sums per-message average-ranks
  (scale-free, conservative); score-sum sums per-message normalized scores (≈ Bayesian intersection).
  Both are reported; on divergence the **lower** (more anonymity-favorable) rank-1 is the credited
  headline (never credit the adversary a fusion-rule coin-flip).

> ⚠️ **Linkage is ASSUMED given** — PR-3 does NOT model *how* the K messages are linked (PHY device
> fingerprinting is a separate slice). This is the worst case (parent §10 "assume the handset is
> uniquely labeled"), so the credited number is an **UPPER BOUND on anonymity**. Still single-event-
> per-message-style *external-passive* only; insider nodes and defenses-against-intersection (PR-4)
> are deferred. The `intersection_scope_tag` saying so travels on every emitted row.

**Honesty controls (credit only a real, originator-specific pin):**
- **Fused-random floor** — fuse K random-guess vectors; its rank-1 must stay ~1/N (fusion itself
  creates no signal). The credited gain is the climb above this floor.
- **Decoy-centrality confound (make-or-break)** — fusion could pin whoever is most *central* in the
  diffusion, not the originator. The decoy = the **highest distinct-foreign-relay innocent node**; the
  same K-message fusion is run against it. Credit requires the originator's fused rank-1 to beat the
  decoy's by `DECOY_MARGIN` — else the result is "confounded by centrality," discounted not credited.
- **Must-localize (inherited)** — the per-message estimator must already be capable (PR-1 gate). Note
  this capability control uses PR-1's *best-of* estimator, while fusion here is reachability-only — so
  the capability bar is, if anything, easier to clear than the fused attack (the conservative direction).
- **Decoy control under both rules** — the centrality check is run for Borda **and** score-sum and the
  worst (higher) decoy rank-1 is used, so it is never weaker than the rule that produced the credited
  (lower) headline.
- **Powered** — ≥ `MIN_INTERSECTION_SAMPLES` (device×seed) fusion samples, else "underpowered."
- **Control A is wired into the verdict** — the exposure threshold is taken over the *measured*
  fused-random floor (`max(1/N, fused_random_floor)`), so if fusion ever manufactured a high floor the
  bar rises with it; credit is the climb **above the floor fusion actually produced**.

**Measured result at the shipped defaults** (`--preset anonymity-intersection`, seed 12345, f=0.7, 8
tracked devices × 12 reps = 96 fusion samples, K∈{1,2,4,8,16}): must-localize passes, the fused-random
floor stays ~1/N (≤0.01) and the central-decoy stays at **0.00 at every K** (centrality ruled out) — and
the sender's fused rank-1 **climbs 0.09 → 0.16 → 0.22 → 0.45 → 0.72** as K goes 1→16, crossing the 0.5
exposure threshold between K=8 and K=16. Borda and score-sum **coincide** at this powered default (the
`min()` "credit the lower" rule then costs nothing; on smaller-sample seeds where they diverge it credits
the more anonymity-favorable one). At K=16 the gate **CREDITS "intersection deanonymizes the sender"**
(0.72 @ decoy 0.00). This is the headline finding of the slice: **multi-session intersection breaks
sender anonymity *under assumed device-linkage* even where a single message (K=1, rank-1 0.09 ≈ the
floor) does not** — exactly the dominant threat PR-1/PR-2 deferred. (Exact numbers are seed-specific; the
*shape* — monotone climb crossing the threshold, decoy flat — is the robust result.)

Additive and **default-inert**: `intersection_sweep` is a new entry point; `anonymity_sweep` /
`anonymity_defense_sweep` and every prior number are bit-identical (no shared mutable path changed).
Candidate set = all N nodes (cone deferred, as in PR-1); the fused anonymity-set size is not separately
emitted (the headline is fused rank-1). The per-message estimator fused here is **reachability-only**
(the principled diffusion-source estimator; it can't oracle-pick per message the way PR-1's reported
best-of can), so K=1 is the single-event *reachability* rank-1 — **≤ PR-1's oracle-best-of headline**,
i.e. the conservative (anonymity-favorable) direction.

## Origination defenses (P2 — PR-2): venue-wide cover floor + probabilistic license
PR-1/PR-2 measured the *cheap* defenses (mixing, hard gate) as **not credited**. This slice tests what
parent §10 actually sanctions against the source-localization adversary, scored by a **which-root,
timing-aware adversary** (spec v0.4), all default-inert (`cover_rate=0`, license off ⇒ every prior number
is bit-identical, zero new RNG on the off path).

> **Build-review correction (round 2 → round 3).** An earlier "mixed-graph" estimator was **proven a
> denominator artifact**: it still scored the *real blob's own hearings* and merely enlarged the
> candidate-node list, so a non-emitting **padding null** (grow candidates with zero dummies) reproduced
> the entire apparent "credit" — at a fixed denominator the cover floor moved rank-1 by **exactly 0**. It
> did no real-vs-dummy inference. That estimator and its "0.49→0.37 credit" are **removed**.

- **Venue-wide cover floor.** EVERY node emits byte-uniform **propagating** dummy roots into the soup at
  Poisson rate `cover_rate`; each is a separate blob id with a distinct emitter node that spreads like any
  blob (real-vs-dummy hidden).
- **The WHICH-ROOT, timing-aware adversary.** It localizes **each root (real *or* dummy) from that root's
  own** first-sighting hearings (per-root emitter localization — the only way dummies enter on equal
  footing). It knows the approximate real-origination time `t*` and treats as **plausibly-real** only
  roots whose emission lies within **±Δt** of `t*` (the strong/conservative direction — knowing `t*`
  rules out temporally-distant dummies, so cover is never *over*-credited). **Metric = rank of the true
  emitter among the distinct emitters of the plausibly-real root set**, at a **fixed denominator**. Cover
  helps only if *other* emitters' dummies coincide with the real send in **time AND space** — real
  K-anonymity, not the banned 1/K and not denominator padding.
- **Credit gate = slice-3 controls + the GROWN-CANDIDATE-NULL (the honesty fix).** A **non-emitting
  padding null** (cover-OFF, candidate set grown to the cover-ON denominator with zero dummies) must
  credit **~0**; the cover arm is credited **only for the rank-1 increment ABOVE that null**. Retains
  must-localize (the slice-3 estimators the adversary reuses must localize cover-OFF), the TTL=∞ control,
  and the powered same-detected-set intersection. The own-root co-location guard is built into the metric
  (an emitter is **one** distinct candidate node).
- **Airtime cost (venue-wide):** cover dummies/min reported and billed against the §11 budget.
- **Probabilistic, time-bounded license** (`license_floor`>0, `license_max_latency_T`=T): fires with
  probability floored >0 and ceiled to **always fire by T** — measured (post-hoc, no engine perturbation)
  for **deadlock-freedom** + **cadence-invariance** (a jammed target still fires by T ⇒ isolation-oracle
  closed). **Honest scope:** liveness only, **NOT a leak reducer** — no leak-drop claimed.

**Measured verdict — NULL** (bounded: n=40, f=0.7, 2 reps, ±Δt=8, `cover_rates`∈{0, 0.4}):
must-localize passes (the estimator localizes cover-OFF, rank-1 0.45, err 0.62 radii). Cover-OFF the
unhidden source is trivially caught (rank-1 **1.00**, K=1). Cover-ON the which-root rank-1 falls to
**0.19** (K≈33–38 plausibly-real emitters) — **but the grown-candidate-null reproduces it: 0.16 with
ZERO dummies.** The credited increment (null − cover) is **−0.03** — real time+space-coincident dummy
emitters are **no more confusable than random padding**, so the gate returns **NULL: no credit above the
grown-candidate-null** (denominator, not position cover). This is the §10 sparse-mode tension made
concrete: a *uniform* venue-wide floor produces emitters spread uniformly, **not concentrated in time and
space around the true send**, so it buys no genuine K-anonymity — at a real airtime cost (≈500–1000
dummies/min). The **license** is deadlock-free and cadence-invariant (fires by T even fully isolated).
Every number is an **UPPER BOUND** (single-event external-passive; intersection/insider deferred to PR-3).

## Clustered "gathering" mobility (slice 4 — PR-1)
Every prior headline (delivery cliff, airtime knee, anonymity) was measured under **RWP open-field**
mobility, flagged *optimistic* — but polleneus's real deployment is a **gathering** (a clustered
crowd). This slice adds a clustered mobility model and asks the foundational question: **does a
clustered venue stay connected enough to deliver?** (`--preset cluster-delivery`.)

- **Model:** K cluster centers; each node does RWP toward targets near its **home** cluster (Gaussian
  `cluster_sigma`), except a `cluster_leak` fraction of retargets send it **wandering uniformly** (an
  inter-cluster mover). `leak=0` → isolated islands; `leak=1` → uniform retargets ≈ **RWP** — a
  built-in correctness gate (the clustered delivery at `leak=1` must equal the RWP delivery).
- **Headline sweep:** delivery (pairwise same-component) + giant-component fraction vs `cluster_leak`
  at a **fixed node count N** (the count for global degree 6 under a *uniform* layout — the realized
  global degree is NOT fixed; clustering concentrates nodes, so it's higher at low leak), time-averaged
  over the trajectory so a transit mover physically bridges the clusters it passes through. At a fixed
  seed the cluster layout is the **same venue across the whole sweep** (only movement varies with leak),
  so the curve isolates the leak effect.

**Measured result** (`--preset cluster-delivery`, K=8, `cluster_sigma=6`, N for uniform-degree 6, 6 reps):
at full islands (`leak=0`) delivery is **0.62** (giant 0.72) **even though the realized global degree is
20.0** (nodes pack into clusters — intra-degree 12.6) — i.e. **fragmentation despite double the local
connectivity**: dense groups that don't talk to each other. A modest **~10% leak recovers 0.86** (and
the realized degree falls to 11 as the crowd spreads), reaching the RWP value **0.91** by `leak≥0.2`;
**`leak=1` recovers RWP (gate PASS)**. So the honest finding is **partial fragmentation, cheaply
recovered**: a clustered crowd loses ~0.3 delivery vs the uniform promise, but only a little
inter-cluster movement restores it. (At tighter/smaller clusters the `leak=0` floor would drop toward
the within-cluster `~1/K`; here clusters are large and overlap, so the loss is milder — the *shape*
(rising with leak, RWP-recovered, realized degree falling) is the robust result.)

Additive and **default-inert**: the `clustered` mode is opt-in; static/rwp configs and every slice-1/2/3
number are bit-identical. The cluster layout rides the mobility RNG substream, fixed by the seed and
stable across the leak sweep (a per-rep venue). Delivery numbers remain an **UPPER BOUND** (clustering
is an optimism-*removing* axis: real crowds gather, so clustered ≤ uniform at the same N).

## The gate (why you can trust the curve)
`tests/test_integration_percolation.py`:
1. **Oracle KAT** — in the static unbounded regime the engine's multi-hop fixpoint delivers
   *exactly* the union-find same-component pairs (independent algorithm cross-check).
2. **Threshold** — susceptibility peaks near d_c≈4.51; giant component absent below, dominant above.

## Module map
`config` (params + CFL + RNG) · `geometry` (torus/walls + analytic contact timing) ·
`cell_list` (O(N) neighbours) · `mobility` (static / RWP / linear / clustered gathering) · `blob` + `buffer`
(eviction + seen-record) · `budget` (density-aware airtime) · `policies` (flood offer-select) ·
`engine` (per-step fixpoint propagation, acquisition-time causality, per-episode airtime
billing, static fixpoint) · `workload` + `metrics` (oracle, fair-chance denominator,
utilization/circulation/T50) · `percolation` (union-find + interval-reachability ground truth) ·
`knee` (saturation-knee estimator + binding publish-gate) · `scenario` (delivery sweep,
airtime sweep + control arms, anonymity sweep + defense sweep + intersection sweep, cluster leak sweep, per-rep CIs) ·
`anonymity` + `adversary` (source-localization estimators, score fusion, must-localize/exposure/
defense/intersection gates) · `report` (CSV + plot).

## Fidelity to the parent design (and bias direction)
| Modeled mechanic | Parent § | Abstraction → bias |
|---|---|---|
| pure flooding, no routing | §1/§2 | faithful; engine is addressing-blind (lint-enforced) → none |
| absolute TTL | §6 | faithful |
| eviction = oldest-by-creation | §9.5 | faithful |
| reconciliation | §8 | per-contact **byte budget**; set-reconciliation overhead **modeled** (P1, opt-in): a flat density-scheduled airtime floor `S(n)=c0+ceil(k*n)` + per-episode cap (`recon_*` config, **default off** ⇒ zero ⇒ bit-identical). Cost cited/uncalibrated; **iOS asymmetry + cross-peer prefix-carry still unmodeled → optimistic** |
| airtime (collision) | §6/§11 | ALOHA `exp(−β·n)`, **β uncalibrated**, no retransmission, ignored scan-duty-cycle misses → **optimistic** (inflate delivered fraction). (Capture effect — not modeled, OUT §4 — would pull the knee *earlier*; a separate effect, not an offset.) |
| contention population | §11 | carrier-sense **max-of-pair, single-snapshot** degree (not the full co-channel union) → **optimistic** (under-counts contenders) |
| decode failure (`p_fail`) | §8 | applied as a deterministic `(1−p_fail)` mean factor, not independent per-blob → removes tail/variance risk → **optimistic** |
| anonymity (source-estimator) | §10 | slice-3 PR-1: receiver-grid source-localization, **UPPER BOUND on anonymity** |
| anonymity (PR-1) single-event *per-message* estimator (no fusion) | §10 | **optimistic for privacy** for a persistent author — now **measured** by the PR-3 intersection slice below |
| anonymity: external passive only (no insider/compromised) | §10 | **optimistic for privacy** (deferred) |
| anonymity: uniform vs chokepoint placement | §10 | chokepoint reported as the adversary; uniform shown only as the weaker arm |
| anonymity: candidate set = all nodes (cone deferred) | §10 | anon-set crowd inflated → **optimistic for privacy** |
| anonymity: adversary unit-disk reception | §10 | optimistic for the adversary's coverage (real RF messier) |
| anonymity: worst-case auxiliary info (all trajectories) | §10 | **conservative** for exposure (safe direction) |
| anonymity defenses (mixing + originate-gate) | §10 | slice-3 PR-2: credited gain is an **UPPER BOUND on protection** (single-event/external-passive only; intersection + insider NOT evaluated) |
| defense credit: same-detected-set intersection | §10 | removes survivorship (slowed spread ≠ anonymity); below `MIN_INTERSECTION_SIZE` → inconclusive, not credited |
| defense credit: per-arm TTL=∞ control | §10 | each defense has its own TTL=∞ control (mixing + gate); a gain that dies at TTL=∞ is **not** credited as anonymity (it was message-dropping) |
| defense credit: must-localize (defenses-off) baseline + per-node relay-density | §10 | no credit if the attack couldn't localize the **defenses-off** baseline, or if the gate arm was relay-starved (per-node density, not per-relaying-node) |
| anonymity intersection (multi-session) | §10 | slice-3 PR-3: fused rank-1 over K **linked** originations, **UPPER BOUND**; device-linkage ASSUMED given (PHY = separate slice) |
| intersection: linkage assumed perfect | §10 | **worst-case upper bound** (real linkage is partial/noisy) — the safe direction for a privacy claim |
| intersection credit: decoy-centrality + fused-random controls | §10 | credit only if the ORIGINATOR is pinned and the most-central innocent relay (decoy) is not; fusion itself creates no signal (random floor stays ~1/N) |
| intersection: credited headline = lower of Borda/score-sum | §10 | **conservative** — never credit the adversary a fusion-rule coin-flip |
| clustered "gathering" mobility (vs RWP open-field) | — | slice-4: **optimism-REMOVING** — real crowds cluster; clustered delivery ≤ RWP at the same node count N (clustering raises the realized degree) |
| clustered: static clusters (no gather→disperse) | — | abstraction; a forming/dispersing crowd is transient (named follow-up) |
| clustered: leak=1 recovers RWP | — | correctness sanity gate, not a bias |
| crypto | §5 | **not modeled** (deferred) |
| tokens / anti-flood rate-limit | §9 | §9 rate-limit **modeled** (anchored-`nf` + epidemic seen-`nf` gossip, post-hoc overlay): the rate-limit is a **gossip-vs-spend RACE** — works (slots/token→~1) only when gossip outpaces the serialized spend rate; a **static burst holder leaks ~D (no rate-limit)**, qualifying §9.3's "D→1" as an instantaneous-gossip idealization. **Device-count residual (cloud/botnet + K-radio farm) + seen-`nf` gossip airtime NOT modeled → optimistic**; `nf` is a per-token pseudonym (handshake-layer linkability); `gossip_delay=0` = unphysical instantaneous front. Every number an UPPER BOUND on the rate-limit |
| delivery | — | arrival == delivery (ignores read-window / FS) → **upper bound** |

## Caveats (idealizations — all bias delivery UP)
Unit-disk links; contention sampled once per step over a carrier-sense max-of-pair degree;
collision steepness `β` is an **uncalibrated** parameter (the knee is reported as a function of
it, with the linear model as the optimistic-band edge); reconciliation/set-reconciliation
overhead modeled as zero; deterministic decode-failure mean; arrival==delivery; RWP open-field
mobility (optimistic vs a clustered venue); fixed-N vs Poisson differences within the reported
CIs. The **publish-gate** refuses to label a curve "airtime-saturation" unless the α=0 and
cap=∞/ttl=∞ controls rule out connectivity/buffer/TTL causes. **Do not read these curves as
measured BLE performance.**
