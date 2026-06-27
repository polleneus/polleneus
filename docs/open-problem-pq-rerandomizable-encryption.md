# Open problem: Post-Quantum Universal Re-encryption (the "re-randomization gate")

**For:** cryptographers. **Self-contained** — everything needed to attack the problem is here.
**Origin:** this is the single primitive whose absence blocks sender-anonymity in an offline mesh
messenger (polleneus). A systems write-up of *why* it's needed is in §6; you do not need it to work on §3–§5.

## 1. One-line ask

Build — or prove must-be-expensive — an **efficient, post-quantum, IND-CPA + key-private public-key
encryption scheme whose ciphertexts can be re-randomized by *any third party without the recipient's
public key*, such that re-randomization is *unlinkable* (even to an observer who sees every hop of a
chain) and the legitimate recipient still recovers the message.** Classical "universal re-encryption"
(ElGamal; GJJS 2004) does exactly this. A **lattice** universal re-encryption has been *attempted*
(Singh–Rangan 2014, on the GHV cryptosystem), but — to our knowledge — **no construction meets the full
deployable bar of §3** (efficient, whole-payload, chain-unlinkable, key-private, uniform fixed-size,
depth-L on a phone). Closing that gap, or showing it cannot be closed cheaply, is the problem.

## 2. The primitive — syntax

A scheme `PQ-URE = (KeyGen, Enc, ReRand, Dec)`:

- `KeyGen(1^λ) → (pk, sk)`
- `Enc(pk, m; r) → c`
- `ReRand(c; r') → c'`  — **takes NO public key.** Any holder of a ciphertext can re-randomize it,
  *without knowing who the recipient is.* (This "universality" is the crux — see §4.)
- `Dec(sk, c) → m` or `⊥`

## 3. Required properties (the full bar)

λ = security parameter; "QPT" = quantum poly-time; "≈c" = computationally indistinguishable to a QPT
distinguisher. **Unless stated otherwise every notion is *computational* and *post-quantum*.**

1. **Correctness under re-randomization, to depth L.** For the true key,
   `Dec(sk, ReRand^k(Enc(pk,m))) = m` with overwhelming probability for all `0 ≤ k ≤ L` (note any
   per-hop failure probability compounds over L). The scheme must support **chained** re-randomization to
   depth **L** (a relay path). Unbounded L is ideal; a stated finite **L (target: L ≳ 30–50)** is
   acceptable — but the achievable L, and what bounds it, **must be quantified.**

2. **Trial-decryption with robustness (SROB).** A recipient does not know which ciphertexts are addressed
   to it; it runs `Dec` with its own `sk`. For a ciphertext not under `pk`, `Dec(sk, ·) = ⊥` with
   overwhelming probability. **This is strong robustness (SROB-CPA), a requirement *independent of*
   key-privacy (3.5)** — and it is in direct tension with the FO **implicit rejection** used by
   ML-KEM/Kyber, which never outputs ⊥ (it returns a pseudorandom key), so naïve trial-decryption never
   detects "not mine." A solution must restore an (anonymity-preserving) ⊥ signal — i.e. plaintext
   redundancy that is itself re-randomized (it must not be a byte-stable marker; see 3.4). (Grubbs–Maram–
   Paterson, EC 2022, is the reference for achieving robustness *and* anonymity in PQ PKE.)

3. **IND-CPA, post-quantum.** Semantic security against a QPT adversary (the reason ElGamal/DDH schemes
   do not qualify).

4. **Re-randomization unlinkability (THE central property).** A QPT adversary **without `sk`**, given a
   ciphertext `c` and a challenge `c*`, cannot tell whether `c* = ReRand(c)` or `c* = Enc(pk, m₀)` for an
   independent **uniformly-chosen** `m₀`: `{c, ReRand(c)} ≈c {c, Enc(pk, m₀)}`. *(Under IND-CPA this is
   equivalent to the standard "ReRand(c) ≈c a fresh `Enc(pk, m)` of the **same** plaintext"; i.e. this is
   ordinary computational rerandomizability — not a new hardness axis. We highlight it because it is the
   property our deployed hybrid fails, not because it is novel.)* The baseline fixes `pk`, so 3.4 gives
   **same-recipient** unlinkability; **cross-recipient** unlinkability is supplied by key-privacy (3.5).
   - **Chain corollary (not a separate axiom):** by a standard hybrid over per-hop 3.4, an adversary
     seeing the *whole* sequence `c₀, c₁=ReRand(c₀), …, c_L` cannot link any pair beyond chance. (Our
     observer is physical and sees every hop — §6.) The genuine difficulty is not the hybrid; it is
     keeping each hop simultaneously ≈-fresh **and** decryptable over L hops at acceptable cost (§4).

5. **Key-privacy / recipient-anonymity (IK-CPA), post-quantum, preserved under ReRand.** Ciphertexts hide
   *which* `pk` they are under, both fresh and after re-randomization. (Grubbs–Maram–Paterson; Maram et al.)

6. **Fixed-size, uniform-looking ciphertexts.** `c` (fresh and re-randomized) is a **fixed-length byte
   string indistinguishable from uniform random bytes** — the post-quantum analogue of an Elligator-
   encoded ciphertext. No headers/tags/structure that survive as a wire fingerprint, and (with 3.4-chain)
   nothing that reveals the hop index / depth.

> **Worked consequence of 3.4 (was a separate "property 7" — it is redundant, so it's a note):** any
> *byte-stable component* across hops is a trivial 3.4 distinguisher (test equality of those bytes). In
> particular a **KEM/DEM hybrid that re-randomizes only the KEM while the symmetric AEAD body stays
> identical is NOT a solution** — it is exactly the distinguisher, and it is the failure that motivates
> this whole problem (§6). A solution must be a *native* re-randomizable PKE over the whole payload, or
> include a re-randomizable DEM.

**Performance / deployment targets.** Plaintext **~256 B up to ~2 KB**. On a **low-end ARM smartphone,
no special hardware**: `ReRand` on the order of **tens of ms/hop**. Ciphertext expansion: be realistic —
PQ-KEM baselines already expand, and re-randomization adds more; a "small constant factor" is the *hope*,
but a scheme that needs (say) 10× at 2 KB should say so, since it changes the systems verdict. **A
quantified cost — or a lower bound (§5) — is itself an acceptable deliverable, not a failure to hit the
ideal.**

**Adversary scope for the *minimum* bar:** the re-randomizer and the observer are **passive / honest-but-
curious**. Active "tagging" attacks (Danezis's breaks of universal-re-encryption mixnets — mark a
ciphertext by multiplying in a known factor and trace it through re-randomizations) are **out of scope
for the minimum**, but an **RCCA-secure / tag-resistant** version is a valued bonus.

## 4. Why it's hard — where known approaches break (attack these)

- **Universality (no-pk re-randomization) in the lattice world — the crux.** Classical URE works because
  an ElGamal ciphertext can carry an encryption of the *identity element* under the recipient's key,
  letting anyone re-randomize via the group homomorphism *without* `pk`. The lattice analogue ("add a
  fresh encryption of zero") is blocked because a fresh LWE encryption of zero needs `b = A·s + e` tied to
  the recipient's secret `s`: **the LWE samples `(A, b)` themselves are the obstacle to producing fresh
  encryption-of-zero material without `pk`.** (For contrast, *with* `pk`, lattice re-encryption is easy and
  even statistical via the Leftover Hash Lemma with only bounded additive noise — the whole difficulty is
  doing it *blindly*.) Singh–Rangan attempt exactly this via GHV's embedded structure + a shared public
  matrix; verifying whether their `ReRand` is truly key-free, and which §3 bars it misses, is the natural
  starting point.
- **Computational vs. statistical re-randomization (don't conflate them).** Property 3.4 is *computational*.
  The ideal is **computational** re-randomization (GJJS-style fresh encryption-of-zero) with **zero noise
  growth and unbounded L**. Only if one pursues a **statistical-flooding** construction (smudge fresh noise
  to swamp the prior ciphertext) does noise growth appear and bound L — and even then the Rényi/Gaussian
  flooding line keeps the modulus polynomial. So **noise growth is a *quantified cost of one strategy*, not
  an a-priori wall.** Whether efficient *computational* PQ re-randomization exists is itself the open
  question; the brief should not steer solvers exclusively toward flooding.
- **Embedded re-randomization material must recursively satisfy 3.6/3.7.** Whatever structure the
  ciphertext carries to enable blind re-randomization must *itself* stay uniform/fixed-size and not become
  a stable label. GJJS gets this for free (group homomorphism); in lattices it is an extra open constraint.
- **Whole-payload, not a single element (3.4 + the §3 note).** Re-randomizable PKE is usually defined for
  short messages. Extending genuine per-hop unlinkability to a **whole ~KB payload** — with no stable
  symmetric body — is itself a design problem (native long-message re-randomizable PKE, or a
  re-randomizable AEAD/DEM).
- **Uniform fixed-size encoding (3.6)** of a *re-randomized* lattice ciphertext (the Elligator analogue for
  Module-LWE / NTRU), preserved across hops.

## 5. What counts as a solution (full / partial / impossibility — all valuable)

- **Full:** an efficient `PQ-URE` meeting §3 with a security proof under a standard post-quantum assumption
  (Module-LWE / Ring-LWE / NTRU / …) and concrete parameters at the §3 targets.
- **Partial (very useful) — state the relaxation explicitly:** bounded depth `L` with quantified
  noise/parameter cost; a **shared global public parameter** (common `A`) if that enables universality;
  **semi-universal** (re-randomization needs a short *public re-randomization key* that can be flooded
  venue-wide — *not* the recipient's `pk` — acceptable if it preserves recipient-anonymity); or
  passive-only security with a clear statement of what an active/tagging adversary breaks.
- **Impossibility / lower bound (equally valuable, and a likely outcome):** e.g. *"any PQ scheme with
  no-pk re-randomization + chain-unlinkability + key-privacy requires ciphertext growth / noise ≥ f(L)"*,
  or a black-box separation explaining why the ElGamal trick has no efficient lattice analogue. A rigorous
  "you can't have it cheaply, here's the price" is a deliverable we will act on (state the limit honestly
  and stop chasing it).

## 6. Systems context (why this primitive — read only if useful)

polleneus is an offline Bluetooth-mesh messenger: phones in a crowd blindly **re-share fixed-size,
byte-uniform, recipient-sealed blobs** (pure flooding, no servers, no routing); recipients **trial-
decrypt**. A passive adversary with **receivers spread across the venue** records **first-sighting times**
of each blob and runs epidemic source-localization (Pinto–Thiran–Vetterli) — the spread ripples back to
the originator. We proved and measured that you **cannot hide the source of an exact-byte single-root
flood**: the only escape is to make each relay hop **byte-unlinkable**, so the adversary cannot stitch the
sightings into one wavefront. That is exactly `PQ-URE`: a relay holding a blob (not knowing the recipient)
re-randomizes it before re-sharing; the recipient still decrypts; the physical trail no longer links back.
The catch that motivates the §3 "whole-payload" note: our payload is an **X-Wing hybrid (X25519 +
ML-KEM-768) KEM + AEAD**, and re-randomizing only the KEM leaves the **AEAD body byte-stable**, so the
trail is still walkable.

## 7. Known related work (so you don't reinvent)

**Classical target:**
- **Golle, Jakobsson, Juels, Syverson — "Universal Re-encryption for Mixnets," CT-RSA 2004** — the
  primitive to make post-quantum (ElGamal; DDH; re-randomize without the recipient key).
- **Prabhakaran & Rosulek — Rerandomizable RCCA, CRYPTO 2007**; **Faonio–Fiore et al.** — rerandomizable /
  structure-preserving RCCA (the tag-resistant / active-attack-hardened line; classical).
- **Danezis — "Breaking Four Mix-related Schemes Based on Universal Re-encryption"** — active tagging
  attacks (defines the bonus RCCA requirement).
- **Elligator / Elligator-Squared (Bernstein et al., CCS 2013; Tibouchi, FC 2014)** — uniform ciphertext
  encoding (classical); the analogue needed for 3.6.

**Post-quantum / lattice (the actual frontier):**
- **Singh & Pandu Rangan — "Lattice Based Universal Re-encryption for Mixnet," JISIS 4(1), 2014** — the
  closest prior attempt (on the GHV LWE cryptosystem, with an IND-URe-CPA model). **Check it first:**
  characterize whether its `ReRand` is genuinely key-free and *which* §3 bars it misses (quantified L /
  noise budget, 3.6 uniform fixed-size, whole-KB payload, key-privacy, chain-observer unlinkability,
  GHV-scale efficiency).
- **Lattice mixnets / verifiable shuffles** (Aranha et al., CCS 2023; and PKC 2025 lattice-mixnet work) —
  re-randomize lattice ciphertexts in a shuffle, but **with** the public key and ZK proofs — *not*
  universal; useful machinery, wrong trust model.
- **Key-privacy / anonymity of ML-KEM and lattice KEMs** (Grubbs–Maram–Paterson, EC 2022; Maram et al.) —
  for 3.2 (robustness) **and** 3.5 (key-privacy), and the implicit-rejection obstacle.
- **Noise-flooding / circuit privacy** (Gentry; Brakerski; the Rényi-divergence flooding line) — the
  technique behind, and the cost bound for, the statistical-construction branch of 3.4.
- **Updatable / rerandomizable PKE and "anamorphic" encryption** — adjacent primitives worth surveying.

## 8. The crisp statement

> *Does there exist an efficient post-quantum public-key encryption scheme with no-public-key,
> whole-payload, chain-unlinkable re-randomization — preserving IND-CPA, key-privacy, robust trial-
> decryption, and uniform fixed-size ciphertexts — to depth L ≳ tens of hops on a low-end phone? If not at
> the full bar, how close can one get (which relaxation), and what is the unavoidable cost (a lower bound)?*
