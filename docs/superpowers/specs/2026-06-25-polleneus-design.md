# polleneus — Vision & Architecture Spec

**Status:** Living design document (vision / endgoal). We keep tinkering; red-team reviews feed back in.
**Version:** v0.4 — 2026-06-25
**Codename:** originally *meldingx* (Norwegian *melding* = "message").
**Authors:** the polleneus project, with design synthesis and three multi-agent adversarial red-team passes.

> **One-liner.** polleneus is an offline-first, anonymous, self-destructing **"message in a bottle."**
> You encrypt a short message to a friend's opaque ID. Your phone drops it into a *uniform soup* of
> fixed-size encrypted blobs that every nearby phone carries and re-shares blindly over Bluetooth. Only
> your friend can recognize and open it. Messages self-destruct on a timer. Internet is an optional,
> anonymized accelerator — never required.

> **The honest promise (say this in the app, not just the doc).**
> *"We hide **who threw the bottle** and **who it's for**. We can't stop the finder from keeping it."*
> Concretely: **an attacker cannot deny service to, or deanonymize, friend-to-friend traffic in a dense
> gathering without physically deploying O(crowd-size) radios and sensors.** Flooding is bounded to a
> **cost** — O(rented sequential cores + K physical radios) — **not made impossible.** That is the real,
> falsifiable guarantee. We do **not** claim "leaves no durable trace" — see §12.

> **Scope.** Works at the scale of a **dense gathering** (stadium / protest / campus / blacked-out
> neighborhood), not a metropolis. Undirected flooding *buys* the anonymity and *caps* the scale; we
> embrace that and engineer around the real wall (airtime, §11), not the imagined one (storage).

---

## 0. Changelog

- **v0.4 (this doc).** Third red-team: designed + selected the **link-local token source**, then attacked all
  four v0.3 primitives. Adopted the **"Reciprocity Hourglass"** token source (§9 — Witnessed-Relay-Reciprocity
  spine × hash-based sequential **PoSW** + zero-knowledge nullifier; *earn-by-relaying* or *sweat-mint*). Red-team
  fixes folded in: **token-anchored nullifier + gossiped seen-set** (rescues the relay-token rate-limit — the
  per-neighbor anchor had made one token worth ~D slots); **dropped the standalone class-group VDF** and unified
  mint-cost on hash-PoSW (the VDF "age-floor backstops immortality" claim was backwards — a floor can't expire
  anything); **token TTL + re-priced discount**; **time-ratcheted forward secrecy** (FS driven by the clock, not
  by reading — closes the seizure/message-suppression hole) with the crypto-shred guarantee **restated as
  probabilistic (≤ p)**; **probabilistic, time-bounded origination license + manufactured cover** (the hard gate
  self-deadlocked at the percolation cliff and its "send anyway" fallback was a tell); anonymity now reported as
  a **measured source-estimator probability**, not the cover-ratio K. Killed two overclaims ("never decryptable
  again"; "VDF age-floor backstops immortality").
- **v0.3.** Second red-team (9 experts). Reframed the scale wall storage → **airtime**; anonymity claim →
  **origination-event K-anonymity**; honest bottle promise. Added rateless reconciliation, link-local relay
  tokens, receive-before-originate gate + Poisson mixing + self-loops, hop-energy + gossip clock, sliding-window
  seen-record, ferrying + NAN/LoRa, truth-in-labeling UX, the 6-phase roadmap, the "opt-in accelerator" rule.
- **v0.2.** Pivoted spray-and-wait → pure flooding; recipient tombstone → sender-owned delete; three-knob
  lifetime; seen-record; panic/duress; scaling math; dense-gathering scope.
- **v0.1.** Initial brainstorm + 11-agent review (broke all five v0.1 guarantees; drove v0.2).

---

## 1. The Core Mental Model — the "uniform soup"

No routing. A soup of fixed-size encrypted blobs.

- Every phone **carries** a bounded set of blobs it cannot read and continuously **re-shares** them over BLE.
- Neighbors don't blindly re-dump everything — they **reconcile sets** (§8) and exchange only the difference.
- Every phone runs **cover traffic** so its output looks identical whether or not it's really sending (§10).
- On meeting a new blob a phone **trial-decrypts** once: success → "mine"; failure → carry, re-share, learn nothing.
- Blobs die on a **timer** (plus optional crypto-shred). Dropped/expired IDs are remembered briefly.

That's the system. Everything below is the careful version.

**Why no routing?** Routing is metadata. Pure flooding has no path, no destination, no wavefront-from-a-source to point back at you. The price is scale — paid in *airtime*, §11.

---

## 2. Goals, Non-Goals, and the Design Rule

### Goals (ranked)
1. **Works with no internet** — full function in a total blackout.
2. **Hide who talks to whom**, from everyone but the two ends — including *which blob is real*.
3. **Ephemeral** — self-destruct on an absolute timer; unreadable-after-read (probabilistically) by default.

### Non-goals (v1)
Group chat; media; multi-device sync; text > 255 chars; guaranteed/real-time delivery; metropolis-wide offline delivery; durable deletion against a hostile node that retains ciphertext; a true per-sender quota.

### The Design Rule (generalized from the §9 internet-bridge philosophy)
> **Every capability that bends an invariant must be an opt-in *accelerator* that the BLE-only / offline / uniform core never depends on.** This governs Wi-Fi Aware/LoRa (§14), the internet bridge (§15), and the optional global delete (§7). The core must always run, and pass tests, with all of them disabled.

### The seven invariants (what alternatives must preserve)
1. No internet required. 2. Pure flooding, no routing/targeting metadata on the wire. 3. Anonymity via uniformity (real ≈ cover ≈ relayed). 4. Sealed-sender, no identity on the wire. 5. Self-destruct (absolute signed TTL + optional shred). 6. No server/account; OOB identity only. 7. Dense-gathering scope.

---

## 3. Threat Model

| Actor | Capability | Posture |
|---|---|---|
| Curious relay | Carries opaque blobs | ✅ Learns nothing |
| One-time co-located sniffer | RF logging, short window | ✅ Learns only "runs the app & emits blobs" |
| **SDR / PHY-fingerprinting adversary** | CFO/IQ radiometrics → IDs a handset ~100% in <1 min, **survives MAC/payload rotation** | ⚠️ **Assume device-linkage ≈ 1.0.** Defense rests on *origination-event anonymity*, reported as a **measured source-estimator probability** (§10) — the only property that survives perfect device labeling |
| **Multi-sensor mesh** (dozen Pi+BLE sniffers) | Triangulate each ID's *first sighting* → first-emergence provenance | ⚠️ Countered by the probabilistic origination license + manufactured cover + Poisson mixing (§10); realized anonymity is measured, not assumed |
| Persistent wide-coverage adversary | Blanket sensors + long-term statistical disclosure | ❌ Not defeated, only made to cost O(crowd-size) hardware; K is per-session and decays across repeat attendance |
| Network/internet observer | Logs bridge traffic | ⚠️ Defended only via Tor/mixnet bridge (§15) |
| Resourced flooder (state, GPU/ASIC/botnet) | Mass-mint, mains power | ⚠️ Bounded by **sequential-PoSW mint-cost** + **token-anchored link-local relay tokens** (§9); not a quota — flooding costs **O(rented sequential cores + K physical radios)**, not impossible |
| Device-seizure / coercion | Seize/coerce a phone, extract keys | ⚠️ **Time-ratcheted forward secrecy** (FS by the clock) + crypto-shred + encrypt-at-rest + **SE/TEE-wrapped keys** + panic/duress + deniable authentication (§5) |

**Out of model:** global passive RF everywhere; persistent *targeted* surveillance of a *named* individual.

---

## 4. Identity & Keys

- **Identity = a keypair:** X25519 (encrypt) + Ed25519 (sign), shown as a fingerprint + QR.
- **Out-of-band exchange only**, via a **mutual-presence ceremony** (§13): hold phones together, mutual QR + a 3-emoji / 4-word **SAS** both humans confirm (far higher completion than digit comparison; the ~13–14% one-way-scan completion rate is a real risk).
- **Persistent local trust states:** `Verified-in-person` / `Unverified` / `Key-changed!`. A key mismatch **quarantines** messages behind a tap ("verify in person"), never silently drops — closing the supervised-MITM / silent-rotation gap (no key-transparency server exists, so detection must be local + loud).
- **Forward secrecy by default** via **time-ratcheted forward-secure decryption** (§5), not a serverless prekey batch (which exhausts) — removing both the prekey-exhaustion trap and the read-to-shred dependency.

---

## 5. The Envelope & Crypto

### 5.1 Header split
| Field | Mutable? | Bound by |
|---|---|---|
| `message-ID` (**256-bit**, `= H(domain‖secret‖ephemeral_pk‖creation_ts)`, non-truncatable) | No | proof + auth |
| `creation-ts`, `global-TTL` (≤ 7 d), `ephemeral_pk`, `version`, **sequential-PoSW proof** | No | proof + auth |
| `hop-energy` counter (born at B, **decrement-only**, floored at 0) | Yes | unauthenticated by design (can only *shorten* life — §6) |

### 5.2 Encryption (serverless, forward-secret, deniable)
- **Forward secrecy by default — time-ratcheted, not puncture-on-read.** Fine-grained time **sub-epochs** inside the ≤7 d TTL; decryption keys for elapsed sub-epochs are deleted on a schedule driven by the §6 **gossip-median mesh clock — whether or not the message was read.** So a seizer cannot freeze the clock to recover unread mail (the *message-suppression* hole the old read-triggered design had), and the pre-read seizure window is bounded. Per-message **disappear-after-read** is an *optional extra* puncture on top, not the FS mechanism.
- **Honest restatement (kills the v0.3 overclaim):** the guarantee is **probabilistic**, not absolute. The only buildable puncturable schemes (Bloom-Filter Encryption / SafetyPin-class) carry a false-positive *retention* probability and very large keys; time-ratcheting bounds key size to a small constant (sub-epochs remaining). State it as *"unreadable after read/expiry with probability ≥ 1 − p"* for a published p, and **surface p in the §13 UX.**
- **Hardware-honored shred.** Key state is wrapped under a key held in **SE/TEE (StrongBox)**-backed Keystore (auth-bound, `setUnlockedDeviceRequired`); ratchet/puncture rewrites only the encrypted blob, and "shred"/panic-wipe = destroy the wrapping key (crypto-erase immune to wear-leveled NAND remnants). Surface in-app where SE/TEE is unavailable.
- **Sealed-sender:** fresh ephemeral per message; sender identity + authenticator live **inside** the seal (anonymous to the world, authenticated to the friend).
- **Deniable authentication:** a **designated-verifier / MAC-from-the-shared-secret** authenticator — the recipient is convinced of authorship, but it is **not transferable proof** under coercion.
- **Key-committing AEAD** (not vanilla Poly1305) so trial-decrypt is unambiguous — important before the PQ hybrid, where ML-KEM non-binding could otherwise make "is this mine?" ambiguous.
- **Signed/authenticated transcript** binds `domain‖version‖sender‖recipient‖message-ID‖ephemeral_pk‖global-TTL‖creation_ts‖text` (defeats surreptitious forwarding / signature-lifting).
- **PQ migration:** **X-Wing (X25519+ML-KEM-768) hybrid**, both components always, version bound into the transcript; treat the classical↔hybrid envelope-size change as a **flag-day**, never a mixed population (a size difference is a fingerprint).

---

## 6. Lifetime & Retention

### Knob 1 — Global TTL (sender-owned, authoritative)
Signed, absolute, ≤ 7 d. After `creation-ts + TTL` every honest node deletes the blob. **No node may extend or reset it.** (Reset-on-hop = immortal-message bug — forbidden.)

> **No proof can expire a message — only the signed TTL can.** The sequential-PoSW iteration count (§9) is a **minimum-age floor** (an anti-spam cost + clock-skew sanity check); it proves work happened *before* verification, never that a blob is *young enough to keep*. Expiry is solely the signed TTL + per-session nullifier freshness. (This corrects the v0.3 "age-floor backstops immortality" overclaim.)

> **The clock-trust hole (and its fix).** "It's expired" = `local_clock ≥ creation-ts + TTL`, but a blackout has no NTP, RTCs drift, and `creation-ts` is sender-signed (forgeable). Two backstops:
> - **Hop-energy decrement (§5.1):** a blob born with budget B loses 1 per re-share, floored at 0; energy-0 ⇒ local drop **regardless of clock.** The *safe dual* of reset-on-hop — it can only ever *shorten* life, so it's safe to leave unauthenticated.
> - **Gossip-median mesh clock:** each phone passively estimates a trimmed-median "freshest creation-ts seen across many independent senders" from the trial-decrypt stream; if its RTC disagrees beyond a threshold it flags itself clock-untrusted and expires by hop-energy. This same clock drives the §5 time-ratchet.

### Knob 2 — Relay retention (you, carrying others' soup)
Size-cap primary ("≤ X GB, evict per policy"); time-cap as a labeled low-power mode. **Density-adaptive auto-knobs (§9)** make the globally-healthy behavior the locally-rational default, dissolving the tragedy-of-the-commons without identity.

### Knob 3 — Inbox policy (you, as recipient)
Disappear-after-read (an optional extra puncture, §5) + inbox size cap.

### Seen-record (anti-resurrection / anti-replay) — sliding-window, not monolithic
A **sliding-window aging filter** (cuckoo with fingerprint+timestamp, or two-generation A2): an ID can't be re-accepted within window W, and **W ≥ maxTTL + margin even under maximal flood** because aging is FIFO-by-time, not FP-by-saturation. The cuckoo variant supports **exact deletion** for panic-purge; per-ID retention keyed to that ID's own TTL. (Also hosts the gossiped seen-**nullifier** set, §9.)

### Token TTL
Relay tokens (§9) also carry a **signed TTL (≤ 7 d)** so a pre-mined war-chest can't be stockpiled and dumped in a blackout.

### Panic / duress
"Delete-all" → wipe soup + inbox, IDs into the seen-record; **encrypt-at-rest + SE/TEE-wrapped keys** (locked seized phone yields nothing); **duress variant** wipes + rotates identity.

---

## 7. Deletion Model

- **Default = time-ratcheted crypto-shred (§5).** A read can optionally puncture the per-message key; regardless, sub-epoch keys are deleted on the clock, so a copy becomes unreadable (probability ≥ 1 − p) *to the recipient and any future seizer* with **zero wire signal.** Every other copy dies at the global TTL.
- **Optional global early-delete = decoupled, gated token, sender-fired, OFF by default, labeled "emits a detectable signal."** `delete-token = H(domain_delete‖secret)` is **decoupled from `message-ID`** (purge without proving the blob was real; mint decoy deletes for cover). Red-team hardening: (1) emitting a delete **costs the same anti-abuse spend as any wire action** (a relay-token, per §9) to stop an unauthenticated flush-DoS firehose; (2) a held blob is purged **only on an exact full-length match** to a per-blob delete-tag committed **inside the sealed transcript** (no loose/prefix match → no eviction of blobs the attacker didn't author); (3) real + decoy deletes ride the §10 **Poisson outbound queue** to decorrelate emission from read events; (4) honestly disclaim that seizing the secret retroactively links `delete-token → message-ID`.
- **Honest framing:** "delete" means *unreadable (≤ p) + TTL death on honest nodes*, **not** durable erasure against a hostile relay that retains ciphertext.

---

## 8. Transport & Gossip — beating the airtime wall

**The real scale wall is airtime, not storage** (BLE has 3 advertising channels, no hopping; at ~200 co-located advertisers collision probability is high; a 1 KB blob is several chained PDUs). The buffer holding the soup does **not** mean the radio can stir it. So the gossip layer must move *minimal bytes*:

- **Rateless set reconciliation (Erlay-style IBLT / minisketch).** Two neighbors exchange a compact **sketch** of their 256-bit ID *sets* and transfer only the **symmetric difference** (cost ∝ difference, not set size). Rateless ⇒ a 2-second brush still makes progress; a long sit fully reconciles. **Fixes airtime, trial-decrypt cost, and battery at once, and gives anti-abuse a hook** (a neighbor who "wants everything" / whose sketch never decodes is fast-droppable *without identity*). The sketch's wire framing must be fixed-size / non-fingerprintable to keep invariant 4. The same channel carries the gossiped seen-**nullifier** set (§9).
- Fall back to Bloom have/want when the difference is huge; bound decode attempts per neighbor (poisoning).
- **Connectionless first:** exchange the sketch + a proof-prefix over advertising/scan-response; open a connection only for the tiny difference transfer.
- **Platform reality (must be specified, not assumed):** publish a **per-platform transport matrix**; **iOS background cannot emit a generic ID-free blob to Android** (overflow-bitmask advertising, throttled cadence) → iOS is foreground-favored and its emission gap is an explicit, surfaced limitation, not a silent invariant-3 violation.
- **"Good crypto is not enough":** outer-frame MAC keyed by the blob's proof, parser fuzzing, **no pre-encryption compression**, constant ID-free advertisements (cf. Bluetooth Mesh Private Beacons).

---

## 9. Anti-Abuse — bound rate without a quota

A true per-sender quota is **fundamentally incompatible** with invariants 3 & 4 (you can't meter an identity you refuse to carry). Build the **achievable shadow**: make sustained rate *physically expensive* and *locally bounded*. The honest result: flooding costs **O(rented sequential cores + K physical radios), not impossible** — a cost bound, labeled as such in-app, not a wall.

### 9.1 Mint-cost = hash-based sequential PoSW (not a VDF)
Token cost is **N sequential hash-steps** (Cohen-Pietrzak Simple Proofs of Sequential Work, Poseidon/BLAKE-friendly), verify sub-ms. Sequential ⇒ a **per-device cap** (more cores/money don't parallelize one chain). Chosen over a class-group VDF because phones have hash hardware, **no trusted setup, no group of unknown order** — and it is the *single* mint primitive (the v0.3 per-blob VDF is gone; the contradiction is removed). Honest limit: caps per-**device** rate, never device **count**.

### 9.2 The token source — "Reciprocity Hourglass"
Rate-limit **relaying**, not identity. A token is a self-issued PoSW tuple `(s, …, proof)`; it is spent as a Fiat-Shamir **zero-knowledge nullifier inside the BLE handshake — never in the blob** (so the soup stays uniform). **Two ways to earn one token format:**
- **Reciprocity path (cheap, prosocial):** earn credit by relaying *novel* blobs to *diverse* strangers (diversity-gated via the local distinct-PHY estimate; novelty-required so recycled-blob loops earn nothing). Credit buys a token at a **steeply reduced PoSW difficulty**. Price → 0 near the percolation cliff, so relaying is rewarded exactly when relays are scarce — directly attacking the relay tragedy-of-the-commons (invariant-aligned, best R7).
- **Sweat path (always available):** any phone self-mints by paying full sequential PoSW in the background (emits **nothing** on the wire — best acquisition anonymity). Keeps the system **live in sparse crowds** with no one to relay for (patches the gate/reciprocity liveness gap).
- **Safety rule:** every token, however earned, still costs sequential wall-clock — the reciprocity discount is **floored > 0** and kept **strictly below the token's re-priced slot value** (§9.4). This single rule cancels both the relay-rebate loophole and the free-clique-credit loophole.

### 9.3 Token-anchored nullifier + gossiped seen-set (the critical red-team fix)
The v0.3 spend nullifier was anchored *per-neighbor*, so one token yielded a fresh valid nullifier against **every** neighbor → one token bought ~D relay slots (D = distinct neighbors met = hundreds in a venue), gutting the rate-limit. Fix:
- Spend reveals **`nf = H("nf" ‖ s)` — one stable marker per token, lifetime-stable** — plus a *separate* session proof-tag that binds the transcript to this handshake (anti verbatim-replay only).
- **Epidemic-gossip the seen-`nf` set** in the same uniform fixed-length flood (opaque hashes, no routing metadata → inv 2/3 hold), hosted in the §6 sliding-window filter.
- Result: "one token = D slots" becomes **"≈ one slot venue-wide, modulo gossip-propagation delay"** (window = neighbors-reachable-in-one-gossip-epoch). **Without this fix, primitive A provides essentially no rate-limit.**

### 9.4 Token TTL + re-priced discount
Tokens carry a **signed TTL (≤ 7 d)** (§6) so stockpiles age out. The discount/price is computed against **expected reachable-neighbors-per-token** (the correct denominator — not one slot), clamped by the **local distinct-PHY estimate** with **no global oracle**. Specifying the exact discount curve is an active research item (§17).

### 9.5 Eviction, density knobs, and defense-in-depth
- **Eviction (attacker-uncorrelated, flood-aware):** never least-PoSW; retain by **real age** (youngest-by-actual-creation, *not* closest-to-TTL — else a TTL=7 d flooder wins), **randomized**, with a **per-neighbor buffer-share cap**.
- **Density-adaptive auto-knobs:** cover floor, relay floor, token price are pure functions of **locally-observed density** (distinct *peer radios*, buffer pressure): dense ⇒ throttle; near the cliff ⇒ be generous. Identical rule for all nodes ⇒ no per-device tell.
- **Non-ZK secondary quota (bounds a ZK bug):** cap relay slots granted to any single observed **PHY-radio-session** to a small constant **regardless of how many valid tokens it presents**, and **fail closed** to this quota if ZK-verify exceeds a latency budget. A soundness bug in the bespoke ZK-spend wrapper is then a *leaf-level* flood (uniformity tolerates it), not a venue-wide rate-limit collapse. Bind the Fiat-Shamir transcript over the **full** statement + domain separators with a negative-test (Frozen-Heart-class) vector suite.

### 9.6 Honest residual
The dominant unresolved threat is funded-adversary **device count**, structurally unfixable without bending an invariant: (1) **cloud/botnet sweat-minting** (sequentiality caps per-device, not core count; no global difficulty oracle to raise N adaptively); (2) **spread-out farm at crowd density** (K real radios serving real strangers legitimately clears the diversity gate — the honorable O(crowd) bound). The token-anchored nullifier is what keeps this a *dent*: it forces a farm to pay sequential wall-clock **per slot** and to genuinely improve the mesh to mint cheaply.

---

## 10. Anonymity Engineering — measured, not assumed

**Reframed claim.** Per-blob uniformity is true but doesn't deliver what users imagine, and **device-linkage ≈ 1.0** (PHY fingerprinting). Report a **measured source-estimator probability** — run an adversarial spread-tree estimator (rumor-centrality; Pinto–Thiran–Vetterli sparse-observer MLE) on simulated + field first-sighting graphs and surface *"at this density your origination is identifiable with probability p"* as the headline in-app number, **not** the flattering cover-ratio K. K is **per-session and decays** across repeated venue attendance (model the multi-session intersection adversary).

- **Probabilistic, time-bounded origination license (replaces the hard gate).** Origination probability rises with relayed/witnessed novelty but is **floored > 0 and ceiled at a max latency T** — it **never deadlocks.** (The v0.3 hard "relay ≥ k novel first" gate self-deadlocked exactly in the sparse/blackout venues invariant 1 promises — the percolation cliff biting the anonymity layer — and its "send anyway with a warning" fallback was itself a deanonymizing tell.)
- **In sparse mode, manufacture cover — don't "send anyway."** Emit your own self-loops/dummies to populate the local first-sighting background *before* releasing the real blob, so a real origination always appears against a non-empty root-set. (Bends inv 3 slightly in sparse mode: more self-originated roots than relays — but every root is byte-uniform and real-vs-dummy stays hidden.)
- **Credit origination eligibility from witnessed (trial-decrypted) novelty equally with relayed**, so token-throttled phones aren't starved of the ability to send.
- **Poisson outbound mixing at a fixed venue-wide rate.** One queue {relayed, dummies, self-loops, real, deletes} popped at exponential times; **fix the rate to a constant** (or ≤ 3 public tiers with hysteresis driven by slow battery/buffer state, **not** instantaneous neighbor count) to restore Loopix's identical-rate precondition and remove the per-device/location rate fingerprint. Keep density-adaptation on the §9 token-price/retention knobs only.
- **Self-loops** (sealed to your own key): cover + active-attack detection + a reachability sensor. A returning loop triggers the **identical** local state transitions as any real inbound, and a node **keeps emitting at the normal Poisson rate when isolated** (with deliberate UX lag/hysteresis) — so an attacker jamming a target can't read "I've isolated you" off any cadence change (closes the isolation oracle).
- **PHY caveat:** MAC/payload rotation defeat only cheap passive sniffers; assume a handset is uniquely labeled. **Publish the device-linkability number from a USRP self-audit** (§16-P6).

---

## 11. Scale — airtime budget beside the storage table

Storage (≈1 KB/blob): a 1–2 GB buffer holds 1–2M live blobs. **But the binding constraint is circulation, not capacity.** Ship an **airtime-budget table** beside the storage table: *live-blobs-that-can-circulate-per-minute* given 3 advertising channels, collision-vs-density, and chosen cadence — computed and field-measured. Rateless reconciliation (§8) is what makes achievable circulation track the buffer instead of collapsing below it.

**The core trade, unchanged:** undirected flooding buys anonymity and caps scale. Gathering-scale works; metropolis needs bridges. Shorter TTL + size caps + reconciliation stretch feasible density.

---

## 12. Honest Limitations

1. **Percolation cliff has no clean answer.** Goal #1 (blackout) and the flooding mechanism physically collide below a critical mean degree — and it bites the anonymity layer too (the origination license + manufactured cover keep it from deadlocking, but can't conjure a crowd). Ferrying + LoRa/NAN (§14) buy **probability, not a guarantee.** The single biggest unsolved thing.
2. **Persistent sensor-net + PHY fingerprinting is made expensive, not defeated.** Device-linkage ≈ 1.0; anonymity is reported as a **measured source-estimator probability** (§10), per-session and decaying.
3. **No true per-sender quota** (incompatible with inv 3/4). The achievable shadow (§9) bounds flooding to **O(rented sequential cores + K physical radios)**; the dominant residual is funded-adversary **device count** (cloud sweat-minting + spread farm). Labeled in-app as a cost bound, not a wall.
4. **Deletion is probabilistic, not durable.** Time-ratcheted crypto-shred makes a copy unreadable with probability ≥ 1 − p (published p) and protects against seizure on the *clock*, not on reading; it does **not** erase ciphertext on a hostile retainer. "Erase from the world now" is not claimed.
5. **iOS background** is foreground-favored; a real, surfaced limit on both reach and uniformity.
6. **Cold-start** is a go-to-market problem (planned gatherings, §16-P4), not solvable by physics.
7. **The ZK-spend wrapper is the largest software-correctness risk** (a soundness bug forges/re-spends tokens with no compute) — bounded, not eliminated, by the §9.5 non-ZK fail-closed quota.
8. **False-confidence harm** is the deadliest failure mode; the entire §13 UX layer exists to prevent it.

---

## 13. UX & Operational Security (truth-in-labeling)

Honesty in the *doc* is not honesty in the *running app* — the gap is where people get hurt. Cheap, high-impact, all-local:

- **First-run "what this protects / does NOT protect" cards**, default on. Lead with the honest bottle metaphor; drop "leave no durable trace."
- **Per-feature inline honesty** (TTL picker: *"the person you send to can keep it"*; shred: *"unreadable after read with ~p chance of lingering"*; origination: *"identifiable here with probability p"*).
- **Honest send states:** *"Released to the soup"* / *"No peers nearby — holding"* / *"Expired before any peer saw it"* — **never a false "delivered."** (Private delivery confirmation only via the recipient's optional sealed ack.)
- **Mutual-presence pairing** (§4) + persistent trust badges; reserve red strictly for `Key-changed!`.
- **In-app "red-team reality" mode** stating the §12 limitations and the live anonymity/shred probabilities.

---

## 14. Reach Beyond One Island (opportunistic, blind)

Per the Design Rule (§2) — accelerators the BLE-only core never depends on:

- **Blind mobility-aware ferrying.** A phone with no new blobs for T minutes (it has saturated its island) preserves its soup more aggressively to carry max payload to the next island — needs **no position, no destination**, just "am I in a stale pocket," plus a UX nudge.
- **Wi-Fi Aware (NAN)** runs the *identical* uniform soup at ~100 m (dodges the iOS-BLE throttle); **optional LoRa** for km-range rural blackout (low-rate, long-TTL bridging only). Both offline. NAN's richer discovery metadata must be hardened to §8 and threat-modeled. Must run BLE-only when unavailable.

---

## 15. Internet Bridge (opportunistic, anonymized-only)
Tor onion-rendezvous or Loopix/Nym mixnet **only**; refuse rather than downgrade; mixed/constant-rate egress; **tested with internet disabled** so the blackout path is never silently bridge-dependent.

---

## 16. Roadmap

- **P0 — Re-scope & measure.** Ship the **airtime-budget table** (§11); reframe the public claims (airtime wall, measured-anonymity-probability, honest bottle promise + the "cost not a wall" flooding bound). Analysis + copywriting.
- **P1 — Highest-ROI, zero-tradeoff wins.** Rateless set reconciliation (§8); mutual-presence pairing + truth-in-labeling UX + honest send/trust states (§13).
- **P2 — Anti-flood + anonymity primitives.** Token source (**Reciprocity Hourglass**: hash-PoSW + ZK nullifier, **token-anchored + gossiped seen-set**, two mint paths, token TTL, re-priced discount, non-ZK fail-closed quota); Poisson mixing + **probabilistic origination license** + manufactured cover + self-loops (§9/§10).
- **P3 — Lifetime/storage hardening.** Hop-energy + gossip-median clock (also drives the §5 time-ratchet); sliding-window seen-record + seen-nullifier set; youngest-by-real-age eviction; density-adaptive auto-knobs (§6/§9).
- **P4 — Percolation + cold-start.** Blind ferrying; opportunistic NAN/LoRa; organizer "gathering kits", pair-to-activate (N=2), standby at N=0 (§14).
- **P5 — Serverless key-management.** **Time-ratcheted forward-secure decryption** + SE/TEE-wrapped keys + gated/exact-match delete-token; X-Wing hybrid + key-committing AEAD; deniable authenticator (§5/§7). Deepest correctness lift — **benchmark ZK-spend verify + key-evolution cost on low-end Android as a release gate.**
- **P6 — Continuous verification.** Multi-OS transport conformance harness; adversarial-eviction CI gate; **USRP PHY self-audit** + **adversarial source-estimator audit** (publish the realized origination-identifiability probability); internet-disabled CI.

---

## 17. Research-Only / Open Questions (out of the shipping core)
1. **Exact discount curve** mapping diverse-novelty-served → reduced PoSW difficulty that keeps cost provably above *r × slot-value* across the density range **with no global oracle** (and is not locally manipulable).
2. **ZK-spend wrapper cost** on low-end Android (Poseidon vs Rescue vs sigma/Bulletproofs) against BLE MTU/fragmentation + battery — is it cheap enough to ship?
3. **N_sweat sizing** so cloud/botnet sweat-minting is uneconomic at 50k-phone scale **without** honest-user battery harm — the core unresolved R1/R7 tension.
4. **Byte-indistinguishability** of sweat-minted vs reciprocity-minted tokens at spend (the two mint paths must not be tellable apart).
5. Fountain/RaptorQ K-of-N shards (anti-suppression, but multiplies the airtime wall — small N, high-stakes only); RLN-on-the-social-graph (the only true quota; bends invariants); stigmergic soft-gradient delivery (would it leak interest?).

---

## 18. Prior Art
Briar/Bramble (audited analog), Bridgefy ("good crypto is not enough"), Signal sealed sender (receipts deanonymize → private ack only), FireChat (density requirement), SSB/Manyverse (bridge must be Tor-only), Berty/Wesh (anti-directory rendezvous), GNUnet Messenger (fixed-size padding + anonymous ego), Bluetooth Mesh Private Beacons, Erlay/minisketch (rateless reconciliation), Loopix (Poisson mixing + loops), Waku RLN (why a true quota needs forbidden infra), **Cohen–Pietrzak Simple PoSW** (the mint primitive), **Privacy Pass** (anonymous tokens — the issuer problem this avoids), **Coconut / KVAC** (threshold & keyed-verification anonymous credentials), **Bloom-Filter Encryption / SafetyPin** (puncturable-FS cost reality), **rumor-centrality / Pinto–Thiran–Vetterli** (source estimation → the measured anonymity number), X-Wing (hybrid KEM).

---

## 19. The Soul-Check (from the third red-team)
The seven invariants are all the right calls, and the recommended fixes preserve every one — the token-anchored nullifier + gossiped set carry opaque hashes only (inv 2/3), token TTL reuses inv 5, time-ratcheted FS + SE-wrapped keys preserve inv 1/5/6, and manufactured-cover origination only bends inv 3 in sparse mode where every root stays byte-uniform. The **token source is dented, not broken**: the architecture is right, but it survives only *with* the four §9 fixes (chiefly the token-anchored nullifier) — without them the relay-token primitive provides almost no rate-limit. **The design's defining honesty is still its best feature**, but v0.4 had to apply that honesty to two overclaims the app would otherwise have lied about: *"never decryptable again"* → probabilistic (≤ p) + clock-driven ratchet; *"VDF age-floor backstops immortality"* → deleted (a floor can't expire anything; only the TTL does). The two truths to keep facing got **sharper**, not softer: the percolation cliff now visibly bites the anonymity layer (the gate's sparse-venue behavior), and device-linkage ≈ 1.0 means realized anonymity must be a **measured** source-estimator probability, not a flattering ratio. State all of it in the app, and the soul stays intact.

---

*Living document. Next: pressure-test §17 (discount curve, ZK-spend cost on low-end Android, N_sweat sizing), or `/superpowers:writing-plans` to turn the §16 P0–P2 wins into an implementation plan. We are deliberately not building yet.*
