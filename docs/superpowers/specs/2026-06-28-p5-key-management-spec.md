# polleneus — P5: Serverless key-management (v1 design for audit) + on-device benchmark protocol

**Version:** v0.1 — 2026-06-28 · **Roadmap:** P5 (§16) · **Status:** **DESIGN FOR AUDIT — UNAUDITED.**
**Parent design:** [polleneus v0.5 §4/§5/§6/§7/§9](2026-06-25-polleneus-design.md) · **Inherits:** P3 time-ratchet caveat

> **READ THIS FIRST — what this document is and is NOT.** This is a *consolidation + hardening* of the
> scattered key-management design (parent §4/§5/§7/§9) into one reviewable artifact, **plus** the substantive
> new piece P3 demanded (the time-ratchet **forward-jump bound**) **plus** the B4 on-device **benchmark
> protocol**. It is **not** validated cryptography and ships **no crypto code**. Per **release-blocker B1, no
> installable build may exist before an independent adversarial audit of this stack.** Every primitive below
> is a *proposal to be audited*; §10 lists the open questions the auditor must close. Treating any line here
> as "secure" is the project's deadliest failure mode (false confidence).

## 1. Scope

Covers the v1 **key lifecycle**: identity keys, the sealed-envelope KEM, time-ratcheted forward-secure
decryption (and its forward-jump bound — the P5 core contribution), key-committing AEAD, the deletion model,
the deniable authenticator, and the v1 spend primitive's key material. **Out of scope / deferred:** the
bespoke Fiat-Shamir ZK-spend nullifier (post-v1, parent §12.7 / B4); any networked key server (the design is
serverless by invariant). The **B4 benchmark protocol** (§9) is the named release gate for spend +
key-evolution cost on low-end Android.

## 2. Key hierarchy (serverless, no prekey batch)

```
Root identity seed  ──(SE/TEE StrongBox, auth-bound, setUnlockedDeviceRequired)──┐
   │                                                                             │ never leaves the enclave
   ├─ long-term X-Wing FS/puncturable KEM keypair (X25519 + ML-KEM-768)  ← recipient address (stable)
   │     └─ per-sub-epoch decapsulation capability k_e, e=0..E in the ≤7 d window — PUNCTURED/EVOLVED forward
   │        so deleting an elapsed k_e removes decapsulation for that sub-epoch WITHOUT changing the address
   ├─ Ed25519 signing key (identity) — out-of-band SAS / key-change detection only, NOT a transferable
   │     per-message signature (that would void §6 deniability)
   └─ per-message keys                 derived per blob via the KEM-encapsulated shared secret
```

- **The forward-secure / puncturable KEM is the load-bearing, UNSPECIFIED-here construction.** "Deleting
  `k_e` destroys decapsulation for sub-epoch `e` while the public address stays stable" is exactly what a
  forward-secure (or puncturable) KEM provides; a plain static keypair with a side-derived `k_e` does **NOT**
  (a seizer with the static private key re-decapsulates → FS fails). Parent §5.2's "small constant key size"
  is optimistic vs. the BFE/SafetyPin cost reality. **Specifying this construction + its cost is the #1 audit
  item (§10.2);** until then the §3 forward-secrecy claim is *construction-conditional*.
- **X-Wing PQ-hybrid KEM (X25519 + ML-KEM-768), both components always**, version bound into the AEAD
  transcript; classical↔hybrid envelope-size change is a **flag-day** (a size delta is a fingerprint — never a
  mixed population). (Parent §5.2.)
- **Ed25519 reconciliation (vs parent §4).** Parent §4 gives every identity an Ed25519 signing key and §5.2 a
  "signed/authenticated transcript." A **transferable per-message signature would break §6 deniability**, so
  v1 scopes Ed25519 to **out-of-band identity / SAS pairing + key-change detection** (parent §4 trust states);
  in-band message authentication uses the **deniable** authenticator (§6). The auditor must confirm nothing in
  the envelope carries a non-repudiable signature that re-incriminates a sender (§10.3).
- **All persistent key state is wrapped under an SE/TEE (StrongBox) key**, auth-bound; "shred"/panic-wipe =
  destroy the wrapping key (crypto-erase immune to wear-leveled NAND remnants). The app must **surface
  in-app when SE/TEE is unavailable** (the hardware-honored-shred guarantee then degrades). (Parent §5.2/§6.)

## 3. Time-ratcheted forward-secure decryption + the FORWARD-JUMP BOUND (the P5 core)

**Mechanism (parent §5.2):** the ≤7 d TTL window is divided into fine time **sub-epochs**; the per-sub-epoch
decryption key `k_e` is **deleted on a schedule** once that sub-epoch has elapsed — *whether or not the
message was read* — so a device seized at time `t` cannot recover mail whose sub-epoch key was already
destroyed — **conditional on a forward-secure / puncturable KEM (§2) that makes deleting `k_e` actually
destroy the *decapsulation capability* for that sub-epoch while keeping the recipient address stable.** If the
long-term static decapsulation key were merely retained and `k_e` side-derived, a seizer re-decapsulates and
forward secrecy **fails outright** — so that construction is the load-bearing audit item (§10.2). The claim is
**computational** (it also assumes the AEAD/KEM are unbroken — the very harvest-now-decrypt-later break X-Wing
exists to delay), **not** information-theoretic "w.p. 1": "deletion of your own copy becomes computationally
undecryptable, assuming the FS-KEM is sound and SE/TEE honours the crypto-erase." Not a probabilistic-survival
claim (there is no "survives with probability p"), but not unconditional certainty either.

**The hole P3 flagged (and this PR closes):** the ratchet schedule is driven by a clock, and the P3 mesh
clock is **biasable toward the future** (a future-dated `creation-ts` flood, or a fast/forged clock, can
advance a node's notion of "now"). An unbounded ratchet would then **delete sub-epoch keys for mail that has
not yet been read / not yet even arrived** — a **timestamp-flood key-destruction DoS** that silently shreds
unread mail. P3 explicitly deferred this bound to P5; here it is:

**FJB — Forward-Jump Bound (normative; supersedes the parent §5.2 "ratchet driven by gossip-median" clock
source — this is a deliberate change, the parent line is superseded).** Key deletion advances on a
**monotonic, local, hardware-backed clock**, never directly on gossiped/network time. Specifically:
1. **Monotonic floor.** The ratchet's "elapsed" is measured by the device's **monotonic boot clock**
   (`CLOCK_BOOTTIME`-class, non-settable, survives sleep), NOT by `creation-ts` / NTP / gossip-median. A
   network-supplied time can only ever *lag* deletion, never *accelerate* it past real elapsed time —
   **between reboots** (see the boot-reset gap below, which this does NOT cover).
2. **Rate cap.** Between reboots the ratchet may advance at most **one sub-epoch per real sub-epoch of
   monotonic time** (plus a small bounded slew). No external input can make it skip ahead while the boot
   clock runs continuously.
3. **Corroboration gate for boot-reset catch-up — KNOWN-INCOMPLETE.** `CLOCK_BOOTTIME` resets to 0 on reboot
   and cannot measure off-time. After a reboot the only way to re-anchor "now" is **network-estimated time**,
   gated on **K independent corroborating timestamps** and capped a safety margin behind the corroborated
   median. **This gate is NOT currently sound:** the only passive estimator we have is the P3 trimmed-median,
   which **P3 itself declares structurally non-functional and DEFERS as an open problem** (median of
   `created_at` tracks message-age centre-of-mass, not "now"; freshest is forgeable). A **Sybil / majority
   timestamp flood** — explicitly out of P3's scope, and only "dented" by the parent §9.6 funded-device bound — can
   present `K` future-dated corroborating timestamps at a victim's boot and push the catch-up past the margin,
   **deleting unread mail.** So the boot-reset catch-up path **can still fail toward DATA LOSS.** This is an
   **unresolved open problem (§10.1)**, not a solved bound; until a sound passive (or hardware-monotonic
   cross-boot) clock exists, the conservative client behaviour is **(3a) never auto-delete on boot until
   corroboration from a trusted source the user accepts** — which then triggers the reverse risk below.
4. **Never delete within the read horizon.** A sub-epoch key is retained until `monotonic_elapsed ≥
   sub_epoch_end + read_grace`, so freshly-arrived unread mail is never shredded by a *between-reboot* clock
   excursion.

**Honest residual (scoped — corrected after review):**
- **Always-on (no reboot):** FJB genuinely defeats the P3 timestamp-flood key-destruction DoS — deletion
  tracks real monotonic time and **cannot be accelerated**; it fails toward availability, not deletion.
- **Boot-reset + Sybil-timestamp:** the gate above is **not yet sound**; this path can still delete unread
  mail. NOT closed — tracked as the load-bearing §10.1 open question.
- **Reverse risk (FS-weakening), NOT "slight":** in the mission's own blackout case — device reboots while
  offline — `CLOCK_BOOTTIME` is 0, off-time is unmeasurable, and **no peers exist to corroborate**, so the
  ratchet **stalls**: elapsed sub-epoch keys are *retained* and a later seizer recovers **more** mail. The
  degradation window is **"until the next successful corroboration"** (potentially the whole offline period),
  **not** bounded by the monotonic floor. The availability default (don't delete without corroboration) and
  the forward-secrecy goal are in **direct tension at boot**; the chosen default favours availability and
  **discloses the FS degradation window.**
The auditor must confirm whether the target SE/TEE exposes any *cross-boot* trustworthy monotonic counter
(some StrongBox/rollback-protected counters do) that would let FJB close the boot gap without the broken
median. **Open — §10.1.**

- **Optional per-message disappear-after-read** is a puncture *on top* (Bloom-Filter-Encryption); its `p` is a
  **collateral over-deletion** (availability cost), never a chance the target survives. OFF by default.

## 4. Key-committing AEAD + trial-decrypt

- **Key-committing AEAD** (e.g. a committing transform over the AEAD, not vanilla Poly1305) is **intended to
  make trial-decrypt unambiguous** — needed both *before and after* the PQ hybrid, where ML-KEM non-binding
  could otherwise make "is this blob mine?" ambiguous and open a **partitioning-oracle / invisible-salamander**
  class attack. (Parent §5.2.) The committing construction + its security proof (pre- and post-PQ) is an
  **audit item (§10.4)** — not yet validated.
- Trial-decrypt cost is bounded by the **parent §8** reconciliation (only the symmetric-difference set is
  trial-decrypted per contact), not by the whole soup.

## 5. Deletion model (consolidated — parent §7)

- **Default = time-ratcheted crypto-shred (§3).** Device-local; **computationally** undecryptable to a later
  seizer *conditional on the §2 FS-KEM + SE/TEE erase* (see §3 — not unconditional "w.p. 1"); zero wire signal.
- **Optional global early-delete = `delete-token = H(domain_delete ‖ secret)`,** decoupled from `message-ID`,
  OFF by default, **labeled "emits a detectable signal."** Hardening (parent §7): (1) emitting a delete
  **costs the same anti-abuse spend** as any wire action (no flush-DoS firehose); (2) a held blob is purged
  **only on an exact full-length match** to a per-blob delete-tag **committed inside the sealed transcript**
  (no prefix/loose match ⇒ an attacker can't evict blobs it didn't author); (3) real + decoy deletes ride the
  **parent §10** Poisson outbound queue (decorrelate from reads); (4) **honest disclaimer:** seizing the secret
  retroactively links `delete-token → message-ID`.
- **Deletion is DEVICE-LOCAL, not durable elsewhere** (parent §12.4): it cannot reach a hostile retainer's
  ciphertext, screenshots, OS backups, or notification mirrors. "Erase from the world now" is **not claimed.**

## 6. Deniable authenticator (parent §5)

Sender authentication should be **deniable** (a recipient can verify the sender but cannot produce
**transferable proof** of authorship to a third party) — so a *recipient* cannot later incriminate a sender.

**v1 construction (decided — research-backed):** a **static pairwise shared-key MAC**. Carry an outer
Encrypt-then-MAC tag `HMAC-SHA-256(K_auth, transcript)` over the X-Wing / key-committing-AEAD ciphertext, where
the MAC `transcript = sealed_blob_ciphertext_bytes ‖ version ‖ global-TTL ‖ message-ID ‖ ephemeral_pk ‖
creation_ts ‖ domain_label` (i.e. the actual ciphertext bytes — true Encrypt-then-MAC — **plus** the mutable
wire-header fields the parent design §5.2 declares authenticated, so a relay cannot alter TTL/version
undetected; this reconciles design §5.2's "authenticated transcript" with this section). `K_auth =
HKDF(K_pair, "…senderauth…")` and the per-contact root `K_pair = HKDF(X25519(my_id_sk, peer_id_pk) ‖ stored
ML-KEM-768 shared secret)` is established **once at pairing** and persisted. Because **both** peers hold
`K_pair`, either could have forged the tag → it is non-transferable (deniable). Being symmetric, the
authenticator is **post-quantum as a symmetric primitive**. The *general* feasibility basis is
Dodis–Katz–Smith–Walfish (TCC 2009): strong deniable authentication is impossible in the PKI/signature setting
under adaptive corruption but **achievable in the symmetric shared-key setting given a shared key**. **Caveat
(audit item §10.3): DKSW does not cover THIS establishment** — the PQ-deniability of the
X25519-static-static ‖ stored-ML-KEM `K_pair` + outer-HMAC composition is not yet proven; "post-quantum" here
means the primitive resists Shor, not that this exact construction's deniability is proven against a quantum
coercer. The sender identity is named **inside** the seal, so trial-decrypt stays O(1) (recipient decapsulates
with its own key, then verifies the one named contact's `K_auth` — no O(contacts) trial-MAC).

**Correction to the prior candidate ("MAC keyed by the KEM shared secret"):** a MAC keyed by *only* the
per-message KEM shared secret (ephemeral→recipient) authenticates **nothing about the sender** — any party can
encapsulate to the recipient's public key and produce a valid MAC. Sender authentication **requires binding the
sender's static identity** (the static-static / stored-KEM `K_pair` above), not the per-message secret alone.

**Construction rules (carried to the §10.3 audit):**
- the **outer MAC MUST be HMAC** (or another committing / collision-resistant MAC), **never Poly1305/GMAC** — a
  polynomial MAC re-opens a partitioning oracle (key multi-collisions) that can deanonymize;
- the inner AEAD commitment level is a deliberate choice: CMT-1 (key-only) does **not** commit AAD, so if any
  bound field's tamper-evidence is load-bearing it needs CMT-3/4 (e.g. CTX / HtE) — the outer Encrypt-then-MAC
  avoids that dependency by binding the ciphertext directly;
- the sealed envelope carries no random nonce field, so the inner key must be **single-use** (it is — a fresh
  per-message X-Wing ephemeral derives it) or, as a hedge, an MRAE be used. **Note (SEAL-03): bare AES-GCM-SIV
  is itself NON-committing** and a partitioning-oracle target — if used it must sit *under* the §4 committing
  transform, never as the committing layer itself;
- deniability delivered is **offline** message deniability (the achievable target); **online** deniability is
  provably unreachable in an asynchronous store-and-forward setting and is therefore **not promised**;
- the **PQ deniability of this static-KEM-pairwise construction specifically** is under-studied in the
  literature → explicit audit item (§10.3).

**Reserve option (not v1):** if a *self-identifying* authenticator (no pre-shared secret / no named-sender
field) is ever required, use a **2-party ring signature** (≈ designated-verifier; e.g. Gandalf NTRU/Falcon
~1.2 KB at ring 2) — but it ≈ doubles the blob and breaks byte-uniformity economics, so it is held in reserve.

**Scope of the protection (do not overclaim):**
- It protects against the **recipient turning informant / a seized recipient transcript being used as
  transferable proof.** It is **VOID against a coercer who IS or controls the recipient device** — that device
  holds the plaintext and the in-seal sender identity regardless of MAC deniability. (So §8 must NOT list it as
  a *recipient-device-seizure* defense — corrected.)
- It is undermined if **anything else in the envelope is non-repudiable** — e.g. a per-message Ed25519
  signature (parent §4/§5.2 "signed transcript") would be transferable proof and **break** deniability. v1
  therefore keeps Ed25519 out-of-band only (§2); the auditor must verify no in-envelope signature/transcript
  binding re-incriminates (§10.3).
- **Metadata deniability is separate and out of scope here** (origination-identifiability is B2/B3): deniable
  authentication does not hide *that you transmitted*.
**The construction + its deniability proof against a coercer is an audit item (§10.3);** do **not** ship on an
unproven deniability claim (a false deniability promise is *worse* than none — it invites incrimination under
a false guarantee).

## 7. v1 spend primitive + key-evolution (B4-gated)

- **v1 spend = a standard, well-studied primitive (blind-RSA or BBS show)** — chosen over bespoke ZK because
  the primitive is mature; **but the polleneus *integration* (token spent as a nullifier inside the BLE
  handshake, token-anchored gossiped seen-set) is itself UNVALIDATED and B1-audited (§10.5)** — "well-studied
  primitive" ≠ "our spend is audited." **The bespoke Fiat-Shamir ZK nullifier is DEFERRED post-v1** (parent
  §9.2/§12.7): ~88 % of disclosed SNARK bugs break soundness; v1 must not gate its rate-limit on unaudited ZK.
  The **parent §9.5** non-ZK fail-closed PHY-session quota bounds any future ZK bug to a leaf-level flood.
- **Key-evolution** (the time-ratchet rewrites + token TTL rotation) has a **compute + battery cost** that
  must fit the budget that keeps the soup uniform and the UX usable — measured by the **B4 protocol (§9).**

## 8. Key-management threat model (what the auditor attacks)

| Threat | Defense (proposed) | Audit must confirm |
|---|---|---|
| Device seizure (locked) | encrypt-at-rest + SE/TEE-wrapped keys + time-ratchet shred (needs §2 FS-KEM) | SE/TEE gates; the §2 FS-KEM actually destroys elapsed decap capability (no NAND remnant, no static-key re-decap) |
| Device seizure (unlocked/coerced) | panic/duress wipe + only forward keys present | duress wipe completeness. (NB the deniable authenticator does **NOT** help here — it is **void** when the coercer controls the recipient device; it protects the sender vs a *recipient-turned-informant*, not a seized device) |
| Sender incrimination by a recipient | deniable authenticator (§6) — no transferable proof | DV-deniability proof; **no in-envelope non-repudiable signature undercuts it** |
| **Timestamp-flood key-destruction DoS** | **FJB (§3): monotonic floor + rate cap + read-grace (always-on)** | always-on: closed. **Boot-reset catch-up: OPEN (§10.1)** — gate relies on the P3-deferred trimmed-median; Sybil flood can still delete unread mail |
| Partitioning oracle / invisible-salamander | key-committing AEAD | the committing construction is sound pre- and post-PQ |
| Harvest-now-decrypt-later (PQ) | X-Wing hybrid (both components always) | hybrid combiner correctness; no downgrade to one component |
| Token forge / re-spend | standard blind-RSA/BBS primitive + parent §9.5 fail-closed quota | the polleneus *integration* — spend unforgeable; nullifier binding (§10.5) |
| Delete-token abuse | spend-cost + exact-match + sealed-transcript tag | no eviction of un-authored blobs |

## 9. B4 — on-device benchmark protocol (the release gate)

**Goal:** measure that the v1 spend (standard blind-RSA/BBS primitive) + key-evolution stack fits a budget
keeping the soup uniform and the UX usable, on a **named low-end Android** (e.g. a ~US$80–120 handset, ≥1 representative SoC; record exact
model/SoC/Android version + StrongBox availability in the result).

**What to measure (per op, median + p95 + battery):**
1. **Spend (blind-RSA / BBS show)** generate + verify latency, under the BLE handshake serialization.
2. **Key-evolution**: one time-ratchet step (sub-epoch key derive + old-key crypto-erase + SE/TEE rewrite),
   and token-TTL rotation, latency + wake cost. **Plus the §2 FS-KEM puncture cost** (the load-bearing item —
   BFE/SafetyPin-class punctures can be expensive; this is what decides whether fine sub-epochs are feasible).
3. **Envelope seal/open**: X-Wing encaps/decaps + key-committing AEAD, **under BLE MTU/fragmentation** (the
   envelope is fragmented over GATT; measure reassembly + decap cost at the real MTU, not in-memory).
4. **Trial-decrypt throughput** over a reconciled symmetric-difference batch (per parent §8) — ops/sec and battery/100 ops.
5. **Sustained battery**: %/hour for a representative duty cycle (advertise + scan + reconcile + ratchet) over ≥1 h.
6. **WORST-CASE arm (the DoS-relevant cost, not the representative one):** maximum sub-epoch catch-up
   (many ratchet steps at once), **max symmetric-difference** reconciliation + trial-decrypt, peak spend rate.
7. **SE/TEE write-rate / endurance:** fine sub-epoch ratcheting does a StrongBox rewrite **per step**; measure
   StrongBox op latency, any rate-limiting, and **write-endurance** over the number of sub-epochs in ≤7 d
   (a feasibility risk — may force coarser sub-epochs; **audit item §10.8**).

**Pass criteria — thresholds are TBD-PENDING-UPSTREAM (a gate cannot pass against a TBD anchor):**
- Per-op latencies within the **BLE contact-episode budget** — pin the brush-by contact duration (**parent §8
  implies ~2 s**) and cross-reference the **P0 airtime budget** *(itself owes a field/USRP number — B2; the
  threshold inherits that TBD)* and the **P1 reconciliation cost**. State the number when both anchors land.
- Key-evolution + FS-KEM puncture + ratchet wake cost ≤ a battery budget that does not dominate idle drain.
- **Worst-case** (item 6) still completes within a relaxed budget (or the client must degrade gracefully —
  specify).
- StrongBox path available + write-endurance sufficient on the target (else hardware-shred degrades — record
  and surface).

**Protocol hygiene:** fixed seeds where applicable; report device/SoC/OS/StrongBox; ≥N runs with median+p95;
publish the raw numbers (no "fast enough" without the table). This protocol is **runnable only on real
hardware by the user / an engineer with a device** — it is a *measurement plan*, not a sim (the simulator
cannot measure handset crypto/battery).

## 10. Open questions for the auditor (B1) — non-exhaustive

1. **FJB boot-reset gap (the biggest open item):** the §3 boot-catch-up gate relies on the **P3 trimmed-median
   clock-trust estimator, which P3 itself declares non-functional / deferred** — so a Sybil/majority timestamp
   flood at boot can still **delete unread mail**. Does the target SE/TEE expose a **cross-boot, rollback-
   protected monotonic counter** that would let FJB re-anchor without the broken median? If not, what is the
   sound boot-time clock-trust mechanism? Until answered, **always-on** is closed but **boot-reset is OPEN**.
2. **The §2 forward-secure / puncturable KEM (load-bearing for ALL of §3/§5):** specify the construction that
   makes deleting an elapsed `k_e` destroy decap capability with a **stable public address**; prove it; and
   measure its puncture cost (§9.2/§9.6 feasibility — BFE/SafetyPin can be expensive). Without this, the
   forward-secrecy claim is unsubstantiated and could fail outright (static-key re-decap).
3. **Key-committing AEAD construction** choice + proof, **pre- and post-PQ**; partitioning-oracle resistance.
4. **Deniable authenticator** construction + deniability-against-coercer proof; **void if the coercer controls
   the recipient device**; **verify NO in-envelope non-repudiable signature/transcript undercuts it** (the
   parent §4/§5.2 "signed transcript" must not be transferable). Do **not** ship on an unproven claim.
5. **X-Wing combiner** + transcript binding; no single-component downgrade; flag-day enforcement.
6. **Spend primitive** (blind-RSA vs BBS) unforgeability + nullifier binding under the **parent §9.3**
   token-anchored gossiped seen-set — the *integration*, not just the textbook primitive.
7. **Crypto-erase actually erases** on the target NAND/SE/TEE (no remnant).
8. **SE/TEE write-rate / endurance** under per-sub-epoch ratchet rewrites over ≤7 d (may force coarser
   sub-epochs — interacts with the FS granularity vs feasibility trade).
9. **Side-channels** (timing/power) on the low-end target for decaps / spend / puncture.

## 11. Honest limitations (carried + corrected after review)

- **UNAUDITED.** Nothing here is validated; B1 gates all of it. Two headline contributions are
  **construction-conditional or scoped**, not settled (below).
- **FJB is closed only for the ALWAYS-ON case.** The **boot-reset catch-up path can still delete unread mail**
  (it leans on the P3-deferred trimmed-median; Sybil-flood vulnerable) — §10.1, unresolved. And the reverse
  risk (post-reboot-offline ratchet **stall** ⇒ a seizer recovers more) degrades forward secrecy **until the
  next corroboration**, not "slightly." The chosen default favours availability and discloses both windows.
- **Forward-secret deletion is computational + construction-conditional** (needs the §2 FS-KEM + SE/TEE
  erase), **not** unconditional "w.p. 1" — §3/§10.2.
- **Deniable authentication** protects against a *recipient-informant*, is **void against a coercer who holds
  the recipient device**, and only if no other envelope field is non-repudiable — §6/§10.4.
- **Deletion is device-local** (§5) — not durable on hostile retainers/backups/screenshots.
- **No metric is "fast/secure enough" without the B4 table / the audit sign-off;** B4 thresholds are
  TBD-pending the P0 field-airtime anchor (B2).
