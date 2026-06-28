# polleneus — P4 PR-2: The bridge (cold-start floor-lift) + low-N activation

**Version:** v0.1 — 2026-06-28 · **Roadmap:** P4 — PR-2 (§16-P4: opportunistic bridge; gathering kits;
pair-to-activate N=2; standby N=0) · **Builds on:** P4 PR-1 (ferrying lift), slice-4 clustered mobility

> **Why this serves the mission.** PR-1 showed mobility ferries below `d_c` **when nodes mix**. But the real
> cold-start is **separated gatherings** (clustered islands): with `cluster_leak=0` ordinary nodes never
> leave their gathering, so **cross-island delivery is a hard floor** — the messages stay trapped in each
> crowd. §14 names the fix: a **bridge / "organizer gathering kit"** — a node that travels *between*
> gatherings and ferries the soup across. This PR models the bridge, measures whether it lifts the floor, and
> states the honest condition under which it works.

## 1. Problem & current state

slice-4's `cluster_leak_sweep` is **engine-free** (static snapshots), so it never measured *temporal*
ferrying across islands. PR-1's ferrying was RWP (ergodic — everyone eventually mixes). Neither answers: in
**true islands** (`leak=0`), does a dedicated bridge carrier actually deliver across gatherings — and does
the *way it moves* matter?

## 2. Mechanism (default-inert)

- **Bridge carriers (`n_bridge`).** The first `n_bridge` nodes get **personal leak = 1.0** (they always
  wander between gatherings) while ordinary nodes keep `cluster_leak` (per-node leak vector; the `rng.random`
  draw is unchanged in size/order ⇒ `n_bridge=0` is **bit-identical**). Only affects `clustered` mobility.
- **Routing model (`bridge_tour`).** *How* a wandering bridge moves decides whether it ferries:
  - `False` (default) — a wandering node targets a **uniform arena point**. In a sparse venue that is mostly
    **empty space**, so the bridge rarely lands in a gathering → a **poor ferry**.
  - `True` — a wandering node heads to a **random cluster centre** (a gathering). This is the §14 **organizer
    gathering kit**: purposeful routing between known meeting points → an **effective ferry**. (`bridge_tour`
    draws different RNG than the uniform branch, so only `False` is the bit-identical legacy path.)

## 3. What we measure (`bridge_lift_sweep`, both arms; seed=7, reps=4; clustered K=4 islands, leak=0)

Config: **K=4, W=H=500, σ=4, r=12** — chosen so the gatherings are **genuinely disconnected**: the
initial-layout giant-component fraction is **`giant_frac = 0.250 = 1/K`** (each gathering its own component;
the sweep emits this so the island premise is **auditable per run**, not asserted — an earlier draft used
W=300/σ=8 where centres overlapped and the "floor" was permeability-inflated to ~0.33; this is the corrected,
honest config). Engine delivery at a **fixed budget** vs `n_bridge`, against the shared no-bridge floor:

| n_bridge | UNIFORM-wander | TOUR (purposeful) |
|---------:|---------------:|------------------:|
| 0 (floor) | 0.17 | 0.17 |
| 1 | 0.10 | 0.54 |
| 2 | 0.19 | **0.81** |
| 4 | 0.21 | 0.79 |
| 8 | 0.23 | 0.94 |

Honest findings (robust **8/8** over independent seed-groups: `giant_frac ≈ 1/K`; tour lifts floor by > 0.3;
uniform stays within 0.25 of floor; tour beats uniform by > 0.3):
1. **The cold-start floor is real and hard.** `giant_frac = 1/K` confirms genuine islands — with no bridge,
   cross-island delivery is ~0 added; delivery is stuck at the intra-gathering fraction (~0.17). Gatherings
   genuinely cannot talk to each other.
2. **A purposeful (tour) bridge lifts it steeply** — **two** tour ferries take 0.17 → 0.81.
3. **A naive uniform-wander bridge is essentially useless here** — eight of them reach only 0.23 (barely off
   the floor; in a genuinely-separated sparse arena a uniform wanderer almost never lands in a gathering).
   **Effective ferrying is a PURPOSEFUL-routing (operational) property — the organizer must travel between
   gatherings — NOT an emergent protocol guarantee.**

## 4. Low-N activation (§14 pair-to-activate / standby)

- **Pair-to-activate (N=2):** two nodes within radio range deliver (deterministic test: `gap < r` ⇒ node 1
  receives the blob). The protocol works at the smallest non-trivial network.
- **Standby (isolated):** a node out of range receives nothing and **falsely delivers nothing** (`gap > r` ⇒
  no delivery, no error). "Standby at N=0/1" — idling when alone with nobody to flood to — is **client UX**
  (the app conserves battery and waits); the sim's contribution is the no-false-delivery / no-crash guarantee
  at tiny N.

## 5. Honesty / invariants

- **UPPER BOUND.** RWP within and between clusters; no airtime/buffer cost on this path. Real movement is more
  constrained; real bridges deliver less.
- **The ceiling is ergodic** (as in PR-1): at unbounded budget even one bridge eventually visits every island,
  so delivery → 1. This is a **fixed-budget** floor-lift; the informative content is *purposeful ≫ naive at a
  bounded budget*, not the ceiling.
- **No invariant touched.** `n_bridge=0` ⇒ bit-identical; `bridge_tour` is a no-op when nothing wanders
  (`leak=0`, `n_bridge=0`) — asserted by a full-result identity test. Determinism preserved.
- **Scope honesty:** the bridge is a *deployment/ops* lever (organizer kits), not a protocol that
  auto-discovers routes. We claim only what we measured: purposeful inter-gathering travel lifts the floor.

## 6. Out of scope / deferred

- A **long-range radio sideband** (real NAN/LoRa link, not a mobile carrier) — a transport add, later PR.
- **Optimal tour scheduling / how many kits per venue** — an ops question; we show the shape, not a planner.
- The §14 **standby/battery** state machine — client UX, not the sim.

## 7. Plan sketch

1. Config: `n_bridge` (per-node leak), `bridge_tour` (routing) — default-inert.
2. Mobility: per-node leak vector; tour branch targets a random cluster centre.
3. `scenario.bridge_lift_sweep` (both arms) + `report.bridge_to_csv_string` (regime + caveat header).
4. `tests/test_p4_bridge.py` — floor/tour-lift/uniform-weak; shared floor; default-inert no-op; validation;
   deterministic pair-to-activate vs standby; determinism.
5. README fidelity note. Bounded measure (small N). Fan-out review; PR (`--base main`); merge.
