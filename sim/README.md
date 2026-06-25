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
.venv/Scripts/python run.py --preset static-cliff --out out/cliff.csv --plot out/cliff.png
```
`run.py` sweeps mean degree and writes a CSV (with the **full parameter manifest** per row,
so any point is reproducible from the file) plus the delivery-vs-density curve.

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

## The gate (why you can trust the curve)
`tests/test_integration_percolation.py`:
1. **Oracle KAT** — in the static unbounded regime the engine's multi-hop fixpoint delivers
   *exactly* the union-find same-component pairs (independent algorithm cross-check).
2. **Threshold** — susceptibility peaks near d_c≈4.51; giant component absent below, dominant above.

## Module map
`config` (params + CFL + RNG) · `geometry` (torus/walls + analytic contact timing) ·
`cell_list` (O(N) neighbours) · `mobility` (static / RWP / linear) · `blob` + `buffer`
(eviction + seen-record) · `budget` (density-aware airtime) · `policies` (flood offer-select) ·
`engine` (analytic multi-hop episodes, half-duplex budget, static fixpoint) · `workload` +
`metrics` (oracle, fair-chance denominator) · `percolation` (union-find ground truth) ·
`scenario` (sweep, per-rep CIs, cliff) · `report` (CSV + plot).

## Fidelity to the parent design (and bias direction)
| Modeled mechanic | Parent § | Abstraction → bias |
|---|---|---|
| pure flooding, no routing | §1/§2 | faithful; engine is addressing-blind (lint-enforced) → none |
| absolute TTL | §6 | faithful |
| eviction = oldest-by-creation | §9.5 | faithful |
| reconciliation | §8 | modeled as a per-contact **byte budget** → optimistic (no IBLT overhead) |
| airtime | §6/§11 | density-aware budget, single-snapshot contention → **optimistic** |
| anonymity (source-estimator) | §10 | **not modeled** (deferred) |
| crypto / tokens | §5/§9 | **not modeled** (deferred) |
| delivery | — | arrival == delivery (ignores read-window / FS) → **upper bound** |

## Caveats (idealizations — all bias delivery UP)
Unit-disk links; contention sampled once per contact; reconciliation as a byte budget;
arrival==delivery; static-uniform placement (RWP overlay is optimistic for an open field, not
a clustered venue); fixed-N vs Poisson differences are within the reported CIs. **Do not read
these curves as measured BLE performance.**
