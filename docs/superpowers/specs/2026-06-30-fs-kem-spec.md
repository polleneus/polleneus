# P5-FS — Forward-Secure KEM construction spec (BKP-HIBE + CHK time-tree on X-Wing)

**Status:** DRAFT · **UNAUDITED** · spec + **M-FS1 built/measured** · **2026-06-30 (rev 2026-07-01: M-FS1)**
**Feature posture:** **DEFERRED in v1** — the *construction* is now implemented + KAT-correct + benchmarked (M-FS1,
§7/§9); FS still ships nothing in v1. Gated on B4 (cost — *full BKP scheme measured + KAT-correct*) and B1 (audit). Extends
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

### 2.1 Anonymity in OUR model — likely avoids the deferred AHIBKEM (M-FS1 adversarial verification)
The literature caveat is that the **plain HIBKEM with a PUBLIC delegation key `dk` is NOT anonymous for L>1** (a
pairing linking test `e(c0, Σf_i(Ēᵢ;d̄ᵢ)) =? e(c1,[b]₂)` decides the recipient — but it **consumes only G2 `dk`
material**). **In CHK-FS, `dk` is the recipient's PRIVATE delegation state; only `mpk` (all G1) is the public
address.** Adversarial verification (M-FS1) established: with `dk` private, a passive/contact adversary's only G2
element is the bare generator `P2`, so the linking test **has no G2 leg to stand on at any depth** — and every
passive/contact distinguisher (cross-ct linkage, "is this ct for known mpk `[a]₁`?") **collapses to DDH-in-G1**,
hard under SXDH (you cannot pair two G1 elements, and `r` lives only in G1). **⇒ the private-`dk` HIBKEM is
plausibly recipient-anonymous, which would let us AVOID the research-grade AHIBKEM.** This is a legitimate downgrade
"research-blocked AHIBKEM → engineering + an SXDH key-privacy proof," but it is **DEFERRED-pending-proof, NOT
proven** (§8.1): BKP proved IND-CPA (secrecy of K), *not* key-privacy. Honest non-leaks to state: anyone holding the
recipient's `usk`/`dk` (the recipient, or a delegated parent up the CHK chain) links **by design** — anonymity is
only against **non-recipients**.

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
  re-paired** — state that horizon. **Cost note (CORRECTED by the M-FS1 measurement):** BKP ciphertext is
  **constant — 4 G1 = 192 B, depth-INDEPENDENT** (the identity aggregates into `Z_id = Σ f_i Z_i` *before*
  encryption, so `c1` is a fixed 2-vector regardless of ℓ). ℓ only grows the *secret-key / delegation* state
  (O(ℓ) G2 stored on-device), **not** the wire ciphertext. (This retracts the earlier "ct grows with depth"
  assumption inherited from the research stop.)
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
- `FS.Encap → (ct = 4 G1 = 192 B, K∈G_T)` — `c0=(ar,r)`, `c1=Z_id·r` (`Z_id=Σf_i Z_i`), `K=e(r·[z0]₁,P2)`.
  **Measured 5.29 ms** (one pairing in K; can be made pairing-free via a precomputed `e(P1,P2)` + GT-exp — M-FS2 opt).
- `FS.Decap → K` — `millerLoopVec` over 4 pairs `{(c0[0],v),(c0[1],u),(−c1[0],t0),(−c1[1],t1)}` + one `finalExp`
  (the `−c1` fold makes it the quotient `e(c0,(v;u))·e(c1,t)⁻¹`). **Measured 2.16 ms big / 12.2 ms little — the
  trial-decrypt hot path.** The KEM `Decap` has **no in-function failure branch** (no secret-dependent branch or
  memory access — verified); a wrong key surfaces later as the AEAD/DEM tag mismatch, which must itself be const-time.

## 7. Cost — MEASURED (M-FS1, the REAL BKP scheme; 2026-07-01)
SD-695-class low-end phone (mcl generic-C, **no asm**), big / little core, depth **L=15** (~2 yr hourly), N=200,
`CLOCK_MONOTONIC`. **KATs ALL PASS** (round-trip depth 1/8/15, cross-id isolation, `millerLoopVec`==stepwise-4-pairings,
4-level delegation) → construction functionally correct (round-trip = ground truth).

| op | big core | little core (worst) | note |
|---|---|---|---|
| Encap | 5.29 ms | 31.8 ms | ≈ FoSAM Pixel-6 5.22 ms |
| **Decap — TRIAL-DECRYPT HOT PATH** | **2.16 ms (p99 2.2)** | **12.2 ms (p99 15)** | 4-pairing `millerLoopVec`; FoSAM Pixel-6 6.70 ms |
| KeyGen | 0.91 ms | 5.19 ms | per recipient key |
| Delegate (1 level) | 8.29 ms | 47.7 ms | background, per epoch advance |
| **ciphertext** | **192 B (4 G1) — CONSTANT** | — | depth-independent |
| usk-core | 384 B (4 G2) | — | + O(ℓ) G2 delegation state on-device |

**Honesty:** the **Decap headline is exact** — its hot path has no secret-scalar mul (only `millerLoopVec`+`finalExp`+
negation), so it is byte-for-byte identical in a constant-time build. **Encap/KeyGen/Delegate use non-CT
`G1::mul`/`G2::mul` over secret scalars → those three are slightly *optimistic lower bounds* vs a hardened (`mulCT`)
build.** **Size budget re-derived for BKP:** ct 192 B + ML-KEM-768 1088 B ≈ **1.28 KB** < 1.8 KB; with a ~2×
byte-uniform encoding on the 192 B G1 part → ~1.47 KB, still fits. Binding constraint = **Decap × inbound-flood
rate** (one decap per new blob, seen-set-gated) → fine within a ~10 s mesh cycle. Formal B4 pass threshold still
TBD-pending the B2 field-airtime anchor.

## 8. Security obligations & implementation hazards (→ B1 audit list)
1. **Key-privacy / pseudorandom-ct proof under SXDH (the core gap — gates "anonymous without AHIBKEM").** Prove
   `ct=([r]₁,[ra]₁,[r·Z_id]₁)` is computationally indistinguishable from **4 uniform G1 elements**, given `mpk`
   (all G1) + many other ciphertexts, **multi-instance**, reducing to DDH/U₁-MDDH in G1 — this yields
   recipient-anonymity + cross-ct unlinkability + id/depth privacy at once (§2.1). **New work:** BKP proved
   IND-CPA, *not* key-privacy. PLUS: enforce the **"only public G2 element is `P2`" invariant** across all
   delegation/FS code (if any `[a]₂/[Z_i]₂/[b]₂/d̄ᵢ/Ēᵢ` ever leaks to G2, or `dk` leaves the device, the linking
   test fires and anonymity collapses), and prove the **CCA / sealed-blob wrapper** is anonymous too (uniform vk,
   no recipient tag, constant length, fresh `r`).
2. **No reference BKP on a raw C pairing lib exists** — the M-FS1 mcl code is **new crypto code** (the affine-MAC
   HIBE *and* the pseudorandomness anonymity rests on). The single biggest B1 surface. (FoSAM's Rust code is
   unreleased / not mcl.) Spec-fidelity was adversarially traced (decap telescopes to `r·z0`; delegation correct
   at all depths); KATs are ground truth — but a formal audit is still owed.
3. **Constant-time:** the M-FS1 code uses non-CT `G1::mul`/`G2::mul` for secret scalars (`a,b,x_i,Y_i,r,s,s'`) —
   port to `mclBnG1_mulCT`/`mclBnG2_mulCT` for production (Encap/KeyGen/Delegate). **Decap's hot path has no
   secret-scalar mul → already CT-safe** (verified). Keep the trial-decap failure (AEAD tag check) const-time.
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
7. **M-FS1 bugs found by adversarial verification + FIXED (pre-audit):** (a) **zero-identity components rejected**
   (`id_j≠0`) — else the level term vanishes and a parent key decaps a child ciphertext (id collision); (b)
   **`Delegate` guarded `p<L`** — was an out-of-bounds read of `udk[L+1]` if delegating from a full-depth key.
   KATs re-pass after both fixes. (Harness never tripped either — ids are hashed; bench delegates `L-1→L`.)

## 9. Build plan (milestones)
1. **M-FS1 — DONE (2026-07-01).** BKP HIBKEM Setup/KeyGen/Encap/Decap/Delegate on mcl + KATs (all pass); real
   scheme benchmarked on the low-end phone (§7); construction derived + adversarially verified; 2 pre-audit bugs
   fixed; private-`dk` anonymity established (pending the §2.1/§8.1 proof). Code: `spike`/`fsbench/bkp_hibe.cpp`.
2. **M-FS2 (next):** CHK binary time-tree (epoch from `creation_ts`, smooth Δt/2 rollover, node erase) +
   **constant-time `mulCT` port** + **byte-uniform wire encoding** (Elligator-class, §8.3b) + a pairing-free Encap
   (precomputed `e(P1,P2)`); property tests incl. an anonymity self-test (ct indistinguishable across keys).
3. **M-FS3:** StrongBox key-wrapping + crypto-erase; **measure erase latency + endurance** (closes the last B4
   on-device unknown).
4. **M-FS4:** X-Wing integration (FS classical leg + static ML-KEM, committing AEAD w/ epoch-AAD) behind a flag;
   flag-day envelope-size handling; FS stays **OFF by default** until B1.
5. **Gate:** B1 audit of the BKP-on-mcl code + the key-privacy proof + erasure guarantee → only then FS-on ships.

## 10. Honest status line
**M-FS1 DONE:** the BKP anonymous-HIBE FS-KEM is **implemented on mcl, KAT-correct, and benchmarked on real
low-end hardware** — Decap **2.16 ms big / 12.2 ms little** (the trial-decrypt hot path), ciphertext **192 B
constant**, corroborated by FoSAM; construction pinned by a derive+adversarially-verify workflow; 2 pre-audit bugs
fixed. The size budget now **fits** (ct 192 B + ML-KEM ≈ 1.28 KB < 1.8 KB). FS is still **NOT shipped, NOT
audited.** Remaining before FS-on: **M-FS2** (CHK time-tree + constant-time `mulCT` + byte-uniform wire encoding —
still OPEN), **M-FS3** (StrongBox crypto-erase — the deletion FS rests on, still **unmeasured**), **M-FS4** (hybrid
integration + CCA/committing wrapper), the **SXDH key-privacy proof + the "only public G2 is P2" invariant**
(§2.1/§8.1), the **boot-reset gap** (§4), and **B1 audit**. v1 remains **static key + FS DEFERRED + in-app
disclosure**.
