# polleneus — P6: Continuous verification (CI gates + internet-disabled CI + audit protocols)

**Version:** v0.1 — 2026-06-28 · **Roadmap:** P6 (§16) · **Parent design:** [polleneus v0.5 §16-P6](2026-06-25-polleneus-design.md) · **Blocker:** B5

> **Why this serves the mission.** A model that *was* honest can silently rot as it evolves. P6 makes the
> simulator's hard-won gates **executable on every change**, and — because polleneus is **offline-first** —
> proves in CI that the tool needs **no network at runtime.** It also writes down the audit protocols that a
> shippable client will need but the sim cannot run (hardware/USRP, multi-OS transport), so they are tracked,
> not forgotten. **Honest scope:** P6 verifies the **simulator**; the **client-side** gates are OPEN (there is
> no client yet) and stay OPEN until one exists — CI green here is *not* a ship signal (B1 still gates that).

## 1. What P6 enforces now vs what is owed

> **Automation status (honest):** the **gates themselves are committed and run via `pytest` today** — the
> offline-first guard (`test_offline_first.py`) and all sim gates are in the suite (242 passing). The
> **GitHub Actions YAMLs that auto-run them on push/nightly are authored** (`.github/workflows/ci.yml`,
> `gates-nightly.yml`) **but NOT yet committed** — the `polleneus-dev` push token lacks the `workflow` scope
> GitHub requires for workflow files. **Needs the user:** grant the token `workflow` scope (or add the two
> files manually); they are ready in the working tree. So "runs in CI on every push" is **PENDING that one
> credential change**; everything below runs locally via `pytest` now.

| Gate | Status (this PR) |
|---|---|
| Sim FAST suite green (percolation oracle, airtime, anonymity gates) | **ENFORCED via `pytest`** (242 passing); auto-run `ci.yml` job `test` **authored, commit PENDING `workflow` token scope** |
| **Internet-disabled GUARD** (no runtime network on the common socket stack) | **ENFORCED in-repo** — `test_offline_first.py` runs every `pytest`; whole-fast-suite `offline-first` CI job authored (PENDING scope). A regression guard, **not a proof** — subprocess/C-level network out of scope (the sim has no network code today, so this pins that) |
| Heavy realistic-sweep gates (airtime n~154, intersection, defense, `-m slow`) | runnable via `pytest -m slow`; **CONFIGURED nightly + on-demand** in `gates-nightly.yml` (authored, PENDING scope). **Timing UNVERIFIED on CI hardware** (one slow test >280 s locally; confirm the set fits the 45-min cap via a `workflow_dispatch` run before relying on it). Kept OFF the per-push path — the engine is super-linear in crowd size |
| Multi-OS BLE transport conformance harness | **OWED** (no client; protocol §4) |
| Adversarial-eviction CI gate (client buffer) | **OWED** (no client; protocol §4) |
| USRP PHY self-audit (device-linkability number, B2) | **OWED** (hardware; protocol §4) |
| Adversarial source-estimator audit (realized origination-identifiability, B2) | **OWED** (hardware/field; protocol §4) |

## 2. The CI (this PR — `.github/workflows/ci.yml`)

- **`test`** — `pip install -e .[dev]` then `pytest -q` (the fast suite). The simulator's gates live inside
  the suite, so this keeps them green as the model evolves.
- **`offline-first`** — same, with `POLLENEUS_OFFLINE_CI=1`. `tests/conftest.py` then **rebinds the socket
  module's connection entry points (`socket.socket`/`create_connection`/`getaddrinfo`) to raise, in-process**,
  for the whole **fast** suite, so any code path that reached the network on that stack fails CI. (Build-time
  `pip install` may fetch deps — the guard activates only during the test session, so this guards the
  **runtime**, which is the offline-first claim. **Scope:** a regression guard over the common socket-based
  stack, **not** a proof — subprocess / C-level network are out of scope. Slow sweeps are deselected by
  `addopts`; they contain no network code either.)
- **`gates-nightly.yml` → `gates-slow`** — `pytest -q -m slow` on a **nightly schedule + manual dispatch**
  (not per-push). The realistic sweeps (airtime knee at n~154, intersection-sharpening, defense-NULL) are
  minute-to-tens-of-minutes because **the engine is super-linear in crowd size** (perf note / task tracked
  separately) — so they are kept off the per-change path to keep push CI fast, but still exercised regularly.
  `timeout-minutes` bounds every job (the bounded-sweep discipline: a runaway must never hang CI).
- **In-repo offline-first gate (always-on, not just CI):** `tests/test_offline_first.py` blocks sockets and
  runs a real delivery run + a scenario sweep, so the offline-first invariant is checked on **every local
  `pytest`**, independent of the CI env var.

## 3. The sim gates being kept green (already in-repo; CI now runs them)

- **Percolation oracle** (`tests/test_integration_percolation.py`): in the static unbounded regime the
  engine's multi-hop fixpoint delivers *exactly* the union-find same-component pairs (independent algorithm
  cross-check), and susceptibility peaks near `d_c ≈ 4.51` (giant absent below / dominant above).
- **Airtime publish-gate**: the binding-constraint verdict (delivery vs circulation) is computed, not
  asserted; the gate refuses optimistic publication.
- **Anonymity gates**: must-localize / exposure / defense-NULL / intersection — the slice-3/P2 honest
  negatives are pinned so a future change can't silently turn a disclosed limit into a false guarantee.
- **Default-inert / bit-identity gates** across P1–P4 knobs (each opt-in knob proven a no-op when off).

These are the project's anti-false-confidence ratchet: a regression that weakened a disclosed limit, or
turned a measured upper bound into a claim, breaks CI.

## 4. Owed audit protocols (written plans — hardware/client-gated, B2/B5)

These cannot run in the sim CI (they need a real radio stack / handset / multi-OS devices). Written here so
they are tracked release gates, not forgotten:

1. **USRP PHY self-audit (B2):** with a software-defined radio, measure the **real device-linkability**
   number (PHY fingerprint stability across sessions) — the assumed-1.0 linkage in the anonymity sim must be
   replaced by a measured figure before any "anonymous" copy. Output: a published linkability probability +
   method.
2. **Adversarial source-estimator audit (B2):** run a real passive receiver-grid source estimator against a
   live deployment and **publish the realized origination-identifiability probability** (the sim gives a
   model upper bound; the field number is owed). Must include a clustered-"gathering" deployment (the sim is
   RWP/clustered-model only).
3. **Multi-OS BLE transport conformance harness (B5):** once a client exists, a device matrix
   (Android/iOS versions) verifying the advertising/GATT framing is byte-uniform / non-fingerprintable
   (invariant 4) and that fragmentation/MTU behaviour matches across OSes.
4. **Adversarial-eviction CI gate (B5):** a client-side test that a flooding adversary cannot evict honest
   mail faster than the oldest-by-creation policy + P3 hold-budget allow (the sim models this; the client
   must too).
5. **Crypto/key-management audit (B1):** the external adversarial audit of the P5 stack against its §10
   open-questions list — the hardest gate; gates every ship decision.

## 5. Honest scope

- **CI green ≠ ship-ready.** P6 verifies the *simulator* and the offline-first runtime property. **B1 (audit)
  still gates any installable build;** the client-side gates (§4) are OPEN until a client exists.
- **Internet-disabled is a runtime GUARD, not a proof and not a supply-chain check** — it shows the sim makes
  no network calls on the common socket stack when running (in-process; subprocess/C-level out of scope); it
  does not audit the build/dependency chain (a separate, later concern for the client).
- **The owed audits (§4) are real release gates,** carried in B2/B5 — not closed by this PR, only written down.

## 6. Plan sketch

1. `.github/workflows/ci.yml`: `test` (fast gates) + `offline-first` (whole suite, sockets blocked) +
   `gates-slow` (heavy sweeps).
2. `sim/tests/conftest.py`: env-gated session-wide socket block (`POLLENEUS_OFFLINE_CI=1`).
3. `sim/tests/test_offline_first.py`: always-on in-repo offline-first gate (blocks sockets around a real run).
4. This spec + release-blockers B5 update.
5. Fan-out review; PR (`--base main`); merge.
