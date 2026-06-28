# polleneus — Scale: the airtime budget (beside the storage table)

**Roadmap:** P0 (*re-scope & measure*) · **Parent design:** [polleneus v0.5 §11](superpowers/specs/2026-06-25-polleneus-design.md#11-scale--airtime-budget-beside-the-storage-table)
· **Generated from:** `sim/` `airtime-knee` apparatus (seed 12345; see *Reproduce*).

> ⚠️ **Every number here is an UPPER BOUND on real-world circulation.** The simulator idealizes the
> radio (unit-disk links, single-snapshot contention, no retransmission), models set-reconciliation
> overhead as **zero**, and the collision steepness **β is an uncalibrated free parameter**. Read these
> as *"the apparatus can detect an airtime knee when one exists,"* **not** as measured BLE performance.
> The field/USRP number is still owed (see [`superpowers/release-blockers.md`](superpowers/release-blockers.md) B2).

## Why this table exists — the re-scope

The intuitive scale wall for a store-and-flood messenger is **storage**: *"won't every phone fill up?"*
The second red-team (v0.3) showed that framing is wrong. **Storage is comfortable; the binding
constraint is *circulation* — how many distinct blobs the soup can actually re-share per minute over a
few shared BLE advertising channels.** So we publish an **airtime-budget table beside the storage
table**, and let the airtime one carry the honest scale claim.

> **Blob size used throughout this doc = 256 B** (the simulator's modeled sealed-message size). The
> parent spec §6 rounds to ~1 KB; **both tables below use 256 B so the comparison is apples-to-apples.**
> Crucially the *ratio* that follows is **blob-size-invariant**: storage capacity (blobs held) and
> circulation (blobs/min) both scale ~1/blob_size, so they cancel — at 1 KB the storage counts and the
> circ/min would each be ~4× smaller and the gap below is unchanged.

## 1. The storage table — capacity is *not* the wall

At **256 B per sealed blob**, a **1–2 GB** working buffer holds **~4–8 million live blobs**, and
absolute TTL + size caps keep the live set bounded.

| Buffer | Blobs held (256 B each) | Binding? |
|---|---|---|
| 256 MB | ~1.0 M | no |
| 1 GB | ~4.2 M | no |
| 2 GB | ~8.4 M | no |

## 2. The airtime table — what the soup actually moves

Measured circulated-blobs/min vs crowd density over **3 shared advertising channels**, mobile (RWP)
nodes, ALOHA **collision** model. The **linear** model (`1/(1+α·n)`, no turn-over) is the optimistic
edge of a model-uncertainty band. *Measured: seed 12345, reps = 2, densities 2–6 (the gathering
operating range — see the reproduce note for why this slice).*

| Mean degree | Collision (blobs/min) | Linear band | Airtime utilization | Delivery | T50 (s) |
|---|---|---|---|---|---|
| 2 | 3,640 | 3,640 | 3.1 % | 1.00 | 9.2 |
| 3 | 5,480 | 5,480 | 3.7 % | 1.00 | 4.8 |
| 4 | 7,280 | 7,280 | 5.7 % | 1.00 | 5.8 |
| 5 | 9,120 | 9,120 | 6.9 % | 1.00 | 6.0 |
| 6 | 10,960 | 10,960 | 10.3 % | 1.00 | 9.8 |

*Collision and linear **coincide exactly** in this range (the band has **zero width** until the
high-density tail, where collision turns over and linear plateaus). The 95% CIs are also zero-width
here — but only because the two reps produced identical circulation to sub-integer precision; this is a
**degenerate reps = 2 interval, NOT a cross-seed stability claim.** (The airtime CI estimator's
upper-bound clamp — which would mis-clamp this unbounded metric's upper CI at higher reps — is corrected
in sibling **PR #13**, and lands on `main` when that PR is merged.)*

**The gap is the point.** Capacity is **millions of blobs** but circulation is **thousands per
minute** — a **~1000× gap** (≈ many hours to circulate one buffer's worth), and that ratio holds at any
blob size. **You will never store-limit before you circulate-limit.**

**What this range shows — and the honest non-claim.** Across the operating range, circulation rises
~linearly with density (≈1.8 k blobs/min per unit degree), **delivery is complete (1.00) and airtime
utilization stays low (3–10 %)** — so the soup is **not airtime-bound at these densities**, and the
binding **publish-gate (§3) returns `publish = False · "no knee in range"`.** We therefore **do not**
label this curve "airtime saturation"; here circulation is connectivity-/demand-bound. (Corroborating
the approach to the wall: the contention-bound fraction of unmet demand already erodes from 1.00 to
**0.85** by d = 6 — the apparatus sees the knee coming, just above the published range.)

**Where the airtime wall is.** The collision turn-over (the airtime *knee*) sits in the **high-density
tail above this range** — predicted at **n\* = 1/β = 10 co-channel contenders** (β = 0.1, uncalibrated).
Its *existence* (the falsifiable prediction: collision turns over, linear plateaus) is pinned by the
simulator's `test_collision_knee_linear_plateau_distinguishable` gate. We **cite** that gate rather than
re-plot the tail here: sweeping the high-density regime is hours of compute (the engine is super-linear
in crowd size) and produces no claim the gate doesn't already establish.

### P1 update (2026-06-27) — reconciliation cost, re-measured

The table above was generated with **set-reconciliation overhead modeled as zero** (optimistic). P1
replaced that with a conservative cost model — a **flat, density-scheduled airtime floor** `S(n)=c0+⌈k·n⌉`
plus a per-episode novel-transfer **cap** (spec [`2026-06-27-p1-reconciliation`](superpowers/specs/2026-06-27-p1-reconciliation-spec.md)) — and re-measured. The honest result is **two-regime**:

**In the operating range it costs airtime but does NOT cut circulation** (`recon_compare_sweep`,
airtime_cfg, reps 2, ON = `cell_bytes 8, c0 2, k 0.5`):

| Mean degree | circ/min OFF → ON | haircut | utilization OFF → ON | charged-airtime OFF → ON |
|---|---|---|---|---|
| 2 | 3,640 → 3,640 | **1.00** | 0.03 → 0.04 | 601 → 843 |
| 4 | 7,280 → 7,280 | **1.00** | 0.05 → 0.09 | 3,820 → 6,385 |
| 6 | 10,960 → 10,960 | **1.00** | 0.11 → 0.30 | 17,728 → 48,948 |

Reconciliation airtime is **genuinely consumed** (utilization and charged-airtime rise — at d=6 utilization
nearly triples, 0.11 → 0.30 — so the free-reconciliation optimism is provably gone), yet **circulation is
unchanged** because the operating range is **not airtime-bound**: there is spare airtime to absorb the
cost, and per-episode-capped transfers simply complete in later contacts via the soup's redundancy.
**P1 confirms, rather than overturns, the P0 conclusion for the operating range.**

**At airtime-saturation the haircut is real.** A deliberately saturated fixture (util ≈ 0.7, seed 12345)
gives, at the representative ON schedule (`cell_bytes 8, k 0.5`), **haircut 0.93** (circ/min 4,435 → 4,127).
The **2-D sensitivity band** (same fixture, baseline circ 4,435) shows the two mechanisms separately —
*uncalibrated `(cell_bytes, k)`, reported as a band, not a single number* (reproduce: `--preset recon-band`):

| `cell_bytes` ↓ \ `k` → | 0.0 (tight cap) | 0.5 | 1.0 |
|---|---|---|---|
| 1 | 0.45 *(cap-bound)* | 0.99 | 0.98 |
| 8 | 0.44 *(cap-bound)* | 0.93 | 0.85 |
| 32 | 0.43 *(cap-bound)* | 0.66 | 0.36 |

At `k=0` the per-episode **cap** dominates (a big haircut ~0.43–0.45, ~520–550 capped episodes,
≈cell_bytes-independent); at `k>0` the **flat airtime floor** dominates and the haircut scales with the
floor size (`cell_bytes × cells`). **Honest caveat:** reconciliation cost is **not strictly monotone** —
the multi-hop engine reorders transfers, so a single run can jitter either way (spec §4); the numbers above
are multi-rep means, and the operating-range haircut is **within reordering noise**. *(The cap is modeled
as `floor(S(n))` — overhead 1, no `c0_reserve` — the minisketch primary, cheapest-defensible bound; a
stricter cap would only increase the haircut.)*

*Reproduce:* `cd sim && .venv/Scripts/python run.py --preset recon-compare --reps 2 --out out/recon.csv`
(operating-range OFF vs ON); the saturated haircut + 2-D sensitivity band via
`--preset recon-band --out out/recon_band.csv`. Both CSVs carry the ON recon schedule in the manifest.

## 3. How to read it — the publish-gate (the honesty guard)

A figure is **only** labelled "airtime-saturation" if the binding publish-gate passes: there is a knee
**AND** ≥50 % of unmet demand at the knee is contention-bound **AND** the **α = 0** (airtime-free)
control does **NOT** turn over (else the turn-down is connectivity-caused) **AND** the **cap = ∞ /
ttl = ∞** control **DOES still** turn over (the turn-down persisting when buffer/TTL are infinite is
what rules out a buffer/TTL cause). Otherwise the curve is labelled **connectivity-/buffer-/TTL-limited**.
For the swept range above the gate returns **`publish = False · "no knee in range"`** — exactly the
honest outcome (no airtime wall in the operating densities; the wall is higher up).

## 4. Provenance (where the inputs come from — all conservative / upper-bound)

| Parameter | Value used | Source / rationale | Bias |
|---|---|---|---|
| `throughput_ideal` (goodput) | ~100 kbps (12.5 kB/s) | BLE 4.x, no Data-Length-Extension; BLE 5 2M PHY + DLE (~1.4 Mbps) is the optimistic sensitivity | conservative headline |
| `t_setup` | 50 ms | BLE connection/handshake floor | — |
| `t_setup_slope` | density-dependent | discovery latency grows with advertiser count | optimistic if under-set |
| `β` (collision steepness) | **uncalibrated** (0.1) | predicted knee `n* = 1/β` reported up front; swept across the band | knee reported *as a function of* β |
| `blob_size` | **256 B** | sim's modeled sealed message; parent §6 rounds to ~1 KB (circ/min ~4× lower at 1 KB; the storage/circulation *ratio* is blob-size-invariant) | optimistic vs 1 KB |
| reconciliation overhead | **0** in the §2 table; **modeled** in the P1 update above | §2 used zero (optimistic); P1 adds a flat density-scheduled floor `S(n)=c0+⌈k·n⌉` + per-episode cap (cited, uncalibrated) | §2 optimistic; the P1 update removes that optimism (airtime consumed; operating-range circulation unchanged, haircut at saturation) |
| contact-duration dist. | RWP, open-field | tail is optimistic vs clustered human-contact traces | optimistic |

## 5. The public claim this supports (re-scoped, honest)

> **Undirected flooding buys anonymity and *caps* scale — and the cap is airtime, not storage.**
> A phone can store ~millions of blobs but the soup circulates only ~thousands per minute (a ~1000×
> gap, blob-size-invariant); at gathering densities that circulation is not yet airtime-bound, and the
> airtime ceiling (collision turn-over) bites only as the crowd gets much denser. polleneus works at
> **gathering scale** (stadium / protest / campus / blacked-out neighbourhood); a metropolis needs
> bridges. The scale limit is a **cost bound**, **not** an impossibility and **not** a storage ceiling.
> Shorter TTL, size caps, and rateless reconciliation (§8) stretch the feasible density.

No claim of metropolis scale. No claim that capacity is the constraint. The number that travels with any
scale statement is **circulated-blobs/min at the venue's density, labelled an upper bound.**

## Reproduce

The shipped preset sweeps **densities 2–18, reps 12** (the full curve through the high-density knee) —
**expensive (hours: the engine is super-linear in crowd size):**

```bash
cd sim
.venv/Scripts/python run.py --preset airtime-knee --reps 12 --seed 12345 --out out/airtime.csv
```

The **table above is the densities 2–6 slice at reps 2** — a reduced operating-range run for tractability
(the preset's density grid is fixed at 2–18, so the published rows are the low-density portion of that
curve; the production preset above regenerates the full curve including the knee). The CSV carries the
full parameter manifest per row, so every point is reproducible. **For correct circ/min confidence
intervals, regenerate on a `main` that includes PR #13** (the CI-clamp fix). See `sim/README.md`
(*slice 2: airtime & mobile delivery*) for the model and the bias table for every idealization's
direction. **Do not read these curves as measured BLE performance.**
