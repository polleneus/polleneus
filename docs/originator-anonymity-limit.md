# polleneus — The originator-anonymity limit (impossibility + the re-randomization gate)

**Status:** analysis / honest-limit record · **Created:** 2026-06-27
**Parent:** [polleneus v0.5 §10](superpowers/specs/2026-06-25-polleneus-design.md#10-anonymity-engineering--measured-not-assumed)
· **Feeds:** release-blockers B2/B3.

> **One-line result.** *You cannot hide the originator of an exact-byte, single-root flood from an
> observer who sees all of space.* This is not an engineering gap we expect to close — it is a property
> of undirected flooding, confirmed by our own measurements, by an independent 4-expert review, and by
> two adversarial verification passes. The escapes that exist are bounded and costly, and the most
> promising one is **blocked by our post-quantum crypto choice** (the "re-randomization gate," below).

## 1. What we are trying to hide

Two byte-uniform sealed blobs are indistinguishable on the wire; crypto hides *content* and *recipient*
(both strong — recipient anonymity comes free from the flood: everyone receives everything). The open
problem is **sender/originator anonymity**: hide *which device/position injected* a given message.

## 2. The impossibility (why blurring can never work)

A message must physically spread *outward from where it was first injected*. A passive **receiver grid**
recording **first-sighting times across space** sees ripples from a stone dropped in a pond; inverting
that gradient (rumor-centrality / Pinto–Thiran–Vetterli sparse-observer MLE) points to the centre — the
originator. Two conservation laws make this inescapable for our system (both independently derived by the
external review and verified):

- **Law 1 — Dedup ⇒ observability.** For the flood to *terminate*, every relay must compute "these two
  sightings are the same message" from observable data, consistently. Our adversary is an
  indistinguishable participant — it computes the same relation, groups all sightings of the target,
  reconstructs the wavefront, and recovers the apex. *Any terminating byte-uniform flood has an
  adversary-reconstructible source.*
- **Law 2 — Multi-root dilemma.** Trying to make the message appear at many places at once is
  self-defeating: identical bits at m nodes were *copied* there, and a copy-tree has a root; hide that
  root by re-randomizing and the bits differ, so the m copies become *independent decoys* — exactly the
  null we measured. Either a traceable apex, or it collapses to the decoy-null. No third branch.

**This explains all three of our measured null results in one stroke** (Poisson mixing, the
receive-before-originate gate, the venue-wide decoy floor): every one of them tried to *blur the
wavefront* with a rule every node applies symmetrically — and a symmetric local rule cannot bend a
gradient, while decoys are separable because the adversary conditions on the *target blob's exact bits*.

**Measured ground truth (sim, upper bounds on anonymity):** single-message originator rank-1 ≈ **29 %**
(~35× the 1/N floor); multi-session fused rank-1 climbs **0.09 → 0.72** over K = 1…16 (a persistent
author is far worse off than a one-off sender).

## 3. The only escapes — and what each costs

The proofs forbid *removing* or *blurring* the apex. They leave exactly three doors, each with a price:

| Escape | Idea | Verdict for polleneus |
|---|---|---|
| **Re-randomize the bytes** | Make each hop look different so the adversary can't link sightings into one wavefront (universal re-encryption; the "stem/bloom" relocation and the "FoG" label-erasure both rely on this) | **BLOCKED by our crypto — see §4.** This was the most promising new direction; it does not work on our post-quantum stack. |
| **No root at all (DC-net)** | The message is *born* from the XOR of every participant's share; no device is ever the root. Information-theoretically perfect, intersection-immune | **Provable but O(N) airtime** — every phone broadcasts a share every round. Viable only for **small, high-stakes groups / long epochs / low throughput**, never stadium-scale low-latency. |
| **Drown / move the root with cover** | Constant-rate cover traffic (the "chamber": every phone always emits, real or dummy) or a relocating proxy hop | **Bounded, conditional.** Helps a *single* message against a *blob-blind* adversary (§5); does **not** help a persistent, fingerprinted sender without near-constant venue-wide cover → straight into the airtime wall. |

## 4. The re-randomization gate (the decisive new finding)

The strongest external proposals (relocating "stem," "fog-of-gossip" label-erasure) all rest on
**universal re-encryption**: re-randomize a ciphertext so an observer cannot link the before/after, while
the recipient still decrypts. Verified to work **as a primitive** (Golle–Jakobsson–Juels–Syverson, under
DDH). **But it does not compose with our design:**

- Our payload uses an **X-Wing post-quantum hybrid KEM (X25519 + ML-KEM-768) + AEAD** (§5). Universal
  re-encryption only re-randomizes a small **classical** group element. The **symmetric AEAD payload
  (~kilobyte) stays byte-identical** across re-randomizations.
- So a spatial grid simply follows the **stable payload bytes** hop-to-hop and walks the trail back —
  the back-tracking "branching factor" collapses to 1 (a thread), reproducing the decoy-null. The
  external review's own falsifier names this exact case ("re-enable byte-linking and you reproduce your
  null"); **our crypto *is* that case.**

**Consequence — a genuine, board-level tradeoff:** there is a direct tension between **post-quantum
confidentiality** and **any re-randomization-based path to sender anonymity**. Closing the gate requires
one of:
1. **Drop post-quantum** and use a fully re-randomizable (classical ElGamal-style) encryption over the
   *whole* payload — surrenders PQ security, and re-randomizing kilobytes per hop is itself costly; or
2. **Efficient post-quantum re-randomizable encryption** — an **open cryptographic research problem**, not
   something to build on today.

Until one of those exists, the re-randomization family (stem, FoG) is **not a near-term mechanism** for
polleneus. Record it as a *gated research direction*, not a roadmap build.

## 5. What survives — and the one cheap experiment worth running

Against a **blob-identity-known** adversary (it already knows which byte-uniform blob is the target — e.g.
a colluding recipient, or external correlation), nothing network-layer helps: it localizes the target's
own wavefront regardless of cover (this is *why* the decoy floor and the mixed-graph denominator both
came out null).

Against a **blob-identity-blind, timing-aware** adversary (it knows roughly *when* the target was sent but
**cannot tell which of the byte-uniform blobs is the target**), the picture is different and is exactly
where the "chamber" / constant-rate-cover intuition has teeth: the originator hides among **everyone who
originated a blob in the timing window**, so single-message rank-1 → ~**1/A(W)**, where A(W) = distinct
originators (real *or* dummy) in the window. This is **not** the decoy-floor (those were the same blob's
wavefront); it is about whether the adversary can even *pick the target blob*. **§6 measures it.**

The honest boundary, stated plainly for the app: *a one-off message in a busy venue can get meaningful
cover (≈1/concurrent-originators) — but that protection evaporates the moment the adversary can identify
the target blob, and it does not protect a persistent, device-fingerprinted sender.*

## 6. Experiment: concurrent-origination ("free cover") — see results

We tested the §5 claim in the simulator (venue n = 120, coverage f = 0.7, reps = 2; reproduce:
`origination_cover_sweep`): sweep the number of concurrent originations in the window and measure the
**blob-known** rank-1 (strong adversary, scored on the target blob's own hearings) vs the **blob-blind**
floor 1/A(W) (A(W) = distinct originators in the window).

| concurrent originations | blob-**known** rank-1 (strong adv) | A(W) distinct originators | blob-**blind** floor = 1/A(W) |
|---|---|---|---|
| 4  | 0.00\* | 4    | 0.250 |
| 12 | **0.29** | 10.5 | 0.095 |
| 30 | 0.22  | 27   | 0.037 |
| 80 | 0.22  | 56   | 0.018 |

\*small-sample noise (8 samples). **Verified reading:**
- **The blob-known adversary is flat at ~0.22–0.29** regardless of how busy the venue is — exactly our
  headline ~29 %. **Concurrent origination / the "chamber" buys nothing against an adversary that can
  identify the target blob.** (This is the same structural reason the decoy floor was null: it scores the
  target's own wavefront.)
- **The blob-blind floor falls steeply toward 1/N** (0.25 → 0.095 → 0.037 → 0.018) as concurrent
  originations rise — A(W) grows ~linearly with the count until it saturates toward N. So the
  "chamber"/busy-venue idea gives **genuine free single-message cover ≈ 1/(concurrent originators)** —
  **but only against an adversary that cannot tell which byte-uniform blob is the target.**

**Caveat (honest):** 1/A(W) is the *no-spatial-prior* floor. A blob-blind adversary that targets a
*region* (surveilling a specific area) narrows the set to A(W, region) ≪ A(W), and a blob-**known**
adversary (colluding recipient, or external correlation) gets nothing from cover at all. And none of this
helps a **persistent, device-fingerprinted** sender — that is the multi-session attack, unaffected here.

**So the chamber works exactly where the threat is weakest and fails exactly where it is strongest** — a
real but narrow win, honestly bounded.

## 7. Honest credits & status

This limit and the re-randomization gate were sharpened by an independent 4-expert review (`docs/riddle/`)
and two adversarial verification passes. The experts converged on the correct theory; the gate is the
reason their strongest constructions do not transfer to *our* post-quantum system. **No silver bullet
exists for our configured adversary.** The honest product posture (carried to B3): *strong recipient
anonymity and content secrecy; single-message sender cover that is bounded and blob-blind-conditional;
no cheap protection for a persistent, fingerprinted sender; perfect sender anonymity only via a
small-group DC-net or a post-quantum crypto advance we do not yet have.*
