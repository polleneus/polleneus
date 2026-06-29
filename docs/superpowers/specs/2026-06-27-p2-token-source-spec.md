# polleneus — P2: Anti-flood token source (Reciprocity Hourglass) + sim rate-limit model

**Version:** v0.3 — 2026-06-29 (pre-B1 red-team AF-2/AF-3/AF-4/AF-6 closed) · **Roadmap:** P2 — PR-1 of 3
**Parent design:** [polleneus v0.5 §9](2026-06-25-polleneus-design.md#9-anti-abuse--bound-rate-without-a-quota)
· **Sibling PRs:** P2 PR-2 (effective origination defenses), P2 PR-3 (intersection defenses).

> **Changelog v0.3 (pre-B1 red-team, 2026-06-29).** **AF-4** — pinned the v1 spend to **blind-RSA**
> (not "blind-RSA / BBS show" interchangeably) and specified the nullifier derivation; BBS-show
> **DEFERRED**. **AF-2** — restated the headline as the conditional it is (≈1 slot/token only when gossip
> outpaces serialized spends; → D for a burst holder, bounded only by `Q`) and repointed the "carried to
> release-blockers" reference to the now-created [release-blockers](../release-blockers.md) entry. **AF-3**
> — conceded commodity RPA/connection rotation, defined the commodity-defender session key, reframed `Q`
> as **per-observed-session friction** (not a per-device quota), and added an attacker-rotation harness
> arm + B1 audit item. **AF-6** — floored the single-radio spend interval at `t_setup` and labelled the
> `token_spend_interval = 0` endpoint as the **multi-radio O(K)** regime.

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
- **Spend = a nullifier in the handshake**, not the blob. **v1 spend = audited blind-RSA (RSA-BSSA)** —
  **pinned** (AF-4), no longer "blind-RSA / BBS show" as interchangeable alternatives. **Rationale:** a
  blind-RSA token **unblinds to a deterministic signature `σ`**, so a **stable, linkable nullifier exists
  naturally** for the §9.3 gossiped double-spend detection. A **BBS "show" is a fresh ZK proof on each
  spend → it yields NO stable, linkable nullifier** without an added double-spend / scope-pseudonym
  extension (k-times-anonymous-authentication style); **BBS-show is therefore DEFERRED** (it would need
  that extension before it could carry the §9.3 mechanism at all). The bespoke Fiat-Shamir ZK nullifier
  is likewise **post-v1** (§12.7) — not modeled here.
- **Token-anchored nullifier:** spend reveals **`nf = H("nf" ‖ σ)`** — the hash of the **deterministic
  unblinded blind-RSA signature `σ`** (the token) — giving **one stable marker per token,
  lifetime-stable** — plus a session proof-tag binding the transcript (anti verbatim-replay only). *(In
  the §3 sim the token is an integer `s` and `nf = hash(s)` stands in for `H("nf" ‖ σ)`; no crypto is
  computed.)* **Unforgeability + nullifier-binding** — that a relay can verify `nf` is backed by a valid
  blind-RSA token at spend time **without re-linking**, and that one token cannot yield two distinct
  accepted `nf` — is the load-bearing crypto property the whole rate-limit rests on. It is the **B1 audit
  item at P5 §10 item 6** (spend-primitive unforgeability + nullifier binding under the parent §9.3
  token-anchored gossiped seen-set — *the integration, not the textbook primitive*). The
  **seen-`nf` set is epidemic-gossiped** in the same uniform fixed-length flood (opaque hashes, no
  routing metadata), in the §6 sliding-window filter (retention horizon **W ≥ maxTTL + margin**, §6, so
  an `nf` is remembered at least as long as a token can live).
- **Non-ZK secondary quota:** cap relay slots granted to any single observed **PHY-radio-session** to a
  small constant `Q` **regardless of how many valid tokens it presents**, fail-closed (§9.5).
  **Commodity-defender session key + honest scope (AF-3):** a commodity Android/iOS phone **cannot do
  USRP-class radiometrics** (parent design §3 reserves PHY fingerprinting that survives address rotation
  to a USRP/SDR *adversary*), so the only session key a commodity defender observes is the
  **per-connection / per-RPA handshake** — and commodity phones advertise with a **Resolvable Private
  Address that rotates (~15 min by default)**, while an attacker can present **fresh connections/RPAs at
  will**. So `Q` is **per-observed-session friction, NOT a hard per-device quota**: an attacker who
  rotates its RPA/connection per spend draws a **fresh `Q` allowance each time** (bounded only by
  serialized `t_setup` and K radios — i.e. this residual **folds into the already-disclosed
  funded-device-count residual** §9.6, not a new wall). **We do NOT claim `Q` bounds a device.**
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
- **ANCHORED + GOSSIP (the fix) — and the RACE that decides whether it works.** The seen-`nf` set
  **propagates epidemically on the engine's own contact dynamics** (the same flood that carries blobs,
  §9.3) — **NOT** a fixed scalar delay. An acceptor rejects `nf` once the gossip front has reached it.
  **But whether the front beats the holder is a RACE between two physical rates** (the central honest
  finding, design-review round 2): the holder relays via **serialized BLE handshakes** (one radio,
  shared channels, ~`t_setup` each → spends are spaced by a **`token_spend_interval`**, NOT
  instantaneous), and the seen-`nf` front propagates at its own per-hop gossip rate. So:
  - **slots/token → ≈ 1 ONLY when the gossip front outpaces the spend rate** (`gossip` propagation per
    acceptor ≪ `token_spend_interval`). The rate-limit is real **only in this regime.**
  - **slots/token → D (NO rate-limit) for a BURST holder** that spends to its co-present neighbors faster
    than `nf` can spread (`token_spend_interval → 0`, or any per-hop `gossip_delay` ≳ the interval).
    **Physicality of the burst endpoint (AF-6):** a **single radio cannot spend "near-simultaneously"** —
    serialized BLE handshakes floor `token_spend_interval` at **`t_setup`** (a real connect + GATT +
    spend-handshake is **hundreds of ms, never 0**). So the **`token_spend_interval = 0` / D endpoint is
    the multi-radio O(K) regime** (K physical radios spending in parallel) — the already-disclosed
    K-radio farm residual (§9.6) — **not a one-device defeat.** The **single-radio worst case is the
    rate-ratio evaluated at `token_spend_interval ≥ t_setup`**, and that is the number we report as the
    single-radio result. **Honest caveat (kept):** a single radio can *still* reach the no-rate-limit
    regime **without** bursting — via **slow gossip** (large venue diameter, or a fragmented venue below
    `d_c ≈ 4.5` where `nf` may never arrive, see below); that geometry path is the genuine single-radio
    residual and is bounded only by `Q`. §9.3's "D → 1" is an **instantaneous-gossip idealization**, not a
    physical guarantee.
  - **`gossip_delay = 0` is an UNPHYSICAL optimistic edge** (instantaneous front) and must **never** be
    the headline; the deliverable is **slots/token as a function of the gossip-rate ÷ spend-rate ratio**,
    spanning the win regime and the no-rate-limit regime. **The exclusion is applied honestly, not
    asymmetrically (AF-6):** `gossip_delay = 0` is unreachable by *anyone* (the front is bounded by
    handshake-time × diameter), so it is dropped; `token_spend_interval = 0` is reachable only by a
    *multi-radio* holder, so it is **kept but labelled as the O(K) regime**, never presented as a single
    device defeating the gossip.
  - The diffusion time also **grows with venue diameter** and in a **fragmented venue (below d_c ≈ 4.5)
    an `nf` may NEVER reach a disconnected pocket** (residual bounded only by the per-PHY quota Q). A
    **MOBILE** holder that moves to fresh neighborhoods faster than the front leaks more than a static
    one. The measurement must include both burst and serialized spending, and both static and mobile
    holders — the honest worst cases the headline must not hide are **(i) the multi-radio burst endpoint
    (O(K), AF-6)** and **(ii) the single-radio slow-gossip / fragmented-venue case** (bounded only by `Q`).
- **Per-PHY-session quota `Q`** (orthogonal, all regimes): even presenting **many** tokens, slots granted
  to one **observed** PHY-radio-session ≤ `Q` — the §9.5 fail-closed backstop. The harness must exercise
  the many-tokens case so Q's bound (and the residual it leaves) is exposed, not assumed.
  **Attacker-rotation arm (AF-3, added):** because the commodity-defender session key is the
  per-connection/RPA handshake (not a device-stable identity), the harness must **also** measure slots
  when the holder **rotates its session id / RPA per spend** — the only way `Q` is actually attacked.
  Against a session-rotating attacker `Q` does **not** bound total slots; it caps slots **per observed
  session** only, so total slots scale as ≈ `Q × window / t_setup` per radio (× K radios). The optimism
  of the "one-session-many-tokens" measurement is recorded in the §5 honesty rows and §7 fidelity row,
  not hidden.

**Metered outputs (residuals reported in the SAME units as the headline):** mean & p95 **slots/token**
per regime; the **epidemic-propagation residual** (slots leaked before `nf` arrives) **vs density AND
venue size/diameter**, including the fragmented-venue → unbounded case; **max slots/PHY-session** vs `Q`.
Deterministic by `master_seed`; default-inert (no metering / no new RNG unless the harness is enabled →
every existing slice bit-identical).

## 4. What we measure

- **Headline = the RACE curve, NOT a single number:** slots/token(ANCHORED+GOSSIP) **as a function of
  the gossip-rate ÷ spend-rate ratio** (`gossip_delay` / per-hop propagation vs `token_spend_interval`),
  spanning **both** regimes: ≈ **1** when gossip outpaces spends (the rate-limit works) and ≈ **D** when
  the holder bursts faster than gossip spreads (NO rate-limit). The amplification
  `slots(BROKEN) ÷ slots(ANCHORED+GOSSIP)` is reported **with `gossip_delay` AND `token_spend_interval`
  on every row** (it is meaningless without them), and **`gossip_delay = 0` is excluded from the headline
  as an unphysical optimistic edge.** The credited win (when it exists) comes from the GOSSIP step
  (BROKEN ≈ ANCHORED-no-gossip), but the honest message is that **the win is conditional on gossip beating
  the spend rate — which it does not for a static burst holder.**
- **The honest residual = a number, not a hand-wave:** the propagation residual vs the rate-ratio,
  density, and venue diameter, with (a) the **static-burst case where slots/token → D (gossip gives
  nothing)** and (b) the sparse/fragmented case (`nf` never propagates → residual bounded only by `Q`)
  both explicitly surfaced. This is the operational meaning of §9.3's "modulo gossip-propagation delay" —
  and the honest correction that §9.3's "D → 1" is an instantaneous-gossip idealization.
- **Quota backstop:** max slots **per observed PHY-session** ≤ `Q` in **every** regime even under many
  tokens — **but** the session key is the rotating per-connection/RPA handshake (AF-3), so this bounds
  **per session, not per device**; the **attacker-rotation arm** measures total slots when the holder
  rotates its RPA/connection per spend (where `Q` buys only per-session friction, residual folded into
  §9.6).
- **Must-demonstrate-attack gate (pre-registered, density-honest):** BROKEN must yield slots/token
  **≥ a pre-registered fraction of the realized distinct-acceptor count at the tested density** (not a
  bare "> 1", which is trivial) — else the "fix helps" claim is vacuous (mirrors the anonymity slices'
  must-localize discipline).

### Measured result (reproducible: committed `sweep_cfg` fixture, static holder, density 6, seed 7, reps 5)

BROKEN (no rate-limit) = **D = 11 slots/token** (n = 38). The gossip arm as a function of the
**rate-ratio = gossip_delay ÷ token_spend_interval** (`token_race_sweep`):

| rate-ratio (gossip per-hop ÷ spend spacing) | slots/token | regime |
|---|---|---|
| 0.12 – 0.25 (gossip outpaces spends) | **1.0** | rate-limit works (mint-only floor) |
| 0.5 – 1.0 | 1.4 | works |
| 2.0 | 2.6 | partial |
| 4.0 | 4.8 | partial |
| **burst** (`token_spend_interval = 0` → **multi-radio O(K) endpoint**, AF-6) | **11.0 = D** | **NO rate-limit** |

*(Reproduce: `token_race_sweep(sweep_cfg(), density=6.0, reps=5, race_points=[(0.5,4),(0.5,2),(1,2),(2,2),(2,1),(4,1),(1,0)], holder="static")`; exact arena in `sim/tests/test_token.py::sweep_cfg`. `gossip_delay=0` is excluded as an unphysical instantaneous front.)*

**The honest headline (corrects §9.3):** the token-anchored nullifier + gossip delivers the "≈ 1
slot/token" rate-limit **only when seen-`nf` gossip keeps pace with the holder's serialized spend rate
(rate-ratio ≲ 1)**; it degrades through a partial regime; and against a holder that spends to its
co-present neighbors faster than `nf` can spread, it provides **essentially no rate-limit
(slots/token → D)**, bounded then **only by the §9.5 per-PHY quota `Q`** (itself per-observed-session
friction — AF-3). §9.3's unconditional "D → 1 venue-wide" is an **instantaneous-gossip idealization**;
the physical guarantee is **conditional on the gossip-vs-spend race**, and that case is the worst case the
headline must not hide. **Single- vs multi-radio (AF-6):** the `token_spend_interval = 0` burst endpoint
requires **multiple parallel radios** (it is the §9.6 K-radio farm residual); a **single radio is floored
at `token_spend_interval ≥ t_setup` (~hundreds of ms per BLE connect+GATT+spend)** and reaches the
no-rate-limit regime only through **slow gossip** (large diameter / sub-`d_c` fragmentation), not through
bursting. So the single-radio headline number is the rate-ratio evaluated at that floor, and the D
endpoint is reported as the multi-radio O(K) regime — keeping the worst case honest **and physical**.

**Mobility (two distinct worst-case axes):** a **mobile** holder leaks a much larger **absolute**
residual (it meets far more acceptors, D ≈ 75–149 vs 8–14). Its residual **fraction** depends on the
rate-ratio: when gossip is **fast** relative to spends (rate-ratio ≲ 1) the static holder leaks a larger
*fraction* (its few co-present acceptors are spent before the front catches them); when gossip is **slow**
(rate-ratio ≳ 2) the **mobile holder evades more** even as a fraction (it reaches fresh pockets ahead of
the front). So "mobile always evades more" is false — it is true only in the slow-gossip regime, and
mobile is unconditionally worse for *total* leak. *(All spend times are capped at the acceptor's contact
`exit_` — a serialized spend can never occur after the holder is out of range; this corrects a round-2
bug where unphysically-late spends gave the gossip front extra time, understating the mobile leak ~3×.)*
This **qualifies the §9.3 public anti-flood claim** and is tracked as the **anti-flood rate-limit
efficacy residual** in [release-blockers.md](../release-blockers.md) (under B4, added 2026-06-29 for
AF-2/AF-3/AF-6) — the entry that **resolves this forward-reference**, which previously pointed at a
close-out section carrying no matching item (AF-2).

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
  (4) discount curve + ZK are research; (5) **`Q`-per-PHY-session assumes session-pinnability the
  commodity defender lacks → optimistic (AF-3):** the "one session, many tokens" measurement holds the
  session id fixed, but a commodity phone keys a session only by the rotating per-connection/RPA handshake
  and an attacker can rotate it per spend; the **attacker-rotation arm** measures this, and the residual
  folds into the §9.6 funded-device-count bound. **Every number is an UPPER BOUND on the rate-limit's
  quality** (equivalently a lower bound on slots an adversary leaks).
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
   cap (under many tokens) **plus a session-rotating attacker arm (rotates its RPA/connection per spend,
   so `Q` is attacked not assumed — AF-3)**. Slot = token accepted by a distinct acceptor. Default-inert
   (bit-identical when off).
3. Scenario: token rate-limit sweep over density **and venue size/diameter** → slots/token per regime,
   amplification, the **measured** epidemic residual (incl. fragmented→unbounded), max-slots/PHY vs `Q`;
   pre-registered must-demonstrate gate.
4. Tests: bit-identity off; BROKEN ≈ ANCHORED-no-gossip ≈ D (static dense holder); ANCHORED+GOSSIP ≪ that;
   residual grows with diameter / →unbounded below percolation; Q bounds slots/PHY under many tokens;
   determinism.
5. Bounded measure (low reps, capped density+size); document; fidelity row "tokens: §9 rate-limit modeled
   (anchored-nf + epidemic gossip); device-count residual + seen-nf gossip airtime NOT modeled →
   optimistic; **`Q`-per-PHY-session assumes session-pinnability a commodity phone lacks (RPA rotation) →
   optimistic unless the rotation arm is run (AF-3)**; nf is a per-token pseudonym (handshake-layer
   linkability)." **B1 audit item (AF-3):** is `Q` a real backstop on real commodity BLE, or does it
   collapse to per-connection friction under RPA rotation? — tracked in
   [release-blockers.md](../release-blockers.md) (B1 + B4).
6. Fan-out code+security review; PR; merge.
