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
  aggregate `n·goodput` has an interior maximum at `n* = n_channels/β` contenders — so
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
  there is a knee AND ≥50% of *unmet* demand at the knee is **contention-bound** AND **neither**
  the **α=0** (airtime-free: β=0, α=0, t_setup_slope=0 → constant goodput, flat setup) control
  **nor** the **cap=∞/ttl=∞** control turns over. Otherwise
  the curve is labelled connectivity/buffer/TTL-limited. This makes it impossible to mislabel a
  storage/connectivity effect as "airtime."
- **Censoring-aware latency:** TTL-expired messages are censored; we report **T50** (time to 50%
  of the fair-chance cohort delivered; `None` when <50% ever arrive) jointly with delivery
  ratio. Delivered-only mean latency is a LOWER bound (survivorship) and labelled as such.

## Airtime provenance (where the numbers come from — all conservative/UPPER-BOUND)
| Parameter | Value used | Source / rationale | Bias |
|---|---|---|---|
| `throughput_ideal` (goodput) | **~100 kbps** headline (12.5 kB/s) | BLE 4.x connection, no Data-Length-Extension; ~1.4 Mbps (BLE 5 2M PHY + DLE) is the optimistic upper sensitivity | conservative headline; report both |
| `t_setup` | 50 ms | BLE connection/handshake floor; short contacts move nothing | — |
| `t_setup_slope` | density-dependent | discovery latency grows with advertiser count (scan-window contention) | optimistic if slope under-set |
| `β` (collision steepness) | **uncalibrated free parameter** | predicted knee `n* = n_channels/β` reported up front; sweep is run across the band | report knee as a function of β |
| `blob_size` | 256 B | one sealed message (parent §6) | — |
| contact-duration distribution | RWP, open-field | report the empirical distribution; its tail is **optimistic** vs clustered human-contact traces | optimistic |

## The gate (why you can trust the curve)
`tests/test_integration_percolation.py`:
1. **Oracle KAT** — in the static unbounded regime the engine's multi-hop fixpoint delivers
   *exactly* the union-find same-component pairs (independent algorithm cross-check).
2. **Threshold** — susceptibility peaks near d_c≈4.51; giant component absent below, dominant above.

## Module map
`config` (params + CFL + RNG) · `geometry` (torus/walls + analytic contact timing) ·
`cell_list` (O(N) neighbours) · `mobility` (static / RWP / linear) · `blob` + `buffer`
(eviction + seen-record) · `budget` (density-aware airtime) · `policies` (flood offer-select) ·
`engine` (per-step fixpoint propagation, acquisition-time causality, per-episode airtime
billing, static fixpoint) · `workload` + `metrics` (oracle, fair-chance denominator,
utilization/circulation/T50) · `percolation` (union-find + interval-reachability ground truth) ·
`knee` (saturation-knee estimator + binding publish-gate) · `scenario` (delivery sweep,
airtime sweep + control arms, per-rep CIs) · `report` (CSV + plot).

## Fidelity to the parent design (and bias direction)
| Modeled mechanic | Parent § | Abstraction → bias |
|---|---|---|
| pure flooding, no routing | §1/§2 | faithful; engine is addressing-blind (lint-enforced) → none |
| absolute TTL | §6 | faithful |
| eviction = oldest-by-creation | §9.5 | faithful |
| reconciliation | §8 | per-contact **byte budget**, set-reconciliation overhead modeled as **zero** → optimistic (no IBLT/rateless overhead) |
| airtime (collision) | §6/§11 | ALOHA `exp(−β·n)`, **β uncalibrated**, no retransmission, ignored scan-duty-cycle misses → **optimistic** (inflate delivered fraction). (Capture effect — not modeled, OUT §4 — would pull the knee *earlier*; a separate effect, not an offset.) |
| contention population | §11 | carrier-sense **max-of-pair, single-snapshot** degree (not the full co-channel union) → **optimistic** (under-counts contenders) |
| decode failure (`p_fail`) | §8 | applied as a deterministic `(1−p_fail)` mean factor, not independent per-blob → removes tail/variance risk → **optimistic** |
| anonymity (source-estimator) | §10 | **not modeled** (deferred) |
| crypto / tokens | §5/§9 | **not modeled** (deferred) |
| clustered "gathering" mobility | — | RWP open-field only (clustered mobility is a named fast-follow) → **optimistic** |
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
