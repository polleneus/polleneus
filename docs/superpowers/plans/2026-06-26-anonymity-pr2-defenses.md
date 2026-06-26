# Anonymity Slice 3 · PR-2 — Defenses (mixing + receive-before-originate) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans). Steps use `- [ ]` checkboxes.

**Goal:** On the trusted PR-1 exposure apparatus (which measured ~29% originator exact-catch at high passive-grid coverage, capability-gate-confirmed), measure whether the design's two cheapest defenses — **Poisson mixing delay** and the **receive-before-originate gate** — actually cut that leak, and at what delivery/latency cost. The honest question: do they work, against an adversary that *tries* to defeat them?

**Architecture:** Additive, all behind default-OFF config (`mixing_lambda=0`, `originate_gate_relays=0`, `originate_gate_time=0`) ⇒ engine bit-identical to the merged state (PR-1 + slices 1–2 gates stay green). Defenses hook into the engine's `_offerable` forwardability guard and `_exchange` relay accounting. A new **origin-vs-relay** estimator gives the adversary a real shot at defeating the gate. `scenario.py` gains defense arms (baseline / mixing / gate / both) with the spec's mandatory **confound controls** (TTL=∞ timing-only for mixing; relay-density for the gate) and a **defense-power gate**. Every number stays an UPPER BOUND on anonymity with the scope tag (PR-1's honesty machinery).

**Tech Stack:** Python 3, numpy, pytest (`pythonpath=["."]`), matplotlib (optional). Determinism via `cfg.rng(*path)`.

## Global Constraints
- **Every anonymity number is an UPPER BOUND on anonymity**; scope tag travels (PR-1 `SCOPE_TAG`). **Defense-scope disclaimer** on every defense-gain number: "gain vs the single-event passive-grid adversary only; NOT evaluated against intersection/insider."
- **Non-regression:** all defenses default OFF ⇒ engine bit-identical (re-run `test_engine_fidelity.py`, `test_engine_airtime.py`, `test_engine_anonymity.py`, `test_integration_percolation.py`, `test_scenario_anonymity.py`).
- **Determinism:** mixing delays drawn from a **dedicated substream `cfg.rng(5)`** (reserved; disjoint from 0/1/2/(3,i)/4/6), guarded so `mixing_lambda=0` draws nothing. Extend the disjointness test.
- **Confound controls are mandatory (spec §5):**
  - **Mixing TTL=∞ timing-only arm** — mixing can "improve anonymity" merely by *dropping* messages (TTL expiry → fewer adversary samples). Re-measure mixing at `ttl=BIG`: if the localization-error gain *survives* ⇒ real timing-scramble; if it *vanishes* ⇒ it was message-dropping → the gate refuses to credit mixing.
  - **Relay-density control for the gate** — the gate's "hidden among relays" is meaningless if few relays exist; confirm the rank gain holds at realistic relay density, not a low-density artifact.
- **The gate is scored by the origin-vs-relay estimator** (not just first-spy) — else the gate gets unfair credit (an omniscient adversary geometrically separates origin from relay).
- **No `sender`/`recipient` tokens in engine-layer files** (lint). **`λ` fixed venue-wide** (a per-node/location rate is itself a fingerprint — spec §5/§10).

## File Structure
- `sim/soup_sim/config.py` — MODIFY: `mixing_lambda, originate_gate_relays, originate_gate_time` (default-off).
- `sim/soup_sim/engine.py` — MODIFY: per-(node,blob) forward delay (mixing); per-node relay count + origin-gate in `_offerable`.
- `sim/soup_sim/adversary.py` — MODIFY: `origin_vs_relay` estimator.
- `sim/soup_sim/scenario.py` — MODIFY: defense arms + confound controls + defense-power gate.
- `sim/soup_sim/anonymity.py` — MODIFY: `defense_gate(...)` + `DEFENSE_SCOPE_TAG`.
- `sim/soup_sim/report.py`, `sim/run.py`, `sim/README.md` — MODIFY: defense CSV/CLI/docs.
- Tests: `test_engine_anonymity.py`, `test_adversary.py`, `test_anonymity.py`, `test_scenario_anonymity.py` (MODIFY); `test_config.py` (MODIFY).

---

## Task 1: Poisson mixing delay (default-OFF, bit-identical)

**Files:** Modify `config.py`, `engine.py`; Test `tests/test_engine_anonymity.py`.
**Interfaces:** `Config.mixing_lambda: float = 0.0`. When >0, each node, on acquiring a blob, draws an `Exp(λ)` hold; the blob is **forwardable only after** `acquired + delay`. λ=0 ⇒ no hold ⇒ bit-identical. Delays from `cfg.rng(5)`, drawn only when λ>0.

- [ ] **Step 1: failing test**
```python
# tests/test_engine_anonymity.py (append)
def test_mixing_delays_forwarding():
    # 3 static nodes in a line A(0)-B(9)-C(18): A holds blob; with a large mixing hold on B,
    # C cannot receive until B's hold elapses. Compare delivery time to no-mixing.
    import numpy as np
    from soup_sim.config import Config
    from soup_sim.mobility import Mobility
    from soup_sim.engine import Engine
    from soup_sim.budget import AirtimeBudget
    from soup_sim.buffer import NodeBuffer
    from soup_sim.blob import Blob
    BIG = 10 ** 9
    def run(lam):
        c = Config(n=3, width=2000.0, height=200.0, radius=10.0, boundary="walls", mobility="static",
                   speed_min=0.0, speed_max=0.0, dt=1.0, ttl=1e12, buffer_cap=BIG, throughput_ideal=1e12,
                   alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=1.0,
                   drain=0.0, n_messages=0, seen_margin=1e12, master_seed=1, mixing_lambda=lam)
        pos = np.array([[0., 50.], [9., 50.], [18., 50.]])
        mob = Mobility("static", pos, np.zeros_like(pos), c.width, c.height, 0.0, 0.0)
        bufs = [NodeBuffer(BIG, 1e12, c.rng(3, i)) for i in range(3)]
        eng = Engine(c, mob, bufs, AirtimeBudget(1e12, 0, 0, 0, 1.0), c.rng(1), on_deliver=lambda *_: None)
        eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
        eng.run_until(50.0); eng.finalize()
        return eng.acquired.get((2, 0))           # when C got the blob (None if never)
    t_nomix = run(0.0)
    t_mix = run(5.0)                              # heavy mixing
    assert t_nomix is not None and t_nomix <= 1.0  # no-mix: C gets it ~immediately (multi-hop fixpoint)
    assert t_mix is None or t_mix > t_nomix        # mixing delays (or prevents within window) C's receipt
```
- [ ] **Step 2: run → FAIL** (`mixing_lambda` unknown).
- [ ] **Step 3:** `config.py`: add `mixing_lambda: float = 0.0` (validate ≥0). `engine.__init__`: `self.forward_delay = {}` (per (node,blob_id)); `self._mix_rng = rng` is NOT it — add a param/derive. (The engine already gets one `rng`; add the mixing draw from a dedicated generator passed in, or `cfg.rng(5)`. Simplest: the Engine constructor takes the cfg, so use `cfg.rng(5)` lazily, only when λ>0.) On acquire (in `_exchange` after accept, and in `inject`), if `cfg.mixing_lambda > 0`: `self.forward_delay[(node,bid)] = self._mix_rng.exponential(1.0/λ)` else 0. In `_offerable`, add: `if self.acquired[(src,bl.id)] + self.forward_delay.get((src,bl.id),0.0) > exit_ + _EPS: continue`.
- [ ] **Step 4: run → PASS** + non-regression (`test_engine_fidelity.py`, `test_engine_anonymity.py`) green (λ=0 default unchanged).
- [ ] **Step 5: commit** `feat(sim): Poisson mixing delay (default-OFF, dedicated RNG) — anonymity defense`

---

## Task 2: Receive-before-originate gate (default-OFF, bit-identical)

**Files:** Modify `config.py`, `engine.py`; Test `tests/test_engine_anonymity.py`.
**Interfaces:** `Config.originate_gate_relays: int = 0`, `originate_gate_time: float = 0.0`. A node's **own originated** blob is forwardable only after the node has **relayed ≥ G others' blobs** (or been alive ≥ T). 0/0 ⇒ off ⇒ bit-identical. Engine tracks `self.relayed_count[node]` (incremented in `_exchange` when a node forwards a blob it did NOT originate).

- [ ] **Step 1: failing test**
```python
# tests/test_engine_anonymity.py (append)
def test_originate_gate_holds_origin_until_relays():
    # origin (node0) holds its own blob; with G=2, it cannot emit until it has relayed 2 others'.
    # Construct so node0 relays others first, then its own becomes forwardable.
    ... (origin with own blob + 2 foreign blobs to relay; assert own blob not forwarded to a peer
         until relayed_count>=2; with G=0 it forwards immediately)
```
- [ ] **Step 2: run → FAIL.**
- [ ] **Step 3:** `config.py`: add the two fields (validate ≥0). `engine`: `self.relayed_count = {}`; in `_exchange`, when `src` forwards `blob` with `self.origin.get(blob.id) != src`, increment `self.relayed_count[src]`. In `_offerable`, for a blob where `self.origin.get(bl.id) == src` (the node's OWN origination): gate it — skip unless `self.relayed_count.get(src,0) >= cfg.originate_gate_relays` AND `self.t - <node-alive-since> >= cfg.originate_gate_time`. (Alive-since = 0 for all in-sim; the relay count is the operative gate.)
- [ ] **Step 4: run → PASS** + non-regression green (0/0 default).
- [ ] **Step 5: commit** `feat(sim): receive-before-originate gate (default-OFF) — anonymity defense`

---

## Task 3: Origin-vs-relay estimator (the adversary that defeats the gate)

**Files:** Modify `adversary.py`; Test `tests/test_adversary.py`.
**Interfaces:** `estimate("origin_vs_relay", msg_hearings, receivers, cand_pos, rng, reach=...)` — down-weights candidates whose **first-hold of the id was preceded by an in-range upstream holder** (a true relayer): a true originator's first emission has no upstream source of that id; a relayer's does. Uses the reach/position info already computed for the reachability estimator. Returns `{point, scores}` like the others; added to the "best per message" set.

- [ ] **Step 1: failing test** — on a constructed case where the true origin has no upstream and a relayer does, origin_vs_relay ranks the true origin above the relayer (and a plain first-spy that ignores upstream does worse on this case).
- [ ] **Step 2: run → FAIL.**
- [ ] **Step 3:** implement. Score candidate c by (reachability residual) + a penalty if c's earliest plausible hold-time has an in-range earlier holder of the id (⇒ likely a relayer, not origin). Reuse `reach`/`forward_reach`-style info from `scenario._forward_reach_matrix`.
- [ ] **Step 4: run → PASS.**
- [ ] **Step 5: commit** `feat(sim): origin-vs-relay estimator (defeats the receive-before-originate gate)`

---

## Task 4: Defense gate + scope disclaimer

**Files:** Modify `anonymity.py`; Test `tests/test_anonymity.py`.
**Interfaces:** `DEFENSE_SCOPE_TAG` (str); `defense_gate(baseline_rank1, defended_rank1, mustlocalize_ok, timing_only_gain_survives) -> {"credited": bool, "label": str}` — a mixing/gate defense's anonymity gain is creditable only if: (a) the capability control passed on the *baseline* (must-localize ok — the attack works, so a drop is real), (b) the defended rank-1 is materially below baseline, AND (c) for mixing, the gain SURVIVES the TTL=∞ timing-only control (`timing_only_gain_survives`). Else label "gain is message-dropping, not timing-scramble" / "estimator inconclusive."

- [ ] **Step 1: failing test** — defense credited when baseline localizes + defended drops + timing-only survives; NOT credited when the gain vanishes at TTL=∞ (message-dropping) or must-localize failed.
- [ ] **Step 2: run → FAIL.**
- [ ] **Step 3:** implement against pre-registered margins.
- [ ] **Step 4: run → PASS.**
- [ ] **Step 5: commit** `feat(sim): defense-power gate (credits a defense only vs a working attack + survives the drop-confound)`

---

## Task 5: Defense sweep arms + confound controls

**Files:** Modify `scenario.py`; Test `tests/test_scenario_anonymity.py`.
**Interfaces:** `anonymity_defense_sweep(base_cfg, f, reps) -> {"arms": {baseline, mixing, gate, both}, "timing_only", "relay_density", "defense_gate", "scope_tag"}` — at a fixed (high) coverage f, measure rank-1 + delivery + T50 + buffer-occupancy for each arm; the gate arm scored by `origin_vs_relay`; the **TTL=∞ timing-only** arm for mixing; a **relay-density** check for the gate; feed `defense_gate`. Deterministic; per-message conditional-on-detection; scope + defense-scope tags. Heavy → `@pytest.mark.slow` realistic; a tiny fast smoke for structure/determinism.

- [ ] **Step 1: failing test (tiny smoke + slow realistic)** — smoke: structure/determinism + arms present + tags; slow: mixing and/or gate reduce rank-1 vs baseline AND (for mixing) the gain survives TTL=∞.
- [ ] **Step 2: run → FAIL.**
- [ ] **Step 3:** implement, reusing `_run_one_anonymity`/`_score_arm` with the defense cfgs (`replace(base_cfg, mixing_lambda=...)`, `replace(..., originate_gate_relays=...)`, both; and the TTL=∞ variant).
- [ ] **Step 4: run → PASS** (+ `test_scenario_anonymity.py` green).
- [ ] **Step 5: commit** `feat(sim): anonymity defense sweep (mixing/gate/both arms + TTL=inf & relay-density confound controls)`

---

## Task 6: Report + CLI + docs

**Files:** Modify `report.py`, `run.py`, `README.md`; Test `tests/test_report.py`.
**Interfaces:** defense CSV (rank-1 per arm + delivery/T50/buffer cost + defense-gate verdict, scope + defense-scope tags as columns); `run.py --preset anonymity-defenses` (prints each arm's rank-1 vs baseline, the confound-control verdicts, the defense-gate credit/label, both tags); README slice-3 PR-2 section + bias rows (mixing-as-drop confound; λ fixed venue-wide idealization; gate metadata-free idealization).

- [ ] **Step 1: failing test** — CSV carries per-arm rank-1 + both tags as columns; enforcement test (CLI stdout + plot title contain the tags).
- [ ] **Step 2: run → FAIL.**
- [ ] **Step 3:** implement + write README rows.
- [ ] **Step 4: run → PASS + FULL default suite green** (`pytest -q`); `pytest -m slow -q` passes; `run.py --preset anonymity-defenses` prints verdicts + tags.
- [ ] **Step 5: commit** `feat(sim): anonymity defense CSV/plot + preset + slice-3 PR-2 docs`

---

## Self-Review
**Spec coverage (§5):** Poisson mixing (fixed λ, dedicated RNG) Task 1; receive-before-originate gate Task 2; origin-vs-relay estimator (so the gate is measured, not asserted) Task 3; defense-power gate + scope disclaimer Task 4; both-on arm + **TTL=∞ timing-only confound control** + **relay-density control** Task 5; delivery/T50/buffer cost reported per arm Tasks 5–6.
**Honesty:** every number an UPPER BOUND; scope + defense-scope tags travel; a defense gain is credited only against a working attack (must-localize) that isn't message-dropping (TTL=∞) and (for the gate) at realistic relay density, scored by an adversary that tries to defeat it (origin-vs-relay).
**Non-regression:** all defenses default-off ⇒ bit-identical; Tasks 1,2 re-run the merged gates.
**Determinism:** mixing RNG = `cfg.rng(5)` (guarded), disjointness test extended.
**Judgment call (build-time):** the defense parameters (λ, G) are uncalibrated knobs — sweep/report the anonymity-gain-vs-cost tradeoff curve rather than a single point; if a defense doesn't beat its confound control, report the honest null ("mixing's apparent gain was message-dropping").
