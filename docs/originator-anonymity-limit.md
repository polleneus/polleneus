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
| **Re-randomize the bytes** | Make each hop look different so the adversary can't link sightings into one wavefront (universal re-encryption; the "stem/bloom" relocation and the "FoG" label-erasure both rely on this) | **BLOCKED on two independent grounds (§4):** (i) crypto byte-stability on our PQ stack, and (ii) **for the flood, Law 1** — re-encryption destroys the dedup a terminating flood needs, so **even a free, perfect PQ universal re-encryption would not open this for the flood.** The single-path *stem* survives Law 1 but is killed separately by multi-session PHY fingerprinting (§5). |
| **No root at all (DC-net)** | The message is *born* from the XOR of every participant's share; no device is ever the root. Information-theoretically perfect, intersection-immune | **Provable but O(N) airtime** — every phone broadcasts a share every round. Viable only for **small, high-stakes groups / long epochs / low throughput**, never stadium-scale low-latency. |
| **Drown / move the root with cover** | Constant-rate cover traffic (the "chamber": every phone always emits, real or dummy) or a relocating proxy hop | **Bounded, conditional.** Helps a *single* message against a *blob-blind* adversary (§5); does **not** help a persistent, fingerprinted sender without near-constant venue-wide cover → straight into the airtime wall. |

## 4. The re-randomization gate — NOT a single crypto gate (corrected; see the consolidated answer)

The strongest external proposals (relocating "stem," "fog-of-gossip" label-erasure) all rest on
**universal re-encryption (URE)**: re-randomize a ciphertext so an observer cannot link before/after, while
the recipient still decrypts (Golle–Jakobsson–Juels–Syverson, under DDH). A focused crypto research effort
([consolidated answer](ANSWER-consolidated-pq-universal-reencryption.md), independently verified) settled
the picture — and it is **deeper than "blocked by our PQ crypto."** Three distinct barriers, not one:

- **(a) Crypto byte-stability (our deployed stack).** Our payload is an **X-Wing PQ hybrid KEM
  (X25519+ML-KEM-768) + AEAD** (§5). The FO transform makes the ciphertext *unique per (message, key)* —
  unre-randomizable even *with* the public key — and the AEAD body stays byte-identical, so a spatial grid
  follows the stable bytes and walks the trail back.
- **(b) Law 1 kills URE *in the flood* — even a free, perfect PQ URE would NOT help.** The decisive
  finding. A terminating flood must **dedup** on a stable, public, proof-bound message-ID, and our
  airtime-winning set-reconciliation (§8) depends on stable global IDs. Re-randomizing every flood hop
  either (i) preserves the ID — which *is* the linking tag the grid groups on — or (ii) re-randomizes it,
  so duplicates never reconcile, the flood never terminates, and the airtime budget collapses. URE is a
  *mixnet (single-path) primitive*, architecturally wrong for a flood. **No PQ-crypto advance opens this.**
- **(c) The single-path *stem* is a different case.** Law 1 does *not* apply to the stem (single-path, no
  dedup), so a free URE *would* give it single-message disk-anonymity. But the stem dies **separately**, to
  the already-known weakness (§5): the originator's own radio emits the first stem hop, so PHY
  fingerprinting + multi-session intersection re-identify a persistent sender regardless of byte-
  unlinkability. And for the stem you don't even *need* keyless URE — the originator picks the path and can
  use **keyed onion** encryption (PQ-buildable today). Keyless URE is needed only where it fails (the flood).

**Crypto status (general, decoupled from polleneus):** keyless PQ URE **exists** but is **provably
expensive** — group-action exponential-ElGamal works but carries only `O(log λ)` payload bits/element
(MB ciphertexts + slow decryption for a kilobyte); the keyless lattice route forces an exponential modulus
(MB-scale). The structural reason: classical GJJS is cheap only because group exponentiation is *noiseless
and has division*, and **no post-quantum substrate has a cheap keyless re-randomization** (lattices have
noise growth; group actions have no division).

**Bottom line (corrected):** the re-randomization family is retired for polleneus — but **not** because we
await a crypto advance. The flood is closed by **Law 1** (no crypto opens it); the stem by **multi-session
PHY fingerprinting**; both also by byte-stability today. Earlier drafts that framed this as *"an efficient
PQ re-randomizable encryption would unblock the gate"* were **wrong** and are corrected here. The surviving
escapes are §3's **DC-net** (small groups), **cover** (single-message, blob-blind), and — if the flood model
is ever allowed to bend — a **keyed-onion stem** (not keyless URE).

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

This limit and the re-randomization gate were sharpened by an independent 4-expert review (`docs/riddle/`),
a focused crypto research effort ([consolidated answer](ANSWER-consolidated-pq-universal-reencryption.md)),
and several adversarial verification passes. The experts converged on the correct theory. **No silver
bullet exists for our configured adversary** — and, per §4, the re-randomization escape is closed
*architecturally* (Law 1 for the flood; PHY fingerprinting for the stem), **not** merely pending a crypto
advance: a free, perfect PQ re-randomizable encryption would **not** open it for the flood. The honest
product posture (carried to B3): *strong recipient anonymity and content secrecy; single-message sender
cover that is bounded and blob-blind-conditional; no cheap protection for a persistent, fingerprinted
sender; perfect sender anonymity only via a small-group DC-net (the flood layer cannot be made
sender-anonymous by any re-randomization scheme).*

## 8. The reframe — does finding the origin even matter? (CTO decision, 2026-06-28)

After establishing that originator-anonymity is impossible for a flood (and that no crypto opens it,
§4), the right move is not a cleverer hack — it is to **ask what the leak actually costs**, and accept
the answer.

**What localizing the origin gets the adversary: exactly one bit — "this device transmitted a message."**
Not the content (sealed, E2E). Not the recipient (everyone receives everything). For the mission that
defines polleneus — coordinating locally when infrastructure is down — the dangerous facts are *what* was
said and *who* it was said to, and **both are protected.** "Someone near the south gate transmitted
something" is usually operationally useless.

**And that one bit is mostly already public.** Every phone relays others' blobs (and may emit cover), so
"you transmitted" ≈ "you are running the app" — a **membership** signal that is unavoidable for *any*
radio tool and that we already disclose. The honest, achievable goal is therefore **"originating blends
into participating,"** not "hide the originator":
- a **single** message blends into concurrent traffic against a blob-blind adversary (§5/§6, ~1/A(W));
- **content + recipient** — the crown jewels — stay protected unconditionally.

**The one genuinely-exposed case, accepted and disclosed:** a *persistent, specifically-targeted,
device-fingerprinted* author is pinned by multi-session intersection (B2). polleneus does **not** protect
that person, and the copy says so — the same limit every mesh tool has.

**Consequence for the roadmap:** originator-anonymity is **retired as a blocker.** It is a *bounded,
disclosed property* (B3), not an engineering gate — and the re-randomization research that chased it is
**parked as decoupled general cryptography** (it cannot help a flood; §4 / Law 1). We stop spending
project effort on hiding the originator and return to making the app work when things go down (P3–P6).
