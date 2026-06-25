# meldingx — Vision & Architecture Spec

**Status:** Living design document (vision / endgoal). We keep tinkering; red-team reviews feed back in.
**Version:** v0.3 — 2026-06-25
**Authors:** Robin (concept & direction), Claude (design synthesis), + two multi-agent adversarial red-team passes.

> **One-liner.** meldingx is an offline-first, anonymous, self-destructing **"message in a bottle."**
> You encrypt a short message to a friend's opaque ID. Your phone drops it into a *uniform soup* of
> fixed-size encrypted blobs that every nearby phone carries and re-shares blindly over Bluetooth. Only
> your friend can recognize and open it. Messages self-destruct on a timer. Internet is an optional,
> anonymized accelerator — never required.

> **The honest promise (say this in the app, not just the doc).**
> *"We hide **who threw the bottle** and **who it's for**. We can't stop the finder from keeping it."*
> Concretely: **an attacker cannot deny service to, or deanonymize, friend-to-friend traffic in a dense
> gathering without physically deploying O(crowd-size) radios and sensors.** That is the real,
> falsifiable guarantee. We do **not** claim "leaves no durable trace" — see §12.

> **Scope.** Works at the scale of a **dense gathering** (stadium / protest / campus / blacked-out
> neighborhood), not a metropolis. Undirected flooding *buys* the anonymity and *caps* the scale; we
> embrace that and engineer around the real wall (airtime, §11), not the imagined one (storage).

---

## 0. Changelog

- **v0.3 (this doc).** Folded in the second red-team (9 experts + synthesis). Reframed the scale wall from
  storage → **airtime**; reframed the anonymity claim from per-blob uniformity → **origination-event
  K-anonymity** (assume device-linkage ≈ 1.0); reframed the promise to the honest bottle metaphor. Adopted
  a composing stack of soul-preserving primitives: **rateless set reconciliation** (§8), **link-local relay
  tokens** (§9), **VDF mint-cost + age-floor** (§9), **receive-before-originate gate + Poisson mixing +
  self-loops** (§10), **puncturable-encryption crypto-shred-on-read + decoupled delete-token** (§5/§7),
  **blind ferrying + Wi-Fi Aware/LoRa** (§14), **hop-energy decrement + gossip-median clock** (§6),
  **sliding-window seen-record** (§6), **truth-in-labeling UX + mutual-QR/SAS pairing** (§13). Added the
  6-phase roadmap (§16) and the "opt-in accelerator" design rule (§2).
- **v0.2.** Pivoted spray-and-wait → pure flooding; recipient tombstone → sender-owned delete; three-knob
  lifetime; 30-day seen-record; panic/duress; scaling math; dense-gathering scope.
- **v0.1.** Initial brainstorm + 11-agent review (broke all five v0.1 guarantees; drove v0.2).

---

## 1. The Core Mental Model — the "uniform soup"

No routing. A soup of fixed-size encrypted blobs.

- Every phone **carries** a bounded set of blobs it cannot read and continuously **re-shares** them over BLE.
- Neighbors don't blindly re-dump everything — they **reconcile sets** (§8) and exchange only the difference.
- Every phone runs **cover traffic** so its output looks identical whether or not it's really sending (§10).
- On meeting a new blob a phone **trial-decrypts** once: success → "mine"; failure → carry, re-share, learn nothing.
- Blobs die on a **timer** (plus optional crypto-shred-on-read). Dropped/expired IDs are remembered briefly.

That's the system. Everything below is the careful version.

**Why no routing?** Routing is metadata. Pure flooding has no path, no destination, no wavefront-from-a-source to point back at you. The price is scale — paid in *airtime*, §11.

---

## 2. Goals, Non-Goals, and the Design Rule

### Goals (ranked)
1. **Works with no internet** — full function in a total blackout.
2. **Hide who talks to whom**, from everyone but the two ends — including *which blob is real*.
3. **Ephemeral** — self-destruct on an absolute timer; unreadable-on-read by default.

### Non-goals (v1)
Group chat; media; multi-device sync; text > 255 chars; guaranteed/real-time delivery; metropolis-wide offline delivery; durable deletion against a hostile node that retains ciphertext.

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
| **SDR / PHY-fingerprinting adversary** | CFO/IQ radiometrics → IDs a handset ~100% in <1 min, **survives MAC/payload rotation** | ⚠️ **Assume device-linkage ≈ 1.0.** Defense rests on *origination-event K-anonymity* (§10), the only property that survives perfect device labeling |
| **Multi-sensor mesh** (dozen Pi+BLE sniffers) | Triangulate each ID's *first sighting* → first-emergence provenance | ⚠️ Countered by the receive-before-originate gate + Poisson mixing (§10), bounded to a measured K |
| Persistent wide-coverage adversary | Blanket sensors + long-term statistical disclosure | ❌ Not defeated, only made to cost O(crowd-size) hardware |
| Network/internet observer | Logs bridge traffic | ⚠️ Defended only via Tor/mixnet bridge (§15) |
| Resourced flooder (state, GPU/ASIC/botnet) | Mass-mint, mains power | ⚠️ Bounded by **VDF** (sequential, no mains advantage) + **link-local relay tokens** (§9); not a true quota |
| Device-seizure / coercion | Seize/coerce a phone | ⚠️ Crypto-shred-on-read (FS default) + encrypt-at-rest + panic/duress + deniable authentication (§5) |

**Out of model:** global passive RF everywhere; persistent *targeted* surveillance of a *named* individual.

---

## 4. Identity & Keys

- **Identity = a keypair:** X25519 (encrypt) + Ed25519 (sign), shown as a fingerprint + QR.
- **Out-of-band exchange only**, via a **mutual-presence ceremony** (§13): hold phones together, mutual QR + a 3-emoji / 4-word **SAS** both humans confirm (far higher completion than digit comparison; the ~13–14% one-way-scan completion rate is a real risk).
- **Persistent local trust states:** `Verified-in-person` / `Unverified` / `Key-changed!`. A key mismatch **quarantines** messages behind a tap ("verify in person"), never silently drops — closing the supervised-MITM / silent-rotation gap (no key-transparency server exists, so detection must be local + loud).
- **Forward secrecy by default** via **puncturable encryption** (§5), removing the serverless prekey-exhaustion trap. Rotation = new keypair; self-signed revocation notes propagate as ordinary messages.

---

## 5. The Envelope & Crypto

### 5.1 Header split
| Field | Mutable? | Bound by |
|---|---|---|
| `message-ID` (**256-bit**, `= H(domain‖secret‖ephemeral_pk‖creation_ts)`, non-truncatable) | No | proof + auth |
| `creation-ts`, `global-TTL` (≤ 7 d), `ephemeral_pk`, `version`, **VDF proof** | No | proof + auth |
| `hop-energy` counter (born at B, **decrement-only**, floored at 0) | Yes | unauthenticated by design (can only *shorten* life — §6) |

### 5.2 Encryption (serverless, forward-secret, deniable)
- **Puncturable encryption (crypto-shred-on-read).** One long-lived public key per identity (great for QR). *Reading* a message **punctures** the key so that ciphertext can never be decrypted again → **FS is the default with no server, no prekey batch to exhaust, no reuse to detect.** "Disappear-after-read" becomes a **local key-puncture with zero wire signal.** Bucket punctures per epoch (≤ TTL) to bound key growth; benchmark on weak phones (open item).
- **Sealed-sender:** fresh ephemeral per message; sender identity + authenticator live **inside** the seal (anonymous to the world, authenticated to the friend).
- **Deniable authentication:** replace a third-party-verifiable signature with a **designated-verifier / MAC-from-the-shared-secret** authenticator — the recipient is convinced of authorship, but it is **not transferable proof** under coercion. (Preserves "authenticated to the friend" without "provable to a captor.")
- **Key-committing AEAD** (not vanilla Poly1305) so trial-decrypt is unambiguous and robust — important before the PQ hybrid, where ML-KEM non-binding could otherwise make "is this mine?" ambiguous.
- **Signed/authenticated transcript** binds `domain‖version‖sender‖recipient‖message-ID‖ephemeral_pk‖global-TTL‖creation_ts‖text` (defeats surreptitious forwarding / signature-lifting).
- **PQ migration:** **X-Wing (X25519+ML-KEM-768) hybrid**, both components always, version bound into the transcript; treat the classical↔hybrid envelope-size change as a **flag-day**, never a mixed population (a size difference is a fingerprint).

---

## 6. Lifetime & Retention

### Knob 1 — Global TTL (sender-owned, authoritative)
Signed, absolute, ≤ 7 d. After `creation-ts + TTL` every honest node deletes the blob. **No node may extend or reset it.** (Reset-on-hop = immortal-message bug — forbidden.)

> **The clock-trust hole (and its fix).** "It's expired" = `local_clock ≥ creation-ts + TTL`, but a blackout has no NTP, RTCs drift, and `creation-ts` is sender-signed (forgeable). Two backstops:
> - **Hop-energy decrement (§5.1):** a blob born with budget B loses 1 per re-share, floored at 0; energy-0 ⇒ local drop **regardless of clock.** This is the *safe dual* of reset-on-hop — it can only ever *shorten* life, so it's safe to leave unauthenticated.
> - **Gossip-median mesh clock:** each phone passively estimates a trimmed-median "freshest creation-ts seen across many independent senders" from the trial-decrypt stream it already processes; if its RTC disagrees beyond a threshold it flags itself clock-untrusted and expires by hop-energy.

### Knob 2 — Relay retention (you, carrying others' soup)
Size-cap primary ("≤ X GB, evict per policy"); time-cap as a labeled low-power mode. **Density-adaptive auto-knobs (§9)** make the globally-healthy behavior the locally-rational default, dissolving the tragedy-of-the-commons without identity.

### Knob 3 — Inbox policy (you, as recipient)
Disappear-after-read (now a free crypto-shred, §5) + inbox size cap.

### Seen-record (anti-resurrection / anti-replay) — sliding-window, not monolithic
Replace the flat 30-day Bloom (a memory-DoS + false-positive censorship surface — a flood of junk IDs drives FP→1.0, silently dropping real inbound) with a **sliding-window aging filter** (cuckoo with fingerprint+timestamp, or two-generation A2). Guarantee restated as a provable inequality: an ID can't be re-accepted within window W, and **W ≥ maxTTL + margin even under maximal flood** because aging is FIFO-by-time, not FP-by-saturation. The cuckoo variant supports **exact deletion** for panic-purge; per-ID retention keyed to that ID's own TTL.

### Panic / duress
"Delete-all" → wipe soup + inbox, IDs into the seen-record; **encrypt-at-rest** (locked seized phone yields nothing); **duress variant** wipes + rotates identity.

---

## 7. Deletion Model

- **Default = crypto-shred-on-read (§5).** The recipient's read punctures the key → their copy is unreadable *to themselves and any future seizer*, with **zero wire signal.** Every other copy dies at the global TTL. No beacon, no recipient leak. This is the anonymity-max default and it *strengthens* §12.4 (a seized device can't recover read messages).
- **Optional global early-delete = decoupled token, sender-fired, OFF by default, labeled "emits a detectable signal."** `delete-token = H(domain_delete‖secret)` is **decoupled from `message-ID`**, so revealing it purges cooperating buffers **without proving the original blob was real** (kills the retroactive "this was real" oracle). Because it's decoupled, you can **mint decoy deletes for your own cover blobs** — finally breaking the old structural wall (we couldn't hide a real delete among decoys when only the recipient could mint one).
- **Honest framing:** "delete" means *unreadable-on-read + TTL death on honest nodes*, **not** durable erasure against a hostile relay that retains ciphertext (it can't read it anyway, and with crypto-shred neither can a future seizer of the recipient).

---

## 8. Transport & Gossip — beating the airtime wall

**The real scale wall is airtime, not storage** (BLE has 3 advertising channels, no hopping; at ~200 co-located advertisers collision probability is high; a 1 KB blob is several chained PDUs). The buffer holding the soup does **not** mean the radio can stir it. So the gossip layer must move *minimal bytes*:

- **Rateless set reconciliation (Erlay-style IBLT / minisketch).** Two neighbors exchange a compact **sketch** of their 256-bit ID *sets* and transfer only the **symmetric difference** (cost ∝ difference, not set size). Rateless ⇒ a 2-second brush still makes progress; a long sit fully reconciles. Two phones sharing 1.99M of 2M blobs swap thousands of IDs, not a megabyte. **Fixes airtime, trial-decrypt cost, and battery at once, and gives anti-abuse a hook** (a neighbor who "wants everything" / whose sketch never decodes is fast-droppable *without identity*). The sketch's wire framing must be fixed-size / non-fingerprintable to keep invariant 4.
- Fall back to Bloom have/want when the difference is huge (long disconnection); bound decode attempts per neighbor (poisoning).
- **Connectionless first:** exchange the sketch + a proof-prefix over advertising/scan-response; open a connection only for the tiny difference transfer.
- **Platform reality (must be specified, not assumed):** publish a **per-platform transport matrix**; **iOS background cannot emit a generic ID-free blob to Android** (overflow-bitmask advertising, throttled cadence) → iOS is foreground-favored and its emission gap is an explicit, surfaced limitation, not a silent invariant-3 violation.
- **"Good crypto is not enough":** outer-frame MAC keyed by the blob's proof (cheap reject of tampered headers), parser fuzzing, **no pre-encryption compression**, constant ID-free advertisements (cf. Bluetooth Mesh Private Beacons).

---

## 9. Anti-Abuse — bound rate without a quota

A true per-sender quota is **fundamentally incompatible** with invariants 3 & 4 (you can't meter an identity you refuse to carry). Stop chasing it; build the **achievable shadow**: make sustained rate *physically expensive* and *locally bounded*.

- **VDF mint-cost + age-floor (replaces PoW).** Each blob carries a **Verifiable Delay Function** proof (Wesolowski/Pietrzak, class-group → no trusted setup) over its immutable core. A VDF is **sequential**: a $10M ASIC beats a phone by a *small constant, not 10⁴–10⁸×* — collapsing the mains-power asymmetry that made PoW useless. The iteration count is **also a trustless wall-clock floor** (a blob proving N squarings can't be older than N/max-rate) — structurally backstopping immortal-message/clock-skew. Verify is cheap (ms); generation is the equalizer (tune so a 1-min "next to me" message isn't gated by a 30-s VDF). Cover blobs run the same VDF (uniformity intact). N-device farms still get N sequential streams → Sybils bounded by *device count*, not human count.
- **Link-local relay tokens (the anonymous-rate-limit answer).** Don't meter "messages per identity" — meter **relaying per neighbor per session.** Each phone accepts/relays ≤ R blobs per neighbor per neighbor-local epoch; a slot costs a **single-use, unlinkable token consumed in the BLE handshake — never embedded in the blob.** Detection is trivially local (count tokens this epoch) → **no global tree, no synchronized clock, no convergence, no identity on the wire** (the exact things RLN/blind-tokens require and this architecture forbids). A flood now costs a scarce token **per hop per neighbor** (compounds against propagation) instead of amortizing like a pre-mined pool. *Open:* the Sybil-resistant token *source* (OOB-pairing mint is a candidate but needs anti-pairing-farm thought — research §17).
- **Eviction (attacker-uncorrelated, flood-aware).** Never least-VDF/least-PoW. With no routing there's no "closest-to-delivery," so retain by **real age** (youngest-by-actual-creation, *not* closest-to-TTL — else a flooder stamping TTL=7d wins), **randomized**, with a **per-neighbor buffer-share cap**. Note the residual: K attacker radios each under the cap still dilute honest blobs — random eviction blunts, doesn't remove; the VDF+token cost upstream is what actually throttles the inflow.
- **Density-adaptive auto-knobs.** Cover floor, relay floor, and token price are pure functions of **locally-observed density** (distinct *peer radios*, buffer pressure — hard-to-forge): dense ⇒ throttle (raise token price, lower your retention); near the cliff ⇒ be generous (≈0 token price, max retention). Identical rule for all nodes ⇒ no per-device tell; resolves sparse-vs-dense and the cold-start battery-for-nothing.

---

## 10. Anonymity Engineering — origination-event K-anonymity

**Reframed claim (the most important conceptual correction).** Per-blob uniformity is true but doesn't deliver what users imagine, and **device-linkage ≈ 1.0** (PHY fingerprinting). The defensible, *measurable* property is: **a real origination is indistinguishable from cover within a spatiotemporal anonymity set of size K**, where **K = cover-originations / real-originations**, surfaced in-app ("your message will hide among ~37 origination events") and treated as a **charge-independent floor.**

- **Receive-before-originate gate.** A phone never emits a fresh real ID "cold." It waits until it has recently relayed ≥ k distinct **novel** IDs, so the venue's first-sighting graph shows it constantly forwarding novelty and **the real origination is buried** (defeats first-emergence/first-spy provenance, the worst flooding-era attack). Degrades to a density-aware UX warning when novelty is scarce.
- **Loopix-style Poisson outbound mixing.** One outbound queue {relayed, dummies, self-loops, real} popped at exponential inter-emission times → timing reveals nothing about which blob is which; kills the origination timing tell.
- **Self-loops** (blobs sealed to your own key): triple duty — cover, **n−1/active-attack detection**, and a **no-routing reachability sensor** (loop returns ⇒ live mesh; never returns ⇒ percolation failure → powers the honest density UX).
- **VDF pre-generation is fine here** (unlike PoW) because the *gate + Poisson mixing*, not per-send timing, provide the anonymity — and VDF still imposes real per-blob sequential cost, so a pre-generated pool doesn't amortize a flood to zero the way a PoW pool did.
- **PHY caveat, stated plainly:** MAC/payload rotation defeat only cheap passive sniffers; assume a handset is uniquely labeled. **Publish the real device-linkability number from a USRP self-audit** rather than assuming it.

---

## 11. Scale — airtime budget beside the storage table

Storage (≈1 KB/blob): a 1–2 GB buffer holds 1–2M live blobs. **But the binding constraint is circulation, not capacity.** v0.3 mandates an **airtime-budget table** beside the storage table: *live-blobs-that-can-circulate-per-minute* given 3 advertising channels, collision-vs-density, and chosen cadence — computed and field-measured, not assumed. Rateless reconciliation (§8) is what makes the achievable circulation track the buffer instead of collapsing far below it.

**The core trade, unchanged:** undirected flooding buys anonymity and caps scale. Gathering-scale works; metropolis needs bridges. Shorter TTL + size caps + reconciliation are the levers that stretch feasible density.

---

## 12. Honest Limitations

1. **Percolation cliff has no clean answer.** Goal #1 (blackout) and the flooding mechanism physically collide below a critical mean degree — flooding can't cross a gap it can't bridge. Blind ferrying + LoRa/NAN (§14) buy **probability, not a guarantee.** This is the single biggest unsolved thing.
2. **Persistent sensor-net + PHY fingerprinting is made expensive, not defeated.** Device-linkage ≈ 1.0; the honorable guarantee is the O(crowd-size)-hardware bound in the header.
3. **No true per-sender quota** (incompatible with invariants 3/4); only the physical+link-local *shadow* (§9). RLN-on-the-social-graph is the only true quota and it bends invariants 1/3/6 → research-only.
4. **Durable deletion is impossible** against a hostile retainer; crypto-shred protects the *recipient's* device, TTL protects honest nodes. "Erase from the world now" is not claimed.
5. **iOS background** is foreground-favored; a real, surfaced limit on both reach and uniformity.
6. **Cold-start** is a go-to-market problem (planned gatherings, §16-P4), not solvable by physics.
7. **False-confidence harm** is the deadliest failure mode; the entire §13 UX layer exists to prevent it.

---

## 13. UX & Operational Security (truth-in-labeling)

Honesty in the *doc* is not honesty in the *running app* — the gap is where people get hurt. Cheap, high-impact, all-local:

- **First-run "what this protects / does NOT protect" cards**, default on. Lead with the honest bottle metaphor; drop "leave no durable trace."
- **Per-feature inline honesty** (TTL picker: *"the person you send to can keep it"*).
- **Honest send states:** *"Released to the soup"* / *"No peers nearby — holding"* / *"Expired before any peer saw it"* — **never a false "delivered."** (Private delivery confirmation only via the recipient's optional sealed ack.)
- **Mutual-presence pairing** (§4) + persistent trust badges; reserve red strictly for `Key-changed!`.
- **In-app "red-team reality" mode** that states the limitations the way §12 does.

---

## 14. Reach Beyond One Island (opportunistic, blind)

Per the Design Rule (§2) — accelerators the BLE-only core never depends on:

- **Blind mobility-aware ferrying.** A phone with no new blobs from any neighbor for T minutes (it has saturated its island) preserves its soup more aggressively to carry max payload to the next island — needs **no position, no destination**, just "am I in a stale pocket," plus a UX nudge ("you may be carrying messages out of range").
- **Wi-Fi Aware (NAN)** runs the *identical* uniform soup at ~100 m (≈100× neighbor-disk area, dodges the iOS-BLE throttle); **optional LoRa** companion for km-range rural blackout (low-rate, long-TTL bridging only). Both are offline (no AP/internet). NAN's richer discovery metadata must be hardened to §8 and threat-modeled (OpenNAN MitM literature). Must run BLE-only when unavailable.

---

## 15. Internet Bridge (opportunistic, anonymized-only)
Tor onion-rendezvous or Loopix/Nym mixnet **only**; refuse rather than downgrade; mixed/constant-rate egress; **tested with internet disabled** so the blackout path is never silently bridge-dependent.

---

## 16. Roadmap

- **P0 — Re-scope & measure.** Ship the **airtime-budget table** beside §11; reframe the public claims (airtime wall, K-anonymity, honest bottle promise). Analysis + copywriting, no architecture.
- **P1 — Highest-ROI, zero-tradeoff wins.** Rateless set reconciliation (§8); mutual-presence pairing + truth-in-labeling UX + honest send/trust states (§13). Cheapest, safest, closes the two most likely "gets-a-user-arrested" harms.
- **P2 — Anti-flood + anonymity primitives.** Link-local relay tokens (handshake-spent); Poisson outbound mixing + receive-before-originate gate + self-loops (§9/§10). Depends on P1's reconciliation layer.
- **P3 — Lifetime/storage hardening.** Hop-energy decrement + gossip-median clock; sliding-window seen-record; youngest-by-real-age eviction; density-adaptive auto-knobs (§6/§9).
- **P4 — Percolation + cold-start.** Blind ferrying; opportunistic NAN/LoRa; organizer "gathering kits" (poster-QR → pre-shared event bundle), pair-to-activate (useful at N=2), standby at N=0 (§14).
- **P5 — Serverless key-management.** Puncturable-encryption crypto-shred + decoupled delete-token; X-Wing hybrid + key-committing AEAD; deniable authenticator (§5/§7). Deepest correctness lift — benchmark on weak phones.
- **P6 — Continuous verification.** Multi-OS transport conformance harness (real circulation + iOS gaps); adversarial-eviction CI gate; **USRP PHY self-audit** (publish the device-linkability number); internet-disabled CI.

---

## 17. Research-Only (flagged, out of the shipping core)
Sybil-resistant token *source* without pairing-farms; fountain/RaptorQ K-of-N shards (anti-suppression, but multiplies the airtime wall — small N, high-stakes only); RLN-on-the-social-graph (the only true quota; bends invariants); stigmergic soft-gradient delivery (would it leak interest?). These are §13-style red-team targets for the next pass.

---

## 18. Prior Art
Briar/Bramble (audited analog; consider building on its transport/rendezvous), Bridgefy ("good crypto is not enough" — broke twice at the mesh layer), Signal sealed sender (receipts deanonymize → private ack only), FireChat (density requirement; HK "proof" was mostly LTE), SSB/Manyverse (bridge must be Tor-only), Berty/Wesh (anti-directory rendezvous), GNUnet Messenger (fixed-size padding + anonymous ego), Bluetooth Mesh Private Beacons (constant ID-free advertisements), Erlay/minisketch (rateless reconciliation), Loopix (Poisson mixing + loops), Waku RLN (why a true quota needs forbidden infra), puncturable encryption (Green–Miers), X-Wing (hybrid KEM).

---

## 19. The Soul-Check (from the red-team, verbatim-in-spirit)
The seven invariants are all the right calls and got **stronger** under review — VDF strengthens TTL, self-loops strengthen cover, reconciliation strengthens uniformity-at-transport, crypto-shred strengthens FS, truth-in-labeling strengthens honesty. **The design's defining honesty is its best feature.** Two truths to keep facing: the **percolation cliff** (goals #1 vs #2 collide; only probabilistic mitigations) and the **persistent sensor-net adversary** (made expensive, not beaten). State both plainly *in the app*, and the soul stays intact.

---

*Living document. Next: pressure-test §17 research items, or `/superpowers:writing-plans` to turn the §16 P0–P2 wins into an implementation plan. We are deliberately not building yet.*
