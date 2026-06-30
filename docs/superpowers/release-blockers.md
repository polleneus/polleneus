# Polleneus — Release Blockers (v1)

**Status:** living tracking doc · **Created:** 2026-06-26 · **Owner gate:** CTO
**Parent design:** [polleneus v0.5](specs/2026-06-25-polleneus-design.md)

A release blocker is a condition that **must be cleared before any public/installable build ships**.
This doc consolidates the security constraints, the parent design's P5/P6 release gates, and the
measured findings from the simulator (slice 3) into one tracked list. Each blocker has a **status**:

- **OPEN** — not yet addressed; no work landed.
- **MEASURED-IN-SIM** — quantified in the simulator (an upper bound / model number), but the
  field/hardware number or the production mitigation is still owed.
- **ADDRESSED** — cleared, with the evidence linked.

The deadliest failure mode for this project is **false confidence** (parent §12.8): shipping while a
caveat reads as a guarantee. So a blocker is "cleared" only with linked evidence, never by assertion.

---

## B1 — No public/installable build before an independent security audit  ·  **OPEN**

No usable or installable artifact (APK/IPA/desktop) may be distributed before an independent,
adversarial security audit of the crypto, transport, and key-management stack. This is the
hardest gate and gates every other "ship" decision.

- **Why:** an offline-first anonymity tool that fails is worse than none — users act on a false
  promise in exactly the settings where exposure is dangerous.
- **Clear when:** a named external auditor signs off on the v1 stack (spend primitive, AEAD,
  key-evolution, transport) against a written threat model.
- **Now:** the codebase is a *simulator/research* tree, not a shippable client — so this is not
  yet imminent, but it must be formalized before any client work begins.
- **Audit target defined (P5):** the v1 key-management stack is now consolidated into one audit-ready
  artifact — [p5-key-management-spec.md](specs/2026-06-28-p5-key-management-spec.md) — with an explicit
  **§10 open-questions list for the auditor** (the load-bearing FS/puncturable-KEM construction; the FJB
  boot-reset gap; key-committing AEAD; deniability; X-Wing combiner; spend integration; SE/TEE
  erase/endurance; side-channels). It ships **no crypto code** and is marked UNAUDITED throughout.
- **Anti-flood transport audit item (added 2026-06-29, AF-3):** the parent §9.5 **per-PHY-session quota
  `Q`** is the fail-closed anti-flood / anti-ZK-bug backstop, but its enforceability on **commodity BLE is
  unproven.** A commodity phone cannot do USRP-class radiometrics (design §3 reserves rotation-surviving
  PHY fingerprinting to a USRP/SDR *adversary*), so a defender can key a "session" only by the **rotating
  Resolvable Private Address (RPA, ~15 min default) / per-connection handle** — which an attacker can
  **rotate per spend** to draw a fresh `Q` allowance. The auditor must determine whether `Q` is a real
  per-device backstop or collapses to **per-observed-session friction** (bounded only by serialized
  `t_setup` and K radios, folding into the §9.6 funded-device residual). See
  [p2-token-source-spec §2–§4](specs/2026-06-27-p2-token-source-spec.md). **Do not claim `Q` bounds a
  device.**
- **Pre-ship client hardening / strip-test-affordances checklist (added 2026-06-29, external review).** The
  prior in-loop red-team scoped itself to "design/spec text, no spike Java", so these real items lived only in
  spike code comments. An external read-only review surfaced them; **none may survive into a shippable client**,
  and the **exported-component / IPC surface is hereby named an explicit B1 audit-scope item** (it is not
  confidentiality-breaking today — service `exported=false`, event channel `RECEIVER_NOT_EXPORTED`,
  package-scoped — but it is a confused-deputy (CWE-926) class). Checklist:
  - [ ] **Exported control surface (C1):** the spike's exported `MainActivity` proxies the private service from
    external intent extras (the deliberate adb `--es` test interface). The client must NOT accept externally
    supplied control extras — make the activity non-exported except for LAUNCHER (or gate to self/signature
    intents); never rely on `service exported=false` behind an exported proxy. (The unbounded `handleInject`
    alloc is being bounded by `MAX_BLOB` now.)
  - [ ] **Fixed deterministic recipient key (H3):** the world-known `RECIPIENT_SEED` test scaffold + any
    default-recipient send path must be **removed**; no-contact send must **fail closed** (being removed now).
  - [ ] **Sensitive logging (H7):** the spike logs decrypted plaintext, SAS, pairing tokens, contact IDs by
    design (the lab tests grep them). The client must **redact / DEBUG-gate** all of these — a logcat ring
    buffer of plaintext + SAS is real data-at-rest under the seizure threat model.
  - [ ] **Raw key material at rest (H4):** spike `identity.dat` / `contacts.dat` store private keys + `K_auth`
    **unwrapped** (app-sandboxed but not keystore-wrapped). The **SE/TEE/StrongBox wrapping required by P5 §2**
    is owed at/before B1. (Spike caveat: keys are currently raw-at-rest — honest disclosure.)
  - [ ] **Pairing-trust gate (H1) + inbound-pairing consent (H2):** contact persistence + send must be gated on
    the **human SAS-match** (not key-confirmation alone), and inbound pairing must be **rejected when pair mode
    is off** (both being fixed in the spike now; carry the gate into the client spec as a build requirement).
  - [ ] **PQ-vs-classical durable marker (H5):** persist + surface a per-contact PQ flag (being added now).
  Owner/home: this checklist is the written home (decision: live here under B1, not only in code comments).

## B2 — Publish the realized sender-origin identifiability number  ·  **MEASURED-IN-SIM**

The parent design (§16-P6, P6) requires publishing the **realized origination-identifiability
probability** from an adversarial source-estimator audit + a USRP PHY self-audit — *before* any
"anonymous" claim. The simulator now provides the **model** number; the **field/USRP** number is owed.

- **Measured (sim, slice 3, all UPPER BOUNDS on anonymity):**
  - **PR-1** — single-event source localization against a passive receiver grid leaks the origin
    (rank-1 materially above the 1/N floor under realistic coverage). [`sim/` slice-3 PR-1]
  - **PR-2** — the cheap network-layer defenses (Poisson mixing λ=0.05, receive-before-originate
    gate G=3) do **NOT** materially cut that leak, and mixing costs delivery — the credit gate
    refuses both. [PR #9]
  - **PR-3** — **multi-session intersection deanonymizes a persistent sender**: fused rank-1 climbs
    ~0.09→0.72 over K=1→16 originations (decoy flat at 0.00, random floor ~1/N), crossing the
    exposure threshold — *under assumed device-linkage*. A single message ≈ anonymous; a persistent
    author is not. [PR #10]
- **Clear when:** the field/USRP device-linkability number is measured and published alongside the
  sim numbers, and the public-facing copy states the honest posture (below, B3).
- **Owed:** USRP PHY self-audit (real device-linkability, not assumed); a real-deployment source-
  estimator pass; clustered-mobility ("gathering") sweep (sim is RWP open-field only → optimistic).

## B3 — Honest anonymity posture in all user-facing copy  ·  **OPEN**

No unqualified "anonymous" claim. The honest, evidence-backed posture (reframed 2026-06-28 — see
[originator-anonymity-limit.md §8](../originator-anonymity-limit.md)):

- **What is protected (the crown jewels — SOLVED):** **content secrecy** (sealed, E2E) and **recipient
  anonymity** (pure flooding lands a message on ~everyone in the component, so receipt ≠ being the
  recipient). For the actual mission — coordinating locally when infrastructure is down — *what* you said
  and *who* you said it to are the dangerous facts, and both are hidden.
- **What origin-localization actually leaks: only "this device transmitted" — not the content, not the
  recipient.** And because every phone relays others' blobs (and may emit cover), "you transmitted" is
  largely the same membership signal as *running the app at all* — which is unavoidable for any radio tool.
  So the achievable, honest goal is **"originating blends into participating,"** not "hide the originator."
- **Single message:** roughly anonymous *against an adversary that cannot pick your blob out of the
  crowd's* — origination blends to ~1/(concurrent originators) (the "free cover" measurement). Useless
  against an adversary that can already identify the target blob.
- **Persistent, targeted, device-fingerprinted author: NOT protected** — multi-session intersection pins
  them (B2: rank-1 → 0.72 at K=16). This is an **accepted, disclosed limit, not a blocker to overcome** —
  it is the same limit every mesh tool (Briar, etc.) has, and it is **architecturally final** (no crypto
  opens it for a flood — the re-randomization escape is closed by Law 1; see the originator-anonymity-limit
  doc). polleneus is **not for a specifically-hunted persistent author under heavy surveillance**, and the
  copy must say so.
- **Existence of mesh traffic is detectable** — running the app is a membership signal in the most
  repressive settings (unavoidable for any radio protocol); blend toward ordinary BLE.
- **Reframe note (CTO decision 2026-06-28):** originator-anonymity is **not** a release blocker we must
  *engineer away* — it is a **bounded property we must honestly disclose.** B3 is cleared by truthful
  copy, not by achieving sender-unlinkability (which is impossible for a flood). The crypto research into
  re-randomization (PQ universal re-encryption) is **parked as decoupled general cryptography** — it
  cannot help our flood (Law 1) and is no longer on the polleneus track.
- **Clear when:** onboarding/marketing/docs carry this posture, reviewed against the B2 numbers; no
  surface implies sender-unlinkability or undetectability, and the persistent-author limit is stated plainly.

## B4 — v1 spend + key-evolution cost on low-end Android  ·  **OPEN**

Parent §P5 names this a release gate: benchmark the **v1 audited spend primitive (blind-RSA / BBS
show)** + time-ratcheted forward-secure key-evolution on low-end Android against BLE
MTU/fragmentation + battery. (The bespoke Fiat-Shamir ZK nullifier is correctly **deferred post-v1**
behind the §9.5 non-ZK fail-closed quota — not a v1 blocker.)

- **Clear when:** measured spend + key-evolution latency/battery on a low-end handset is within the
  budget that keeps the soup uniform and the UX usable.
- **Protocol defined (P5):** the on-device measurement plan is now written —
  [p5-key-management-spec.md §9](specs/2026-06-28-p5-key-management-spec.md) — naming exactly what to
  measure (spend, key-evolution + **FS-KEM puncture cost**, envelope under BLE MTU, trial-decrypt,
  sustained + **worst-case** load, SE/TEE write-endurance) on a named low-end Android. Thresholds are
  **TBD-pending the P0 field-airtime anchor (B2)** — a gate can't pass against a TBD. **Owed:** the run on
  real hardware (the simulator cannot measure handset crypto/battery).
- **FS construction DECIDED (target); v1 ships FS DEFERRED (ratified 2026-06-30, FS decision memo).** The
  forward-secrecy *primitive* is settled by the invariants: **CHK03-shape forward-secure PKE on the classical
  X25519 leg** of X-Wing (an **anonymous** HIBE — **BKP/SXDH**, superseding the earlier BBG pick; see
  [fs-kem-spec](specs/2026-06-30-fs-kem-spec.md)), **ML-KEM-768 static**, **1-hour epochs** (tree depth ℓ sized to
  the *address lifetime*, not the TTL), crypto-erase
  driven by the FJB monotonic boot-clock. **Guaranteed FS window ≥ TTL.** Honesty guard: classical FS and PQ
  confidentiality defend **disjoint** adversaries — never claim "post-quantum *and* forward-secret" against a
  quantum-capable seizing adversary in v1; **PQ-FS DEFERRED** (no standardized mobile PQ-FS-PKE exists). Per-message
  BFE/puncture **rejected** for v1 (MB–GB keys / O(n) decrypt). **Two real gates before FS-on ships:** (i) **this B4
  benchmark** — per-blob *pairing decrypt* in the trial-decrypt hot path on a named low-end phone (the dominant open
  cost; 2014-SoC proxies are not authoritative), plus StrongBox erase/endurance + 1.8 KB byte-uniform fit at ℓ=8;
  and (ii) a **B1 audit of the research-grade pairing dependency** (`libforwardsec`/RELIC-class, ~unmaintained — the
  practical blocker, more than the crypto math). **Honest interim (now):** ship **static recipient key + FS DEFERRED,
  disclosed in-app**; **no FS theatre** (a retained static decap key with a side-derived `k_e` gives *zero* FS). The
  current spike crypto is verified clean of FS theatre (static-key X-Wing seal, no epoch key-derivation). Design doc
  reconciled v0.7 (§4/§5.2/threat-table); the prior "FS by default" headline was an overclaim and is retracted.
- **FS COMPUTE sub-result — MEASURED on low-end hardware (2026-06-30). De-risks the compute concern; does NOT
  clear B4.** The doubt that drove the deferral was the per-blob **pairing-decrypt** cost (all prior numbers were a
  2014-Snapdragon-801 *proxy*: ~55 ms). Measured directly on a **SD-695-class low-end Android** (Cortex-A78 prime +
  A55 littles), using **mcl** BLS12-381 on the **generic-C path (no arm64 assembly → conservative)**, a faithful
  BBG-HIBE decrypt proxy (BBG decrypt = **2 Miller loops + 1 *shared* final-exponentiation** — a product-of-pairings,
  hence *cheaper* than 2 standalone pairings; depth-independent, BBG's headline property):
  **big core ≈ 1.65 ms (p99 1.72), little core ≈ 9.2 ms (p99 12.9)** for the proxy; a standalone pairing ≈ 1.1 / 6.3 ms;
  G2 mul ≈ 0.23 / 1.25 ms (KeyUpdate is a handful of muls, once/hour → trivial). Full per-blob decrypt adds the
  X-Wing X25519 op + ML-KEM-768 decap + KDF/DEM + serialization on top of this dominant cost. **Even worst-case
  (slowest core, no asm) this is well inside any plausible interactive-latency target — the formal B4 threshold is
  still TBD-pending the B2 field-airtime anchor.** Sizes — **earlier BBG-based estimate, now KNOWN-STALE for BKP and
  to be RE-DERIVED** (fs-kem-spec §3/§8.3b/§10): BBG's constant 3-element ct (~150 B) was the basis, but **BKP ct is
  all-G1 and grows with depth ℓ**, and **byte-uniformity needs an ~2× Elligator-class encoding** (BLS12-381 G1 is
  not byte-uniform) — so the FS-leg ct is larger and the **~1.8 KB hybrid-envelope fit is no longer assured**
  (ML-KEM ct alone is 1088 B; classical-only PDU was ~1 KB; envelope = a pending decision). sk = O(ℓ) node keys at
  the *address-lifetime* ℓ (not ℓ=8) → KB-scale, expected to fit StrongBox. **All FS sizes are an M-FS1 measurement,
  not settled.**
  **Dependency posture improved:** the feared `libforwardsec` is dead (won't build on a 2026 toolchain), but **mcl**
  (BSD-3, actively maintained) and **jedi-pairing** (BSD-3, self-contained, hand-written AArch64 asm) are healthy
  foundations — a far smaller B1 surface than "research-grade unmaintained." Prior art (read 2026-06-30): **FoSAM**
  (arXiv 2603.12871, KIT) — forward-secret receiver-public-key-only *anonymous* ad-hoc messaging w/ an Android
  prototype — independently corroborates this approach (its Pixel-6 full-scheme decrypt of **6.70 ms** sits inside
  our measured bracket) and motivates an **anonymous/key-private HIBE** (sealed-sender needs ciphertext-key
  unlinkability — plain BBG is not anonymous; FoSAM uses Blazy-MDDH); polleneus's X-Wing adds the **PQ leg FoSAM lacks**.
  **STILL OPEN before B4 clears / FS-on ships:** (i) a **full anonymous-HIBE (BKP) + CHK time-tree** impl (the proxy measures the
  dominant cost, not the scheme), (ii) **StrongBox crypto-erase latency + flash endurance** for hourly key-erase —
  *the deletion mechanism FS actually rests on, still unmeasured*, (iii) the **boot-reset clock gap** (P5 §10.1,
  unsolved), (iv) the **B1 pairing-dependency audit**. **FS stays DEFERRED** until these clear; the static-key interim
  + in-app disclosure stands. (Bench: native arm64 binary via NDK r27d clang → `adb push` to `/data/local/tmp`;
  N=300/op, CLOCK_MONOTONIC; tool + raw logs local in `spike/`.)
- **FS construction now SPECCED (2026-06-30) — [fs-kem-spec.md](specs/2026-06-30-fs-kem-spec.md), DRAFT/UNAUDITED.**
  After a source-cited research stop, the anonymous-HIBE pick is **Blazy–Kiltz–Pan (BKP, SXDH) HIBE + CHK binary
  time-tree on mcl** — *not* BBG: sealed-sender trial-decrypt **requires key-privacy**, BKP ciphertexts are
  pseudorandom (PR-ID-CPA, anonymity proven under MDDH/SXDH) and BBG is not anonymous. Validated by **FoSAM** (the
  same construction, Android prototype). The spec carries the build plan (M-FS1…4) + the B1 list: replicate FoSAM's
  cross-instance key-privacy proof, **new BKP-on-mcl code is the top audit surface**, constant-time trial-decap +
  uniform all-G1 serialization, and **StrongBox crypto-erase latency/endurance (still UNMEASURED)**. FS-on gated on
  M-FS2…4 + the proof + B1; **stays DEFERRED**.
- **M-FS1 DONE (2026-07-01) — BKP HIBKEM built + KAT-correct + benchmarked on real low-end hardware.** Construction
  pinned by a derive+adversarially-verify workflow (4 derivations; 3 agree, verifiers confirm decap inverts).
  Implemented on mcl (Setup/KeyGen/Encap/Decap/Delegate); **KATs ALL PASS** (round-trip depth 1/8/15, cross-id
  isolation, `millerLoopVec`==stepwise, 4-level delegation — round-trip = ground truth). Tab A9+ (SD-695, generic-C),
  big/little core: **Decap (trial-decrypt hot path) 2.16 / 12.2 ms** (the headline is constant-time-exact — no
  secret mul in the hot path), Encap 5.29 / 31.8, KeyGen 0.91 / 5.19, Delegate 8.29 / 47.7. **Ciphertext = 192 B
  (4 G1) CONSTANT** — *correcting the earlier "ct grows with depth"*: the identity aggregates into `Z_id` before
  encryption, so ℓ grows only the on-device key state, not the wire ct. **Size budget now FITS:** 192 B + ML-KEM
  1088 B ≈ 1.28 KB < 1.8 KB (≈1.47 KB with the ~2× byte-uniform encoding). **Anonymity finding (adversarial
  verification):** in our model `dk` is recipient-PRIVATE (only mpk/G1 public) → the HIBKEM linking test has no G2
  leg and every passive distinguisher collapses to DDH-in-G1 ⇒ **plausibly avoids the research-grade AHIBKEM**, but
  **DEFERRED-pending an SXDH key-privacy proof + a "only public G2 is P2" invariant**. 2 pre-audit bugs found+fixed
  (reject zero-id; Delegate `p<L` guard). STILL OPEN: M-FS2 (CHK tree + `mulCT` + byte-uniform encoding), M-FS3
  (StrongBox erase), the key-privacy proof, boot-reset gap, B1.
- **Anti-flood rate-limit EFFICACY residual (added 2026-06-29, AF-2 + AF-3 + AF-6) · MEASURED-IN-SIM —
  resolves the [p2-token-source-spec §4](specs/2026-06-27-p2-token-source-spec.md) "carried to
  release-blockers" forward-reference, which previously had no matching entry:**
  - **AF-2 — the "≈1 slot venue-wide" claim is conditional.** The parent §9.3 idealization ("one token =
    D slots" → "≈1 slot venue-wide, modulo gossip-propagation delay") holds **only when seen-`nf` gossip
    outpaces the holder's serialized spend rate**. For a **burst / co-present holder** the token-source sim
    measures **slots/token → D (≈11 = D in the committed sweep) = NO rate-limit**, bounded then **only by
    the §9.5 quota `Q`**. The honest headline is the **gossip-vs-spend race curve**, not a single number.
  - **AF-3 — `Q` is per-observed-session friction, not a per-device quota.** Commodity phones rotate their
    RPA (~15 min default) and an attacker can present fresh connections/RPAs per spend → a fresh `Q` each
    time; this residual folds into the already-disclosed funded-device-count bound (§9.6). (Enforceability
    is the B1 audit item above.)
  - **AF-6 (physicality) — the `token_spend_interval = 0` / D endpoint is the multi-radio O(K) regime;** a
    single radio is floored at `t_setup` (~hundreds of ms/spend) and reaches the no-rate-limit regime only
    via slow gossip (large diameter / sub-`d_c` fragmentation), not via bursting.
  - **Owed:** an **attacker-RPA/session-rotation harness arm** (does `Q` survive rotation?) and the **B1
    audit determination** above; the field number depends on real commodity-BLE RPA behaviour.

## B5 — Continuous-verification gates green  ·  **OPEN**

Parent §P6: multi-OS transport conformance harness; adversarial-eviction CI gate; **internet-disabled
CI** (an offline-first tool must build/test with no network); the simulator's percolation +
airtime + anonymity gates kept green as the model evolves.

- **Status (P6):** the simulator's **fast** gates (percolation oracle, airtime publish-gate, anonymity
  must-localize/exposure/defense/intersection gates) are green and run via `pytest` in-repo (242 passing).
  **Internet-disabled is ENFORCED as a runtime GUARD** for the simulator: an in-repo gate
  (`test_offline_first.py`) rebinds the socket connection entry points around a real run on **every `pytest`**
  — a regression guard over the common socket stack (in-process; not a supply-chain proof). The **GitHub
  Actions auto-run is now LIVE and green on `main`** (#29): the per-push `CI` workflow (`ci.yml` — `test` +
  `offline-first`) passes on the runner; `gates-nightly.yml` (heavy `-m slow` sweeps) is scheduled but its
  **CI timing is still UNVERIFIED** until the first nightly/dispatch run. The **client-side** transport
  conformance + adversarial-eviction + client
  internet-disabled CI remain **OPEN** (no client yet); the **USRP PHY** + **source-estimator** field audits
  remain **OWED** (hardware). Protocols for all of these are written in
  [p6-continuous-verification-spec.md §4](specs/2026-06-28-p6-continuous-verification-spec.md).

---

## Deferred (explicitly NOT v1 blockers)
- **Bespoke Fiat-Shamir ZK-spend nullifier** — deferred post-v1 (parent §12.7); v1 ships the audited
  blind-RSA/BBS spend, bounded by the §9.5 non-ZK fail-closed quota.
- **Insider / compromised-node adversary**, **defenses-vs-intersection (sim PR-4)**, **clustered
  mobility** — named follow-ups; tracked under B2's "owed" list, not v1 ship gates on their own.

## Change log
- 2026-06-26 — created; B2 populated from slice-3 PR-1/PR-2/PR-3 (PRs #7–#10).
- 2026-06-28 — **P0–P6 campaign ratified** ([campaign-p0-p6-closeout.md](campaign-p0-p6-closeout.md), PRs
  #13–#27). B1 audit target + open-questions defined (P5); B4 benchmark protocol defined (P5); B5 sim gates +
  offline guard enforced via `pytest` (P6). **Both human-action items now DONE:** the `polleneus-dev` token
  was granted `workflow` scope → **CI is LIVE and green on `main`** (#29), and the **repo default branch was
  fixed to `main`** (one residual: delete the orphaned `chore/ways-of-working` branch). No release blocker
  cleared — B1–B4 + client-side B5 remain OPEN/OWED pending audit, hardware, and a client.
- 2026-06-29 — **pre-B1 red-team AF-findings folded in:** added the **anti-flood rate-limit efficacy
  residual** (under B4, AF-2 + AF-3 + AF-6) — resolving the dangling `p2-token-source-spec` "carried to
  release-blockers" forward-reference — and a **B1 anti-flood transport audit item** on the §9.5 quota
  `Q` enforceability under commodity-BLE RPA rotation (AF-3). No release blocker cleared.
