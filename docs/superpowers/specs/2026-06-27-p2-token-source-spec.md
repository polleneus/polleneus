# polleneus — P2: Anti-flood token source (Reciprocity Hourglass) + sim rate-limit model

**Version:** v0.2 — 2026-06-27 (design-review round 1 folded in) · **Roadmap:** P2 — PR-1 of 3
**Parent design:** [polleneus v0.5 §9](2026-06-25-polleneus-design.md#9-anti-abuse--bound-rate-without-a-quota)
· **Sibling PRs:** P2 PR-2 (effective origination defenses), P2 PR-3 (intersection defenses).

> **Scope of THIS PR.** The token-source *mechanism* (parent §9, sharpened) **and** the one falsifiable
> sim claim: **the token-anchored nullifier + epidemically-gossiped seen-set is what makes the relay
> rate-limit exist** — a per-neighbor nullifier buys ~D relay slots/token (D = distinct neighbors
> *relayed-to*, hundreds in a venue), and **the GOSSIP (not the anchoring alone)** is what collapses that
> toward ≈ 1 venue-wide, *modulo a measured epidemic-propagation residual* (§9.3: "Without this fix,
> primitive A provides essentially no rate-limit"). Discount curve (§9.4) and ZK-spend (§12.7) are
> research / post-v1 and NOT modeled here.

## 1. Problem & why this is P2

A true per-sender quota is incompatible with invariants 3 & 4. The achievable shadow (§9): a self-minted
**PoSW token** spent as a **nullifier in the BLE handshake** (never the blob → soup stays uniform). The
crux red-team finding: a **per-neighbor** nullifier lets one token re-spend against every neighbor →
~D slots/token → **no rate-limit**. The fix is a **token-anchored** nullifier `nf = H("nf"‖s)` (one
stable marker per token) **plus epidemic gossip of the seen-`nf` set** — and §9.3 is explicit that the
*gossip* is the load-bearing part. **The simulator has never modeled tokens/crypto**; P2 PR-1 adds the
minimal model needed to *measure that this fix works and to quantify its residuals honestly.*

## 2. The mechanism (parent §9, made concrete)

- **Mint = sequential hash-PoSW** (Cohen–Pietrzak Simple PoSW); per-**chain** friction, **not** a
  per-device quota — one device runs many chains, faster HW lowers each chain's wall-clock (§9.1).
- **Spend = a nullifier in the handshake**, not the blob. **v1 spend = audited blind-RSA / BBS show**;
  the bespoke ZK nullifier is **post-v1** (§12.7) — not modeled here.
- **Token-anchored nullifier:** spend reveals `nf = H("nf"‖s)` — **one stable marker per token,
  lifetime-stable** — plus a session proof-tag binding the transcript (anti verbatim-replay only). The
  **seen-`nf` set is epidemic-gossiped** in the same uniform fixed-length flood (opaque hashes, no
  routing metadata), in the §6 sliding-window filter (retention horizon **W ≥ maxTTL + margin**, §6, so
  an `nf` is remembered at least as long as a token can live).
- **Non-ZK secondary quota:** cap relay slots granted to any single observed **PHY-radio-session** to a
  small constant `Q` **regardless of how many valid tokens it presents**, fail-closed (§9.5).
- **Two earn paths** (reciprocity / sweat); **discount curve = research (§17), NOT modeled here.**

## 3. The sim model (the measurable deliverable)

A new, **default-inert** rate-limit harness over the existing contact engine. A token is an integer id
`s`; `nf = hash(s)` is an int (no crypto computed). The model meters **how many useful relay slots one
minted token buys**, where **a slot = the token accepted by a *distinct acceptor* for a distinct novel
forward** (*acceptors relayed-to, not merely met*; a peer that already has everything, or a contact too
short to transfer, grants no slot). **This requires NEW per-(token, acceptor) accounting** — the engine's
existing `relayed` field tracks distinct foreign *blob ids*, **not** distinct acceptors, so it cannot
supply this quantity and is not reused for it. Three regimes:

- **BROKEN (per-neighbor nullifier):** a token is accepted once per **(token, acceptor)** pair →
  slots/token = distinct acceptors relayed-to = **~D**.
- **ANCHORED, no gossip (acceptor-local seen-set):** each acceptor remembers `nf` locally, but with no
  gossip a fresh acceptor has never seen it. So for a **static/dense** holder, slots/token ≈ **D** too
  (it spends the same token once against each of its D distinct acceptors); it drops below D **only** when
  the holder physically moves to fresh neighborhoods it has not yet hit. **This regime ≈ BROKEN for a
  static holder by design** — confirming §9.3 that the anchoring *alone* buys little; the win is the
  gossip.
- **ANCHORED + GOSSIP (the fix):** the seen-`nf` set **propagates epidemically on the engine's own
  contact/diffusion dynamics** (the same interval-reachability flood that carries blobs — §9.3 "same
  uniform flood") — **NOT** a fixed scalar delay. An acceptor rejects `nf` once the gossip front carrying
  it has reached that acceptor. So slots/token → **≈ 1 + a measured residual** = the slots spendable in
  the window **between an `nf`'s first spend and its epidemic arrival at each prospective acceptor.** A
  per-hop latency knob `gossip_delay` may be layered on top, but the dominant term is the **measured
  diffusion time on the contact graph**, which **grows with venue diameter, falls with density, and can
  exceed the token TTL / seen-window W** — and in a **sparse/fragmented venue (below the measured
  percolation threshold d_c ≈ 4.5) an `nf` may NEVER reach a disconnected pocket**, so the residual there
  is **unbounded by gossip and bounded only by the per-PHY quota Q.** **Worst case = a MOBILE holder that
  outruns the gossip front:** by moving to fresh neighborhoods faster than `nf` propagates, it leaks more
  slots than a static holder — so the measurement **must include a mobile adversary**, not only a static
  one (a static-seed measurement under-states the worst-case leak).
- **Per-PHY-session quota `Q`** (orthogonal, all regimes): even presenting **many** tokens, slots granted
  to one PHY-radio-session ≤ `Q` — the §9.5 fail-closed backstop. The harness must exercise the
  many-tokens case so Q's bound (and the residual it leaves) is exposed, not assumed.

**Metered outputs (residuals reported in the SAME units as the headline):** mean & p95 **slots/token**
per regime; the **epidemic-propagation residual** (slots leaked before `nf` arrives) **vs density AND
venue size/diameter**, including the fragmented-venue → unbounded case; **max slots/PHY-session** vs `Q`.
Deterministic by `master_seed`; default-inert (no metering / no new RNG unless the harness is enabled →
every existing slice bit-identical).

## 4. What we measure

- **Headline (parent §9.3):** slots/token ≈ **D (BROKEN ≈ ANCHORED-no-gossip)** → **≈ 1 + residual
  (ANCHORED+GOSSIP)**. Reported as the amplification `slots/token(BROKEN) ÷ slots/token(ANCHORED+GOSSIP)`
  with **both terms' definitions pinned** (slots = distinct novel forwards to distinct acceptors; the
  denominator is *not* hard-clamped to 1 — it is whatever the gossip leaves). The credited win is shown
  to come from the **GOSSIP** step (BROKEN ≈ ANCHORED-no-gossip ≫ ANCHORED+GOSSIP).
- **The honest residual = a number, not a hand-wave:** the epidemic-propagation residual vs density and
  venue diameter, with the sparse/fragmented case (`nf` never propagates → residual bounded only by `Q`)
  explicitly surfaced. This is the operational meaning of §9.3's "modulo gossip-propagation delay."
- **Quota backstop:** max slots/PHY-session ≤ `Q` in **every** regime even under many tokens.
- **Must-demonstrate-attack gate (pre-registered, density-honest):** BROKEN must yield slots/token
  **≥ a pre-registered fraction of the realized distinct-acceptor count at the tested density** (not a
  bare "> 1", which is trivial) — else the "fix helps" claim is vacuous (mirrors the anonymity slices'
  must-localize discipline).

## 5. Invariant & honesty check

- **Blob-soup invariants hold (inv 2/3/4 at the blob layer):** the token is spent in the **handshake,
  never the blob**, so the blob soup stays byte-uniform; `nf` + the gossiped seen-set are opaque,
  fixed-length, no routing metadata.
- **BUT the stable `nf` is a per-token PSEUDONYM (residual, not "cleanly held"):** because `nf` is
  lifetime-stable and **gossiped venue-wide, ANY passive listener** (not only a handshake counterparty)
  learns it, and can **link one token's spends — including their WHERE and WHEN — into a per-token
  spend-location/time trail** across neighborhoods. This is a **deliberate rate-limit ↔ linkability
  tradeoff** (the
  stability is *exactly* what stops one-token-D-slots): it links **one token's spends**, is **per-token
  not per-device**, and reaches **identity only when combined with the already-assumed PHY-fingerprinting
  worst case** (parent §10, device-linkage ≈ 1.0). The blob soup is unaffected. *(Parent §9.3 says "inv
  2/3 hold" — true for the soup; this handshake-layer per-token linkability should be stated there too;
  flagged for a parent-spec note.)*
- **Honest residuals carried as numbers, never hidden:** (1) **per-chain, not per-device** — meters
  slots/token, NOT device count; **cloud/botnet sweat-minting + a K-radio spread farm remain the dominant
  UNFIXABLE residual** (§9.6), structurally unmodeled here; (2) the epidemic-propagation residual is
  measured + reported (incl. the unbounded fragmented case); (3) gossip-of-seen-`nf` **airtime** is, in
  this PR, modeled as out-of-band of the §11 airtime budget — an **optimistic** simplification flagged in
  the fidelity row (the seen-`nf` flood does compete for airtime; folding it into §11 is a follow-up);
  (4) discount curve + ZK are research. **Every number is an UPPER BOUND on the rate-limit's quality**
  (equivalently a lower bound on slots an adversary leaks).
- **No "quota" claim:** the deliverable is "the anchored nullifier + gossip turns ~D into ≈ 1 + residual
  slots/token," **never** "per-device rate is capped" (impossible, §9.1/§9.6).

## 6. Out of scope / deferred (this PR)

- Reciprocity-vs-sweat **discount curve** (§9.4/§17); **real PoSW / blind-RSA-BBS / ZK** crypto.
- Folding the **seen-`nf` gossip airtime** into the §11 budget (named optimistic gap this PR).
- **Effective origination defenses** (P2 PR-2); **intersection defenses** (P2 PR-3).
- Density-adaptive discount/price knobs (§9.5) beyond the per-PHY quota.

## 7. Plan sketch (for writing-plans)

1. Config: token-harness fields (default-inert; `token_rate_limit_mode` off/broken/anchored/gossip,
   `phy_session_quota`, optional `gossip_delay` per-hop knob), validation, zero-RNG when off.
2. Overlay: per-relay token-spend metering with **new per-(token, acceptor) accounting** (NOT the
   `relayed` blob-id field); `nf` epidemic propagation seeded at its **mid-run first-spend time** — this
   must use the engine's **acquisition-time causality path**, NOT `percolation.temporal_reachable` (whose
   docstring warns it ignores `created_at` and is wrong for a blob/marker born mid-run). Acceptor-local
   seen-sets; the 3 regimes; a **mobile** adversary holder (worst case) alongside static; the per-PHY `Q`
   cap (under many tokens). Slot = token accepted by a distinct acceptor. Default-inert (bit-identical
   when off).
3. Scenario: token rate-limit sweep over density **and venue size/diameter** → slots/token per regime,
   amplification, the **measured** epidemic residual (incl. fragmented→unbounded), max-slots/PHY vs `Q`;
   pre-registered must-demonstrate gate.
4. Tests: bit-identity off; BROKEN ≈ ANCHORED-no-gossip ≈ D (static dense holder); ANCHORED+GOSSIP ≪ that;
   residual grows with diameter / →unbounded below percolation; Q bounds slots/PHY under many tokens;
   determinism.
5. Bounded measure (low reps, capped density+size); document; fidelity row "tokens: §9 rate-limit modeled
   (anchored-nf + epidemic gossip); device-count residual + seen-nf gossip airtime NOT modeled →
   optimistic; nf is a per-token pseudonym (handshake-layer linkability)."
6. Fan-out code+security review; PR; merge.
