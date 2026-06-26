# Anonymity Slice 3 · PR-2 — Defenses (mixing + receive-before-originate) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans). Steps use `- [ ]` checkboxes.

> **v2 (folds plan-review round 1):** the confound control was not rigorous — added the spec-mandated **same-detected-set intersection** (TTL=∞ alone can't isolate timing-scramble from drop in a finite window); fixed the **persistent mixing RNG** (`cfg.rng(5)` is fresh per call — must be one generator) + the **inverted-λ** Task-1 test (heavy mixing = small λ); **threaded the origin-vs-relay estimator's `upstream` input** (uncomputable from the old signature); relay-count = **distinct ids**; relay-density metric + `MIN_RELAY_DENSITY`; `defense_gate` gated on intersection-set rank-1; `deliver_t` includes the mixing hold; disjointness test extended to tags 4/5/6; gate-deadlock documented as a delivery/latency cost.

**Goal:** On the trusted PR-1 exposure apparatus (which measured ~29% originator exact-catch at high passive-grid coverage, capability-gate-confirmed), measure whether the design's two cheapest defenses — **Poisson mixing delay** and the **receive-before-originate gate** — actually cut that leak, and at what delivery/latency cost. The honest question: do they work, against an adversary that *tries* to defeat them?

**Architecture:** Additive, all behind default-OFF config (`mixing_lambda=0`, `originate_gate_relays=0`, `originate_gate_time=0`) ⇒ engine bit-identical to the merged state (PR-1 + slices 1–2 gates stay green). Defenses hook into the engine's `_offerable` forwardability guard and `_exchange` relay accounting. A new **origin-vs-relay** estimator gives the adversary a real shot at defeating the gate. `scenario.py` gains defense arms (baseline / mixing / gate / both) with the spec's mandatory **confound controls** (TTL=∞ timing-only for mixing; relay-density for the gate) and a **defense-power gate**. Every number stays an UPPER BOUND on anonymity with the scope tag (PR-1's honesty machinery).

**Tech Stack:** Python 3, numpy, pytest (`pythonpath=["."]`), matplotlib (optional). Determinism via `cfg.rng(*path)`.

## Global Constraints
- **Every anonymity number is an UPPER BOUND on anonymity**; scope tag travels (PR-1 `SCOPE_TAG`). **Defense-scope disclaimer** on every defense-gain number: "gain vs the single-event passive-grid adversary only; NOT evaluated against intersection/insider."
- **Non-regression:** all defenses default OFF ⇒ engine bit-identical (re-run `test_engine_fidelity.py`, `test_engine_airtime.py`, `test_engine_anonymity.py`, `test_integration_percolation.py`, `test_scenario_anonymity.py`).
- **Determinism:** mixing delays drawn from a **dedicated substream `cfg.rng(5)`** (reserved; disjoint from 0/1/2/(3,i)/4/6), guarded so `mixing_lambda=0` draws nothing. Extend the disjointness test.
- **Confound controls are mandatory (spec §5) — and TTL=∞ ALONE IS NOT ENOUGH.** Mixing can "improve anonymity" two ways that aren't timing-scramble: (i) TTL expiry drops messages (fewer adversary samples); (ii) even at TTL=∞, the *slowed* epidemic means fewer holders reach a receiver **within the finite sim window**, so the detected-set still shrinks. Computing rank-1 *conditional on detection* then suffers survivorship (the dropped messages may be the easy exact-catches). So BOTH spec controls are required, conjoined:
  - **Same-detected-message-set intersection (spec §5, was missing in v1).** Compare rank-1 across arms only over `S = S_baseline ∩ S_defended ∩ S_ttl∞` (messages detected in *all* compared arms). This removes the survivorship channel directly.
  - **TTL=∞ timing-only arm.** Re-measure mixing at `ttl=BIG` AND **verify TTL=∞ restores the detected-set size to ~baseline** (size `drain` so the slowed epidemic fully spreads in-window — assert `|S_ttl∞| ≈ |S_baseline|`). If the error/rank gain survives on the intersection set AND at restored-detected-set TTL=∞ ⇒ real timing-scramble; else ⇒ message-dropping → `defense_gate` refuses to credit mixing.
  - **Relay-density control for the gate.** Metric = mean distinct foreign blob-ids available to relay per node at gate-eligibility time; pre-register a minimum (`MIN_RELAY_DENSITY`). Below it, the gate arm is labeled "low-density artifact, not credited" (the "hidden among relays" claim is vacuous with few relays).
- **Mixing RNG is ONE PERSISTENT generator.** `cfg.rng(5)` returns a FRESH generator each call (drawing per-acquire would repeat one constant — not Poisson). Create `self._mix_rng = cfg.rng(5)` ONCE in `__init__`, only when `mixing_lambda > 0` (so λ=0 never instantiates/draws ⇒ bit-identical), and draw every hold from it.
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
    t_mix = run(0.05)                            # HEAVY mixing = SMALL lambda (Exp mean 1/lambda = 20s)
    assert t_nomix is not None and t_nomix <= 1.0  # no-mix: C gets it ~immediately (multi-hop fixpoint)
    assert t_mix is None or t_mix > t_nomix        # mixing delays (or prevents within window) C's receipt
```
- [ ] **Step 2: run → FAIL** (`mixing_lambda` unknown).
- [ ] **Step 3:** `config.py`: add `mixing_lambda: float = 0.0` (validate ≥0). `engine.__init__`: `self.forward_delay = {}` (per (node,blob_id)); **`self._mix_rng = cfg.rng(5) if cfg.mixing_lambda > 0 else None`** — ONE persistent generator created once (NOT `cfg.rng(5)` per draw — that returns a fresh generator each call and would repeat one constant). On acquire (in `_exchange` after accept, and in `inject`), **guarded by `if cfg.mixing_lambda > 0`**: `self.forward_delay[(node,bid)] = self._mix_rng.exponential(1.0/cfg.mixing_lambda)`. In `_offerable`, add: `if self.acquired[(src,bl.id)] + self.forward_delay.get((src,bl.id),0.0) > exit_ + _EPS: continue`. In `_exchange`, set `deliver_t = max(enter, self.acquired[(src,blob.id)] + self.forward_delay.get((src,blob.id),0.0))` so the recorded hear-time reflects the mixing hold (not the step-quantized acquire). Add a test asserting λ=0 advances `self._mix_rng` zero times (it's None) ⇒ bit-identical. **Extend the RNG-disjointness test** (`test_config.py`/`test_scenario.py`) to assert tags **4, 5, 6** produce streams disjoint from 0/1/2/(3,i) and from each other (4 and 6 went in untested in PR-1).
- [ ] **Step 4: run → PASS** + non-regression (`test_engine_fidelity.py`, `test_engine_anonymity.py`) green (λ=0 default unchanged).
- [ ] **Step 5: commit** `feat(sim): Poisson mixing delay (default-OFF, dedicated RNG) — anonymity defense`

---

## Task 2: Receive-before-originate gate (default-OFF, bit-identical)

**Files:** Modify `config.py`, `engine.py`; Test `tests/test_engine_anonymity.py`.
**Interfaces:** `Config.originate_gate_relays: int = 0`, `originate_gate_time: float = 0.0`. A node's **own originated** blob is forwardable only after the node has **relayed ≥ G others' blobs** (or been alive ≥ T). 0/0 ⇒ off ⇒ bit-identical. Engine tracks `self.relayed_count[node]` (incremented in `_exchange` when a node forwards a blob it did NOT originate).

- [ ] **Step 1: failing test (concrete — the gate has subtle deadlock/count semantics)**
```python
# tests/test_engine_anonymity.py (append)
def test_originate_gate_holds_origin_until_relays():
    # node0 holds its OWN blob (id 100) + can relay 2 foreign blobs (ids 1,2 injected at node1, node2,
    # which are in range of node0). With G=2, node0's own blob must NOT reach a peer until node0 has
    # relayed both foreign ids; with G=0 it leaves immediately.
    import numpy as np
    from soup_sim.config import Config
    from soup_sim.mobility import Mobility
    from soup_sim.engine import Engine
    from soup_sim.budget import AirtimeBudget
    from soup_sim.buffer import NodeBuffer
    from soup_sim.blob import Blob
    BIG = 10 ** 9
    def run(G):
        c = Config(n=4, width=2000.0, height=200.0, radius=10.0, boundary="walls", mobility="static",
                   speed_min=0.0, speed_max=0.0, dt=1.0, ttl=1e12, buffer_cap=BIG, throughput_ideal=1e12,
                   alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=1.0,
                   drain=0.0, n_messages=0, seen_margin=1e12, master_seed=1, originate_gate_relays=G)
        pos = np.array([[0., 50.], [9., 50.], [18., 50.], [200., 50.]])  # node3 = a peer to receive node0's own
        mob = Mobility("static", pos, np.zeros_like(pos), c.width, c.height, 0.0, 0.0)
        bufs = [NodeBuffer(BIG, 1e12, c.rng(3, i)) for i in range(4)]
        eng = Engine(c, mob, bufs, AirtimeBudget(1e12, 0, 0, 0, 1.0), c.rng(1), on_deliver=lambda *_: None)
        eng.inject(Blob(100, 0.0, 1e12, 1.0), 0)   # node0's OWN
        eng.inject(Blob(1, 0.0, 1e12, 1.0), 1)     # foreign, node0 will relay
        eng.inject(Blob(2, 0.0, 1e12, 1.0), 2)     # foreign (reaches node0 via node1 multi-hop)
        eng.run_until(5.0); eng.finalize()
        return eng.buffers[1].has(100)             # did node0's OWN blob reach a peer (node1)?
    assert run(0) is True                          # gate off: own blob leaves immediately
    # gate on (G=2): node0 must relay ids 1 AND 2 before its own can leave. (If it can't reach G,
    # its own blob is legitimately suppressed — modeled as origination-latency/undelivered cost, not a bug.)
```
- [ ] **Step 2: run → FAIL.**
- [ ] **Step 3:** `config.py`: add the two fields (validate ≥0). `engine`: `self.relayed = {}` (node → **set of distinct foreign blob-ids forwarded**, to match spec "≥ G ids", not per-forward events). In `_exchange`, when `src` forwards `blob` with `self.origin.get(blob.id) != src`, do `self.relayed.setdefault(src,set()).add(blob.id)`. In `_offerable`, for a blob where `self.origin.get(bl.id) == src` (the node's OWN origination): skip unless `len(self.relayed.get(src,())) >= cfg.originate_gate_relays` AND `self.t >= cfg.originate_gate_time`. **Deadlock-is-correct-model:** an isolated origin that never relays G keeps its own blob suppressed — a faithful model of the gate's cost; ensure such never-emitted originations are counted as a delivery/latency cost (NOT dropped from the denominator), so the gate can't bank isolation as anonymity (a survivorship cousin of the mixing confound). Both `_offerable` guards (mixing + gate) are independent `continue`s; the both-arm cost is their composition.
- [ ] **Step 4: run → PASS** + non-regression green (0/0 default).
- [ ] **Step 5: commit** `feat(sim): receive-before-originate gate (default-OFF) — anonymity defense`

---

## Task 3: Origin-vs-relay estimator (the adversary that defeats the gate)

**Files:** Modify `adversary.py`; Test `tests/test_adversary.py`.
**Interfaces:** `estimate("origin_vs_relay", msg_hearings, receivers, cand_pos, rng, reach=..., upstream=...)` — NEW `upstream` kwarg: a per-candidate vector `upstream[c]` (bool/score) meaning "candidate c's earliest plausible hold of this id was preceded by an in-range *upstream* holder" (⇒ likely a relayer, not the origin). The estimator legitimately uses the position oracle (spec §3): `upstream` is computed adversary-side in `_score_arm` from `position_log` + the forward-infection times (`_forward_infection`), NOT from the engine's private `acquired`. Score = reachability residual + a large penalty when `upstream[c]` is set. Returns `{point, scores}`; added to the "best per message" set (and is the estimator the GATE arm is scored by).

- [ ] **Step 1: failing test (concrete, must beat first-spy)** — construct a message where the true origin has NO upstream holder and a decoy relayer DOES (pass `upstream` with the relayer flagged): assert `origin_vs_relay` ranks the true origin strictly above the relayer, AND that plain `first_spy` (which ignores `upstream`) ranks the relayer at-or-above the origin on this case (proving the upstream signal is what defeats the gate).
- [ ] **Step 2: run → FAIL.**
- [ ] **Step 3:** implement `estimate` branch (reachability score + `UPSTREAM_PENALTY` where `upstream[c]`). In `scenario._score_arm`, compute `upstream[c]` for each candidate = "is there another node k≠c with a forward-infection/first-hold time of this id earlier than c AND within range of c at c's hold time" (from `position_log` + `_forward_infection`). Define "earliest plausible hold-time" of c = its forward-infection time from the observed spread. Thread `upstream` into the `origin_vs_relay` call.
- [ ] **Step 4: run → PASS.**
- [ ] **Step 5: commit** `feat(sim): origin-vs-relay estimator (defeats the receive-before-originate gate)`

---

## Task 4: Defense gate + scope disclaimer

**Files:** Modify `anonymity.py`; Test `tests/test_anonymity.py`.
**Interfaces:** `DEFENSE_SCOPE_TAG` (str); `defense_gate(baseline_rank1, defended_rank1, mustlocalize_ok, timing_only_gain_survives, relay_density_ok=True) -> {"credited": bool, "label": str}`. **The `baseline_rank1`/`defended_rank1` passed in MUST already be computed on the SAME-DETECTED-SET intersection (Task 5), not raw per-arm — that's where survivorship is removed.** Creditable only if: (a) capability control passed on the baseline (must-localize ok — the attack works, so a drop is real), (b) defended rank-1 materially below baseline on the intersection set, (c) for mixing, the gain SURVIVES the TTL=∞ timing-only control with restored detected-set (`timing_only_gain_survives`), AND (d) for the gate, `relay_density_ok` (enough relays to hide among). Else label "gain is message-dropping/survivorship, not timing-scramble" / "low-density artifact" / "estimator inconclusive."

- [ ] **Step 1: failing test** — defense credited when baseline localizes + defended drops + timing-only survives; NOT credited when the gain vanishes at TTL=∞ (message-dropping) or must-localize failed.
- [ ] **Step 2: run → FAIL.**
- [ ] **Step 3:** implement against pre-registered margins.
- [ ] **Step 4: run → PASS.**
- [ ] **Step 5: commit** `feat(sim): defense-power gate (credits a defense only vs a working attack + survives the drop-confound)`

---

## Task 5: Defense sweep arms + confound controls

**Files:** Modify `scenario.py`; Test `tests/test_scenario_anonymity.py`.
**Interfaces:** `anonymity_defense_sweep(base_cfg, f, reps) -> {"arms": {baseline, mixing, gate, both}, "timing_only", "relay_density", "defense_gate", "scope_tag", "defense_scope_tag"}` — at a fixed (high) coverage f, run each arm via `replace(base_cfg, mixing_lambda=…/originate_gate_relays=…)`, the mixing `timing_only` arm via `replace(..., ttl=BIG)`. **Compute rank-1 on the SAME-DETECTED-SET intersection** `S = ∩ detected-ids across (baseline, the defended arm, timing_only)` — this is the survivorship fix; report raw per-arm rank-1 too but gate on the intersection. **Assert `|S_ttl∞| ≈ |S_baseline|`** (size `drain` so the slowed epidemic spreads in-window; if not restored, flag the timing-only control invalid). Compute the **relay-density metric** (mean distinct foreign ids available per node at gate-eligibility) vs `MIN_RELAY_DENSITY`. Report rank-1 + delivery + T50 + buffer-occupancy per arm; gate arm scored by `origin_vs_relay`; feed `defense_gate(...)`. Deterministic (`_seed_for(fi,rep)`, `cfg.rng(5)`); scope + defense-scope tags. Heavy → `@pytest.mark.slow` realistic; a tiny fast smoke for structure/determinism. Add `MIN_RELAY_DENSITY` + `UPSTREAM_PENALTY` + `MIN_INTERSECTION_SIZE` to `anonymity.py` constants. **`defense_gate` returns "inconclusive — intersection too small" when `|S| < MIN_INTERSECTION_SIZE`** (heavy mixing can shrink the same-detected-set toward empty → rank-1 on a near-empty set is noise; mirror of `MIN_MESSAGES_PER_RUN`). The `|S_ttl∞|≈|S_baseline|` check is a tolerance assert on a stochastic size — on failure, label the timing-only control INVALID (don't crash); size `drain` generously to avoid flakiness.

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
