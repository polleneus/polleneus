# Feature Spec — Clustered "Gathering" Mobility (Simulator Slice 4) — PR-1

**Status:** Draft → CTO design-direction approved (static clusters + intra-cluster RWP, PR split) → **CTO SIGN-OFF (2026-06-26)** — authorizes the PR-1 implementation plan.
**Date:** 2026-06-26
**Parent design:** [polleneus v0.5](2026-06-25-polleneus-design.md) · **Builds on:** [soup-sim slice 1](2026-06-25-soup-sim-spec.md), [airtime slice 2](2026-06-25-airtime-sim-spec.md), [anonymity slice 3](2026-06-26-anonymity-sim-spec.md)
**Roadmap:** every prior headline (delivery cliff, airtime knee, source-localization + intersection) was measured under **RWP open-field mobility**, which the bias tables flag as *optimistic*. Polleneus's real deployment is a **gathering** — a clustered crowd. This slice adds a clustered mobility model and asks the foundational robustness question first: **does a venue-scale crowd stay connected enough to deliver as it clusters?**

> **What this is and is NOT.** PR-1 ships the clustered mobility *model* + a **delivery/connectivity robustness sweep** over the inter-cluster leak rate. It does NOT re-run the anonymity slice — *clustered anonymity (does intersection still deanonymize a persistent sender under clustering?)* is the named **PR-2**. Clusters are **static** (no gather→disperse dynamics — a named follow-up).

> **Honesty (inherited).** Every delivery number remains an **UPPER BOUND on real delivery** (idealized reconciliation, no decode-failure tail, etc. — see slice-1/2 bias tables). Clustering is a *new optimism-removing* axis: the uniform/RWP numbers were optimistic *because* real crowds cluster, so clustered numbers are expected to be **lower** (more honest). Every emitted clustered figure carries its **mobility regime** inline (e.g. `delivery=0.4 [clustered: K=8, leak=0.1]`).

---

## 1. The model — clustered RWP (CTO-chosen)
Reuse RWP's move-toward-target mechanics; change only **where targets come from**.
- **K cluster centers** placed uniformly at random in the arena (seeded substream).
- **Home assignment:** each node is assigned a home cluster **round-robin** (`node i → cluster i mod K`), fixed for the run — balanced cluster sizes, deterministic, no extra RNG draw.
- **Cluster-aware retarget:** when a node arrives at its target, it draws a new target = `home_center + Normal(0, cluster_sigma)` (torus-wrapped / wall-clamped to the arena), EXCEPT with probability **`cluster_leak`** it instead targets a *uniformly-random other* cluster's neighborhood (an inter-cluster mover).
- **Limiting cases (the built-in sanity checks):**
  - `cluster_leak = 0` → nodes never leave their home cluster → **isolated islands**.
  - `cluster_leak = 1` → every retarget goes to a random cluster → targets ≈ uniform over the arena → **recovers RWP**. The clustered delivery cliff MUST converge to the RWP cliff as `leak→1` (a DoD test).
- **Initial positions** drawn near each node's home center (same Normal), then the existing RWP burn-in relaxes toward the clustered stationary distribution.

## 2. Config (additive; existing static/rwp untouched)
New fields, used ONLY when `mobility == "clustered"` (so every static/rwp config stays bit-identical):
- `n_clusters: int` (≥1) — K.
- `cluster_sigma: float` (≥0) — intra-cluster spread (in arena units; relative to `radius` for interpretation).
- `cluster_leak: float` (0..1) — per-retarget probability of moving to another cluster (the sweep axis).
- `validate()` guards: `n_clusters ≥ 1`, `0 ≤ cluster_leak ≤ 1`, `cluster_sigma ≥ 0` — only enforced when `mobility == "clustered"`.

## 3. Headline deliverable — the leak-rate robustness sweep
At a **fixed global mean-degree** (chosen above the uniform connectivity threshold d_c≈4.51 so the *uniform* field would deliver), sweep `cluster_leak ∈ {0, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0}` and report, per leak, over a seed ensemble:
- **delivery** = pairwise same-component fraction (the slice-1 quantity), mean + 95% CI over seeds.
- **giant-component fraction** = `largest_component_fraction` (the *mechanism*: fragmentation, not just lower delivery).
- **realized intra- vs inter-cluster degree** (diagnostic: confirms clustering is real and leak does what it says).
- **The RWP-recovery check:** delivery at `leak=1` ≈ the RWP delivery at the same global degree (within CI) — printed as an explicit PASS/FAIL line.

**Stated prediction (up front, honest):** delivery **collapses** toward 0 as `leak→0` (islands cannot exchange) despite high *intra*-cluster density, then rises to the RWP value as `leak→1`. The decision-relevant number is *how much inter-cluster leak is needed to keep a clustered venue connected* — i.e. clustering can push the mesh below the uniform cliff's promise, and we quantify the leak rate that recovers it.

## 4. Architecture — additive, mobility-agnostic reuse
- `mobility.py` (extend): a `clustered` branch in `make_mobility` (place centers, assign homes, near-home init + targets, burn-in) and a cluster-aware retarget inside `Mobility.step` (reuse the existing move-toward-target + arrival logic; only the target-draw on arrival is cluster-aware). New `Mobility` fields: `centers`, `home`, `cluster_sigma`, `cluster_leak` (None for static/rwp → existing paths unchanged).
- `scenario.py` (extend): `cluster_leak_sweep(base_cfg, leak_values, degree, reps)` returning per-leak delivery + giant-component + intra/inter degree + the RWP-recovery comparison. Reuses the existing percolation/ensemble helpers; does NOT touch `static_delivery_sweep`/`airtime_sweep`/the anonymity sweeps.
- `report.py` (extend): `cluster_to_csv_string` — one row per leak with delivery/CI, giant-component, intra/inter degree, mobility-regime tag as a column.
- `run.py` (extend): `--preset cluster-delivery` — run the leak sweep, print the curve + the RWP-recovery PASS/FAIL + the mobility-regime tag.
- **RNG (no new tag):** cluster centers + near-home init all draw from the **mobility substream (tag 0)** that `make_mobility` already receives, drawn *before* any per-leg target — so the cluster layout is fixed by the seed and is **identical across the leak sweep** (only the per-retarget leak choices, drawn later in `Mobility.step`, vary with `cluster_leak`). Home assignment is round-robin (no draw). Static/rwp never enter the clustered branch, so their tag-0 usage is unchanged → bit-identical. (Existing tags unchanged: mobility=0, engine=1, cohort=2, buffers=(3,i), placement=4, mixing=5, estimator=6, tracked-cohort=7, airtime-bootstrap=777.)
- **Default-inert:** all new code is gated on `mobility == "clustered"`; the slice-1/2/3 gates (percolation oracle, airtime knee, anonymity) stay bit-identical with static/rwp configs.

## 5. Bias table (new rows)
| Mechanic | Direction |
|---|---|
| clustered mobility (vs RWP open-field) | **optimism-REMOVING** — real crowds cluster; clustered delivery ≤ RWP delivery at the same global degree (more honest) |
| static clusters (no gather→disperse) | abstraction → mild; a forming/dispersing crowd is transient (named follow-up PR) |
| K centers uniform-random, home assignment fixed | faithful to "zones with stable membership"; extreme layouts (one mega-cluster) not swept here (follow-up) |
| delivery still pairwise same-component (slice-1 quantity) | **UPPER BOUND on delivery** (inherited; reconciliation idealized, no decode tail) |
| leak=1 recovers RWP | sanity check, not a bias — a DoD correctness gate |

## 6. Definition of Done
- `clustered` mobility mode implemented; `make_mobility` places K centers, assigns homes, inits near-home, burns in; `Mobility.step` retargets cluster-aware with leak. Deterministic by seed.
- `cluster_leak_sweep` produces delivery + giant-component-fraction + intra/inter-degree vs leak, with CI over seeds, at a fixed global mean-degree.
- **RWP-recovery gate (correctness):** delivery at `leak=1` equals the RWP delivery at the same global degree within CI — asserted by a test and surfaced in the CLI.
- **leak=0 isolation:** inter-cluster degree ≈ 0 and delivery ≈ the within-largest-cluster fraction — asserted by a test.
- Every emitted clustered number carries the mobility-regime tag (asserted by a test).
- Engine + slices 1/2/3 bit-identical / non-regressing with static/rwp configs; one-command run (`--preset cluster-delivery`); bias table filled.
- The measured headline (how delivery + giant component move with leak, and the leak needed to stay connected) reported faithfully in the README — including the honest fragmentation finding.

## 7. Decisions confirmed / to confirm at sign-off
- **Feature = Slice 4, clustered "gathering" mobility** — *CTO ✓ (feature pick delegated, clustering chosen).*
- **Model = static clusters + intra-cluster RWP + inter-cluster leak; leak the sweep axis; RWP = leak→1 limit** — *CTO ✓ (approach A).*
- **PR split: PR-1 = model + delivery/connectivity robustness; PR-2 = anonymity (intersection) under clustering** — *CTO ✓.*
- **Headline = delivery + giant-component-fraction vs leak at fixed global degree, with the RWP-recovery gate** — *recommend yes.*
- **Additive/default-inert; cluster layout on the mobility substream (no new RNG tag, stable across the leak sweep); uniform numbers remain the labeled optimistic baseline** — *recommend yes.*
