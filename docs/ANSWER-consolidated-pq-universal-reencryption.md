<!-- IMPORTED from the crypto research workspace; authoritative crypto result, preserved here for the repo record.
     OUR VERIFICATION NOTE (3-lens adversarial pass): crypto existence + cost claims are primary-accurate and the
     practical conclusion (retire re-randomization; pursue DC-net/cover) is correct. ONE scope-correction: the
     "retires the WHOLE re-randomization family" / "even free URE wouldn't help, period" framing is OVERSTATED —
     Law 1 retires keyless URE *in the flood*; the single-path *stem* survives Law 1 and is retired SEPARATELY by
     multi-session PHY fingerprinting (already-known), not by Law 1. The scope-correct statement is in
     originator-anonymity-limit.md §4. Also: the "genus-theory-fragile at real CSIDH params" cite (§3) is loose —
     CSV 2020/151 says CSIDH (odd class number) is NOT genus-theory-affected. -->

# The answer — efficient post-quantum universal re-encryption, consolidated & primary-verified

**Status:** AUTHORITATIVE consolidated answer · supersedes the two reversed claims (see §6) · **Created:** 2026-06-27
**Supersedes/links:** [plan](pq-universal-reencryption-research-plan.md) · [Stage 0 findings](stage0-findings-prior-art-and-barrier.md) · [Stage 0 verdict](stage0-verdict-and-go-no-go.md) · [Path B/isogeny](stage1-probe-keyless-csidh-obstruction.md) · [Path D/theorem (refuted)](stage1-pathD-impossibility-theorem-skeleton.md) · [Path A/lattice](stage1-probe-pathA-bounded-L-lattice.md) · gate: [originator-anonymity-limit.md](originator-anonymity-limit.md)

> **One line.** An efficient post-quantum keyless universal re-encryption **does not exist today** (it is provably
> *expensive*, the expense *caused by the keyless requirement itself*) — **AND, more fundamentally, even a free perfect one
> would not help polleneus**, because universal re-encryption is a **mixnet primitive that is architecturally incompatible
> with a terminating flood** (it destroys the dedup a flood needs — the gate doc's own **Law 1**). So the re-randomization
> gate is **not a crypto gate a PQ advance opens; it is a Law-1 gate no crypto opens** for a flood. This **confirms and
> deepens the gate doc's conclusion.**

> **The deepest finding (added after the tiny-payload swing — primary-sourced, see §7.5).** Chasing "can we build PQ URE"
> was, at the system level, chasing the wrong question. A terminating flood must **dedup** (recognize duplicate copies →
> a stable linkable identifier); URE makes copies **unlinkable** → it **destroys dedup**. You can have unlinkable hops
> *or* a terminating flood, not both. So even a perfect, free PQ URE is the **wrong tool** for polleneus. The crypto cost
> (below) is real, but it was never the binding constraint.

## 1. The question
A PQ analog of GJJS universal re-encryption meeting 7 properties: ① keyless re-randomization (no recipient key/token at
the relay), ② whole-ciphertext computational unlinkability over L hops, ③ PQ IND-CPA, ④ PQ key-privacy, ⑤ robust
trial-decryption, ⑥ uniform fixed-size, ⑦ depth-L. "How close, and what's the unavoidable cost?"

## 2. The answer
- **Existence — YES (settled).** A keyless PQ universal re-encryption exists: group-action exponential-ElGamal
  (`Enc(β)=(g_b⋆x₀, tᵝg_b g_a⋆x₀)`, keyless `ReRand=(r⋆c₁,r⋆c₂)`, decrypt by reading the offset `tᵝ`). Keyless, perfect,
  correct, IND-CPA in the generic group-action model. **No impossibility theorem holds** (§6).
- **Efficiency — NO (the real limit).** Every known keyless route is heavy, and the **keyless requirement is the direct
  cause**: classical GJJS is cheap only because group exponentiation is **noiseless and has division**; neither PQ
  substrate has a *keyless noiseless* re-randomization.

## 3. The two routes and their costs (primary-verified)

| Route | Keyless construction? | Cost — and why the keyless requirement forces it |
|---|---|---|
| **Lattice** (Singh-style carried E(0), RLWE) | yes | **Modulus exponential in L → MB-scale**, *worse* than even token-PRE's regime B. Keyless relay must re-randomize **recipient-specific carried zero-material by self-combination** ⇒ noise `~(√m·σ_R)^L`. The *additive* (efficient) rate needs the re-encryption **key** to inject fresh bounded noise — not available keyless. [ePrint 2024/681 Tables 2–3: ~60 bits/hop, 6.5 MB@13 hops; ~16–63 MB@L=32 for strong unlinkability; ~33 KB only at weak ν≈20. Primary-PDF.] |
| **Isogeny / group action** (exponential-ElGamal) | yes | **`O(log λ)` payload bits per group element** (no division ⇒ message recovered only by brute-forcing a small offset) ⇒ a kilobyte ≈ thousands of elements ⇒ **MB ciphertexts + ~hours of CSIDH evals to decrypt**. PQ-IND-CPA **cannot be proven in the generic model** (QGGAM breaks GA-DLOG) and is **genus-theory-fragile** at real CSIDH params. [MZ 2022/1135, Duman 2023/186, CSV Crypto 2020. Primary/HIGH.] |
| **Token-based** (TOGA-UE isogeny; 2024/681 lattice PRE) | **no — needs a key-derived token** | Efficient (fixed-size/unbounded-depth isogeny; additive ~60 bits/hop lattice) — but the token is exactly the "division"/fresh-noise the relay would need; **wrong model** for polleneus's no-coordination relay. |
| **Classical GJJS (DDH)** | yes | Cheap, all 7 — but **Shor-broken**. |

Multi-hop unlinkability for bounded L is itself fine (Rényi/KL flooding, ~2.5–4.6 bits loss at L=32) — but proven only
for the token scheme; the keyless cost above dominates regardless.

## 4. The unified structural reason (the "must pay ≥ X")
**Keyless re-randomization with bounded cost requires a *noiseless, division-like* public operation on ciphertexts.**
- Classical groups have it (exponentiation/division) ⇒ GJJS is cheap — but DDH is Shor-broken.
- **Lattices** have no noiseless re-randomization: keyless ⇒ re-combine carried recipient-specific noise ⇒ multiplicative
  growth ⇒ exponential modulus. Fresh-noise injection needs the key.
- **Group actions** have no division: keyless re-randomization works, but decryption can only recover a *tiny offset* by
  brute force ⇒ `O(log λ)` bits/element.
So the unavoidable cost is: **keyless PQ re-randomization pays either exponential modulus / MB ciphertexts (lattice) or
`O(log λ)` bits-per-element + slow decryption (isogeny)** — because the noiseless keyless re-randomization that makes
classical GJJS cheap has **no efficient post-quantum analogue**. This is a *cost lower bound by structural exhaustion*,
not a proven theorem — but it is primary-anchored and consistent across both substrates.

## 5. What is primary-verified vs inferred
- **Primary-PDF (HIGH):** lattice rate ~60 bits/hop, 6.5 MB@13 hops, weak-vs-strong ν tradeoff (2024/681); Rényi/KL
  flooding losses (2022/816, 2015/483); Singh 2014 keyless single-hop multiplicative mechanism; MZ CDH≡vectorization
  average-case (2022/1135); GGAM operation set + classical GA-DDH hardness (2023/186); TOGA-UE token = `k_{e+1}k_e⁻¹`
  (2022/739); FO ciphertext rigidity (2021/708).
- **Inference (MED-HIGH):** the L-fold multiplicative blow-up of Singh's carried material (mechanism primary, L-extrapolation inferred); "no published keyless multi-hop lattice scheme" (negative search); the structural cost-bound of §4 (exhaustion, not a theorem).

## 6. Corrections — two confident claims I made were refuted (by primary-sourced red-teams)
1. **"Keyless CSIDH URE is structurally walled" — WRONG.** A keyless construction exists (exponential-ElGamal, §2). The
   true limit is *payload efficiency* (`O(log λ)` bits/element), not a wall. My "can't decrypt" conflated recovering the
   message (the offset, easy for small messages) with stripping the randomness (which cancels).
2. **"Perfect keyless PQ re-randomization is impossible (GGAM theorem)" — WRONG.** Refuted by the §2 counterexample;
   Montgomery–Zhandry needs an *average-case* CDH solver, which the recipient's own key does not provide. The salvageable
   result is the **payload-efficiency cost bound** of §4, not an impossibility.

## 7. Verdict for polleneus (B2/B3)
**Unchanged from the gate doc, now precisely grounded: keep re-randomization (stem/FoG) as a *gated research direction*,
do not build on it.** The reason is sharpened twice over: (i) the X-Wing+AEAD stack is *structurally* non-re-randomizable
(FO produces a unique ciphertext per (m,pk)); (ii) even a purpose-built keyless PQ scheme is **provably too expensive**
(MB-scale + slow, on every route) for stadium-scale kilobyte flooding — and the keyless requirement *is* the cost. The
honest product posture in gate-doc §7 stands.

## 7.5 The architectural mismatch — why even free PQ URE wouldn't help (primary-sourced)

The tiny-payload swing (Path 3) tried the one regime the isogeny route doesn't obviously exclude — a few-byte *signalling* token. Two findings, the second decisive:

- **The tiny-payload primitive is real but weak.** A keyless group-action exponential-ElGamal (`t = single small prime`,
  message = small offset `tᵝ`, brute-forced at decryption) gives keyless + IND-CPA/key-private/unlinkable (from GA-DDH,
  which **survives** in odd-order CSIDH — Castryck–Sotáková–Vercauteren 2020/151 say their attack "does not impact
  CSIDH") + **unbounded depth**. But the "`√M` cheap decryption" is **refuted**: the giant-step needs the (infeasible at
  PQ params) class-group structure, so decryption is an **O(M) walk** (~28–200 ms/step) → **~1 byte only** (seconds to
  decode; 2 bytes = minutes–hours; 3 bytes = days), and it is **dominated by SiGamal** (Moriya–Onuki–Takagi 2020/613,
  which carries more payload and decrypts exactly via Pohlig–Hellman). *Niche at best.*

- **URE is the wrong primitive for a flood — the binding constraint.** Even a *perfect, free* PQ URE would not deliver
  originator anonymity for polleneus:
  - **B1:** a few-byte token does **not** break the trail of the byte-stable ~kilobyte AEAD blob — the observer trails
    the stable bulk and ignores the token.
  - **B2:** the token can't be a per-hop rekeying seed (it is *constant* under re-randomization and only the key-holder
    reads it), nor a relay-routing label (relays have no key) — its only honest use is an **unlinkable presence/rendezvous
    tag** (the RFID-privacy niche: Ateniese–Camenisch–de Medeiros, CCS 2005), which can only *bootstrap* a **separately**
    protected bulk channel.
  - **The systems killer:** a flood needs **seen-message suppression (dedup)** to terminate; dedup requires a stable,
    linkable identifier; URE deliberately makes copies **unlinkable** → it **destroys dedup**. This is the gate doc's
    **Law 1** ("Dedup ⇒ observability") applied to the re-randomization escape itself. **URE is a mixnet primitive**
    (single-path, batch-and-permute) — architecturally wrong for a flood.

**Consequence — re-frame gate-doc §4.** The re-randomization gate was presented as "blocked by our PQ-crypto choice; an
efficient PQ re-randomizable encryption would unblock it." The honest, primary-sourced conclusion: **an efficient PQ
version would NOT unblock it.** The blocker is not the crypto — it is Law 1 (re-randomization ⊥ dedup ⊥ a terminating
flood). The correct building blocks for bulk originator anonymity are **per-hop keyed re-encryption (layered/onion** —
isogeny onion routing already exists, arXiv 2510.01464**)** or a **DC-net** (the gate doc's §3 surviving escapes), not
universal re-encryption. *This retires the re-randomization family as a research direction for polleneus, not merely as a
near-term build.*

## 8. What remains genuinely open
- **For polleneus: nothing in the re-randomization family.** §7.5 (Law 1) retires it — *no* PQ-crypto advance opens the
  gate for a flood. The live directions are the gate doc's other escapes: **DC-net** (small high-stakes groups) and
  **cover traffic** (bounded, blob-blind), plus **per-hop keyed onion** if the flood model can bend.
- **As a general cryptography question (decoupled from polleneus):** *efficient* keyless PQ universal re-encryption
  (whole-payload, fast, secure at real params) remains **open** — existence and cost are now characterized, efficiency is
  the gap; and a **formal cost lower bound** (a *correctness/efficiency* bound for large message spaces, not a PQ-IND-CPA
  impossibility) is promising but unproven. These would matter for a **mixnet**, not a flood.
- **Tiny-payload signalling — RESOLVED (this swing):** the few-byte isogeny primitive works but is ~1 byte, slow at PQ
  params, dominated by SiGamal, and — decisively — **does not address the bulk-trail problem** (§7.5). Not a path for
  polleneus; at most an unlinkable presence tag bootstrapping a separately-protected channel.
