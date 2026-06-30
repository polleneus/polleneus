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
  ciphertexts are **pseudorandom (PR-ID-CPA)** ⇒ semantic security **and** key-privacy in one property. It
  supports hierarchical **delegation** (`HIBE.Del`) → drives the CHK binary time-tree with parent-key erasure.
  Precedent: **FoSAM** (arXiv 2603.12871, KIT 2026) builds exactly this (CHK epoch-tree over BKP on BLS12-381,
  implicit addressing, BLE flooding) with an Android prototype — independent validation of this whole design.
- **Rejected: BBG-HIBE (and the `hohibe` crate).** BBG has constant-size ct + 2-pairing decrypt but is **NOT
  anonymous** — its ciphertext links to the recipient identity (Ducas 2010; Lee–Park–Lee survey). `hohibe`
  exposes delegation but is plain non-anonymous, unaudited BBG → unsuitable for trial-decrypt sealed-sender.
  Making BBG anonymous (Boyen–Waters) costs O(ℓ) ct / O(ℓ²) keys — loses the size win. (Detail: the FS memo's
  original "BBG-HIBE" pick is **superseded by BKP** for the anonymity requirement.)

## 3. Forward secrecy = CHK transform over BKP
Canetti–Halevi–Katz: a HIBE + a binary tree of time periods ⇒ a forward-secure (key-evolving) PKE. The recipient
holds the secret key for the current epoch node + the right-sibling/ancestor nodes needed to *derive forward*; it
**crypto-erases** elapsed nodes so past epochs become undecryptable.
- **Fixed public address** (BKP master/root pk) — senders keep using the OOB-paired address forever (CHK: the
  public key is fixed for the system's lifetime). No new wire field; the **epoch is derived from the blob's
  `creation_ts`** already in the header (byte-uniformity preserved).
- **Epoch** = `floor((creation_ts − genesis) / Δt)`, encoded as the HIBE identity path (binary tree, depth
  `ℓ = ⌈log2(#epochs over TTL)⌉`; ℓ=8 for 1-hour epochs over ≤7 d). Secret key = O(ℓ) node keys.
- **Smooth epoch rollover (adopt, from FoSAM §6.4):** advance every **Δt/2** but retain the *previous* epoch
  key in memory, so a blob sent just before a boundary still decrypts. Cleaner than fine sub-epochs.
- **Guaranteed FS window ≥ TTL (by construction):** the device must read in-flight unexpired mail for the whole
  TTL, so it cannot also have shredded that epoch's key. FS cleans only the trailing edge *beyond* TTL.

## 4. Clock that drives erasure (our conservative posture)
Deletion is driven by a **monotonic, local, hardware-backed boot-clock (FJB; P5 §3)** — **gossiped/network time
may only *lag* deletion, never advance it.** This **diverges deliberately from FoSAM**, which uses gossip-majority
voted time *as* the FS clock: voted time is **Sybil-skewable**, and a forward skew would shred unread keys
(timestamp-flood DoS). We trade some availability for attack-resistance. **OPEN (unsolved, P5 §10.1):** the
boot-reset gap — `CLOCK_BOOTTIME` resets on reboot and can't measure off-time; re-anchoring needs network time
(the very input FJB excludes). Availability-default = refuse to over-advance; disclose the FS-degradation window.

## 5. X-Wing integration (FS on the classical leg only)
The seal stays X-Wing (X25519 + ML-KEM-768), KEM-combiner unchanged. **Replace the static X25519 leg with the
BKP/CHK forward-secure KEM**; **ML-KEM-768 stays static (no FS).** Decaps needs *both* shared secrets, so the blob
is secure if *either* leg holds.
- **CLASSICAL-ONLY HONESTY GUARD (load-bearing).** Classical FS and PQ confidentiality defend **disjoint**
  adversaries. Classical FS protects against a **present-day classical seizer** (erased epoch key + unbroken
  X25519 ⇒ past mail safe). It gives **ZERO** against a **future quantum** seizer (Shor recovers the classical
  secret from public values without touching the evolved key; the static ML-KEM key is also seized). **Never
  claim "post-quantum *and* forward-secret" against one quantum-capable seizing adversary in v1.**
- AEAD stays **key-committing**, with the **epoch label bound in AAD** (period-confusion / partitioning-oracle
  defense; HMAC/CMT, never Poly1305/GMAC bare).

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
| `Encap` | ~1 / ~5–6 ms | pairing-free; matches FoSAM Pixel-6 5.22 ms |
| **`Decap` (TRIAL-DECRYPT HOT PATH)** | **~1.6 / ~9–13 ms** | 1–2 pairings; matches FoSAM Pixel-6 6.70 ms; **× inbound-blob rate = the real budget** |
| `Update`(+erase) | ~tens–~120 ms, once/epoch | FoSAM Pixel-6 ratchet 120 ms; background, not hot |

**Verdict:** well inside any plausible interactive target; the formal B4 threshold stays TBD-pending the B2
field-airtime anchor. The binding constraint is **Decap × inbound-flood rate** (every new blob is trial-decapped
with the current-epoch key — one attempt per blob, gated by the seen-set), not single-op latency.

## 8. Security obligations & implementation hazards (→ B1 audit list)
1. **Replicate FoSAM's cross-instance key-privacy proof.** BKP's native anonymity is *within one master key*; we
   need **PR-HID-CPA ⇒ FS-ANON** across instances (FoSAM §7.2). Do not assume — reprove for our composition.
2. **No reference BKP on a raw C pairing lib exists** — this is **new crypto code** (the affine-MAC HIBE *and*
   the pseudorandomness that anonymity rests on). The single biggest B1 surface. (FoSAM's Rust code is
   unreleased / not mcl.)
3. **Constant-time:** secret-dependent muls via `mclBnG1_mulCT`/`mclBnG2_mulCT` (default `mul` is NOT CT);
   **constant-time/indistinguishable trial-decrypt failure**; **uniform all-G1 ciphertext serialization** (any
   encoding bias breaks pseudorandomness ⇒ breaks anonymity).
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
FS **compute + size feasibility is measured and good**; the **construction is selected and precedented** (BKP +
CHK, per FoSAM). FS is **NOT built, NOT shipped, NOT audited.** v1 remains **static key + FS DEFERRED + in-app
disclosure**. This spec is the green light to *build M-FS1*, nothing more.
