# P5-FS — Forward-Secure KEM construction spec (BKP-HIBE + CHK time-tree on X-Wing)

**Status:** DRAFT · **UNAUDITED** · spec-before-build (the loop's *spec* step) · **2026-06-30**
**Feature posture:** **DEFERRED in v1** — this spec defines the *target* construction to build + benchmark; it
ships nothing. Gated on B4 (cost — *compute sub-result measured, see below*) and B1 (audit). Extends
[p5-key-management-spec.md](2026-06-28-p5-key-management-spec.md) §2/§6 and the FS decision (release-blockers B4;
parent design §5.2). Evidence base: measured B4 primitive benchmark (2026-06-30), the FS decision memo, and a
multi-agent source-cited research stop (anonymous-HIBE selection + FoSAM corroboration).

---

## 1. Goal & non-goals
**Goal:** give polleneus **forward secrecy of already-received mail** — a recipient device seized at time *t*
cannot decrypt blobs whose epoch key it has already crypto-erased — *without* breaking the two hard constraints:
**sealed-sender anonymity** (no addressing on the wire; blobs trial-decrypted) and **byte-uniformity**.
**Non-goals (v1):** post-compromise security (no back-channel; needs OOB re-pair); PQ-FS (deferred — no
standardized mobile PQ-FS-PKE); per-message puncture / disappear-after-read (BFE = MB–GB keys, rejected for v1);
durable deletion against a hostile *retainer* (deletion is device-local).

## 2. The primitive — why BKP, not BBG
Sealed-sender delivery is **trial decryption with implicit addressing**: every node tries to decrypt every blob.
This **requires a key-private / anonymous** encryption scheme — a ciphertext must be **unlinkable to the
recipient's public key**, or an observer deanonymizes traffic and byte-uniformity is moot.
- **Chosen: Blazy–Kiltz–Pan (BKP, CRYPTO 2014) HIBE, SXDH (k=1) instantiation** (eprint 2014/581). BKP
  ciphertexts are **pseudorandom (PR-ID-CPA)** ⇒ semantic security **and** key-privacy in one property (attribution
  to verify: confirm PR-ID-CPA is established in BKP 2014/581 itself vs. the *cross-instance* key-privacy FoSAM
  adds — §8.1). It supports hierarchical **delegation** (`HIBE.Del`) → drives the CHK binary time-tree with
  parent-key erasure. Precedent: **FoSAM** (arXiv 2603.12871, KIT 2026) builds the same construction *family* (CHK
  epoch-tree over BKP on BLS12-381, implicit addressing, BLE flooding) with an Android prototype — a precedent for
  the primitive choice + a feasibility datapoint, **not** validation of *this* design: polleneus diverges (adds the
  PQ leg FoSAM lacks; uses a boot-clock, not FoSAM's gossip-voted clock) and **owes a re-proved cross-instance
  key-privacy argument** (§8.1).
- **Rejected: BBG-HIBE (and the `hohibe` crate).** BBG has constant-size ct + 2-pairing decrypt but is **NOT
  anonymous** — its ciphertext links to the recipient identity (Ducas 2010; Lee–Park–Lee survey). `hohibe`
  exposes delegation but is plain non-anonymous, unaudited BBG → unsuitable for trial-decrypt sealed-sender.
  Making BBG anonymous (Boyen–Waters) costs O(ℓ) ct / O(ℓ²) keys — loses the size win. (Detail: the FS memo's
  original "BBG-HIBE" pick is **superseded by BKP** for the anonymity requirement.)

## 3. Forward secrecy = CHK transform over BKP
Canetti–Halevi–Katz: a HIBE + a binary tree of time periods ⇒ a forward-secure (key-evolving) PKE. The recipient
holds the key for the **current epoch leaf** plus the **right-sibling node keys along the root→current path** (which
allow *forward-only* derivation), and **crypto-erases every consumed node key — including elapsed ancestors.**
(Retaining a raw ancestor key would re-derive erased descendants and break FS — ancestor erasure is mandatory.)
- **Fixed public address** (BKP master/root pk) — senders reuse the OOB-paired address for the whole **address
  lifetime**. No new wire field; the **epoch is derived from the blob's `creation_ts`** already in the header.
- **Tree depth = the ADDRESS lifetime, NOT the TTL.** Leaves = time periods over the intended address lifetime:
  `ℓ = ⌈log2(address_lifetime / Δt)⌉`. E.g. 1-hour epochs over **~2 years** ⇒ ~17 500 leaves ⇒ **ℓ ≈ 15**.
  (The earlier "ℓ=8" was wrong — depth-8 = 256 hourly leaves ≈ **11 days**, which would exhaust the address in
  ~11 days; corrected here.) Secret key = O(ℓ) node keys; when the tree exhausts, the address must be **OOB
  re-paired** — state that horizon. **Cost note:** unlike BBG (constant 3-element ct), **BKP ciphertext size grows
  with the identity length (~depth)**, so ℓ feeds directly into the ct-size budget (§7/§8) and must be measured at
  the chosen ℓ in M-FS1.
- **Smooth epoch rollover (adopt, from FoSAM §6.4):** advance every **Δt/2** but retain the *previous* epoch key,
  so a blob sent just before a boundary still decrypts.
- **FS window ≥ TTL — a *limit*, by construction in the target design:** the device must read in-flight unexpired
  mail for the whole TTL, so it cannot also have shredded that epoch's key — FS cleans only the trailing edge
  *beyond* TTL, never below it. (This *bounds* FS; it is not itself a protection guarantee.)

## 4. Clock that drives erasure (our conservative posture)
Deletion is driven by a **monotonic, local, hardware-backed boot-clock (FJB; P5 §3)** — **gossiped/network time
may only *lag* deletion, never advance it.** This **diverges deliberately from FoSAM**, which uses gossip-majority
voted time *as* the FS clock: voted time is **Sybil-skewable**, and a forward skew would shred unread keys
(timestamp-flood DoS). We trade some availability for attack-resistance. **OPEN (unsolved, P5 §10.1):** the
boot-reset gap — `CLOCK_BOOTTIME` resets on reboot and can't measure off-time; re-anchoring needs network time
(the very input FJB excludes). Availability-default = refuse to over-advance; disclose the FS-degradation window.

## 5. Hybrid integration (FS on the classical leg only) — a NEW combiner, not stock X-Wing
The classical X25519 KEM leg is **replaced by the BKP/CHK forward-secure KEM**; **ML-KEM-768 stays static (no FS).**
⚠️ Once X25519 is replaced this is **no longer X-Wing** — X-Wing's combiner + IND-CCA proof are specific to
X25519+ML-KEM. The combiner robustness (**secure if either leg holds**) must be **re-proven** for a
`(BKP-CHK-KEM ‖ ML-KEM-768)` composition. **Note BKP is CPA-only,** so the classical fallback is *weaker* than the
CCA ML-KEM leg; the robust-combiner + any CCA upgrade of the classical leg is a **B1 item**.
- **CLASSICAL-ONLY HONESTY GUARD (load-bearing), by adversary model:**
  - **(i) Non-seizing interceptor / harvest-now-decrypt-later:** safe if *either* leg holds — ML-KEM vs a quantum
    interceptor, the classical leg vs a classical one.
  - **(ii) Device seizer:** obtains the **static ML-KEM secret regardless**, so on seizure **only the classical FS
    leg can protect past mail — and only against a *classical* seizer** (erased epoch key + unbroken **dlog/SXDH on
    BLS12-381** ⇒ past mail safe). A **quantum seizer gets ZERO**: Shor recovers the **BKP master secret from the
    public key**, and the static ML-KEM secret is seized too. **Never claim "post-quantum *and* forward-secret"
    against one quantum-capable seizing adversary in v1.**
- **Epoch binding:** the KEM-derived key **already binds the epoch** (encap is to the epoch identity) — that is the
  primary binding. AEAD stays **key-committing**; if the epoch is *also* bound via AAD, use a transform that
  **commits AAD (CMT-3/CTX)** — *not* CMT-1, which commits only the key (P5 §6) — or fold the epoch into the outer
  HMAC transcript. HMAC/committing only; never bare Poly1305/GMAC.

## 6. Algorithms (spec level)
Type-3 pairing on BLS12-381. **Group assignment (BKP/FoSAM): ciphertext in G1, user keys in G2, key-mask in G_T.**
- `FS.KeyGen() → (pk, sk_0)` — master keypair; `sk_0` = root node key.
- `FS.Update(sk_i) → sk_{i+1}` — CHK tree walk: derive next epoch node via `BKP.Del` (re-randomized), **erase**
  the consumed parent/elapsed nodes (StrongBox wrapping-key crypto-erase, not file unlink).
- `FS.Encap(pk, epoch) → (ct, K)` — pairing-free: ~4–6 G1 muls + 1 G_T-exp; `ct` is all-G1 (uniform).
- `FS.Decap(sk_epoch, ct) → K | ⊥` — ~1–2 pairings (batch with `millerLoopVec` + one `finalExp`) + small G_T;
  `⊥` on the wrong epoch / not-ours (trial-decrypt). **The ⊥ path must be constant-time/indistinguishable.**

## 7. Cost budget (measured primitives → estimate)
From the 2026-06-30 mcl benchmark on a SD-695-class low-end phone (generic-C, no asm), big / little core:
pairing 1.15 / 6.34 ms · G1mul 0.12 / 0.68 · G2mul 0.23 / 1.25 · GT-exp 0.38 / 2.05 ms.

| op | estimate (big / little) | note |
|---|---|---|
| `Encap` | ~1 / ~5–6 ms | pairing-free; ≈ FoSAM's real Pixel-6 5.22 ms |
| **`Decap` (TRIAL-DECRYPT HOT PATH)** | **~1.6 / ~9–13 ms** | 1–2 pairings; FoSAM's real Pixel-6 decrypt 6.70 ms sits *inside* this [big,little] bracket; **× inbound-blob rate = the real budget** |
| `Update`(+erase) | ~tens–~120 ms, once/epoch | FoSAM Pixel-6 ratchet 120 ms; background, not hot |

These are **structure-derived estimates from the measured BBG-shaped primitives** (not a published BKP op-table or a
reference impl); M-FS1 replaces them with the real BKP-at-depth-ℓ scheme numbers. **Verdict (on the estimates):**
they sit well inside any plausible interactive target; the formal B4 threshold stays TBD-pending the B2
field-airtime anchor. The binding constraint is **Decap × inbound-flood rate** (every new blob is trial-decapped
with the current-epoch key — one attempt per blob, gated by the seen-set), not single-op latency.

## 8. Security obligations & implementation hazards (→ B1 audit list)
1. **Replicate FoSAM's cross-instance key-privacy proof.** BKP's native anonymity is *within one master key*; we
   need **PR-HID-CPA ⇒ FS-ANON** across instances (FoSAM §7.2). Do not assume — reprove for our composition.
2. **No reference BKP on a raw C pairing lib exists** — this is **new crypto code** (the affine-MAC HIBE *and*
   the pseudorandomness that anonymity rests on). The single biggest B1 surface. (FoSAM's Rust code is
   unreleased / not mcl.)
3. **Constant-time:** secret-dependent muls via `mclBnG1_mulCT`/`mclBnG2_mulCT` (default `mul` is NOT CT);
   **constant-time / indistinguishable trial-decrypt failure path**.
3b. **Byte-uniformity of the FS leg — OPEN (flagged, NOT solved).** PR-ID-CPA gives pseudorandom-*as-a-group-element*,
   which is **not** uniform-random-*bytes-on-the-wire* (invariant #1). A compressed BLS12-381 **G1 point is NOT
   byte-uniform** — fixed flag bits, only ~½ of x-values valid — so it is distinguishable from random 48-byte
   strings *even with zero encoding bias*, and **BLS12-381 G1 has no clean Elligator**. Wire-uniformity for the
   all-G1 FS-leg ct needs an **Elligator-squared-class encoding at ~2× expansion** — a real ct-size cost. **Until
   that is designed, byte-uniformity of the FS leg is OPEN/DEFERRED (do not assert it holds)**; the ~2× expansion
   must be booked into the (to-be-re-derived) BKP ct-size budget.
4. **Erasure is the thing FS rests on** — must be **StrongBox wrapping-key crypto-erase**, not file deletion;
   **measure erase latency + flash endurance** (still UNMEASURED — the next on-device task). If erasure isn't
   irreversible on the target TEE/flash, the FS claim is theatre even classically.
5. **mcl audit caveats** (Quarkslab/EF): library is audited but flagged reliability issues to fix before
   production; pin a reviewed version; verify `hashAndMapTo` DST (draft-06/07/EIP-2537, not final RFC 9380).
6. **Type-3 discipline:** ct∈G1 / keys∈G2 exact; validate peer points (subgroup/low-order); FIPS-203 checks on
   the static ML-KEM leg unchanged.

## 9. Build plan (milestones)
1. **M-FS1:** minimal BKP-HIBE (SXDH) Encap/Decap/Del on mcl as a standalone arm64 module + KATs; bench the
   *real* scheme on the low-end phone (replace the §7 primitive-estimate with measured scheme numbers).
2. **M-FS2:** CHK binary time-tree (epoch from `creation_ts`, smooth Δt/2 rollover, node erase) + constant-time
   trial-decap + uniform serialization; property tests (anonymity self-test: ct indistinguishable across keys).
3. **M-FS3:** StrongBox key-wrapping + crypto-erase; **measure erase latency + endurance** (closes the last B4
   on-device unknown).
4. **M-FS4:** X-Wing integration (FS classical leg + static ML-KEM, committing AEAD w/ epoch-AAD) behind a flag;
   flag-day envelope-size handling; FS stays **OFF by default** until B1.
5. **Gate:** B1 audit of the BKP-on-mcl code + the key-privacy proof + erasure guarantee → only then FS-on ships.

## 10. Honest status line
FS **compute feasibility is de-risked via measured pairing *primitives* + estimates** — the **full BKP/CHK scheme is
NOT yet benchmarked** (M-FS1), and the **size budget is estimated, not measured, and must be re-derived for BKP**
(all-G1 *depth-dependent* ct ≠ BBG's constant 3-element ct, + the ~2× byte-uniform encoding of §8.3b). The
**construction is selected and precedented** (BKP + CHK, per FoSAM). FS is **NOT built, NOT shipped, NOT audited,
and byte-uniformity of the FS leg is OPEN.** v1 remains **static key + FS DEFERRED + in-app disclosure**. This spec
is the green light to *build M-FS1*, nothing more.
