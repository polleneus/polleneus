# polleneus — P1: Pairing & truth-in-labeling UX (honest send/trust states)

**Version:** v0.2 — 2026-06-29 (was v0.1 — 2026-06-27) · **Roadmap:** P1 (*highest-ROI, zero-tradeoff wins* — the UX half)
**Parent design:** [polleneus v0.5 §13](2026-06-25-polleneus-design.md#13-ux--operational-security-truth-in-labeling)
· **Sibling:** [P1 reconciliation](2026-06-27-p1-reconciliation-spec.md).
*v0.2 — pinned the SAS as a quantified security parameter, defined the pairing transcript it binds,
canonical ordering / re-pair / race handling, and the `K_pair`-aware trust-state machine incl. duress
rotation (closes pre-B1 red-team F1, F2, F4, F5, F6, DSA-04; §5.1–5.6). Also reconciled the deletion-claim
UX copy to P5 §3 — computational & construction-conditional, not "exact / probability-1" (SEAL-02).*

> ⚠️ **SPEC ONLY — no client is built here.** This is client-surface design. Per release-blocker **B1**
> (no installable build before an independent security audit) and the standing *"we are deliberately not
> building yet,"* **execution is B1-gated**: this spec defines *what the honest UX must say and do* so
> that whenever a client is built, the truth-in-labeling is a requirement, not an afterthought. The
> project's deadliest failure mode is **false confidence** (parent §12.8) — and the UX is exactly where a
> caveat in the doc turns into a lie on the screen. This spec exists to close that gap **in advance**.

## 1. Why this is P1 (and why it's the cheapest, highest-ROI honesty win)

Every measured limitation — sender-origin identifiability (B2), device-local-only delete, detectable
mesh membership, the airtime cap — is harmless in the *spec* and dangerous in the *app* if the screen
implies otherwise. The UX honesty work is **all-local, no crypto, no network, no new attack surface**:
pure copy + state machine. It is "zero-tradeoff" in the literal sense the reconciliation half is not —
it costs nothing but discipline. So it is the right P1 companion: the design's defining feature is its
honesty, and this is where that honesty either reaches the user or doesn't.

## 2. First-run "what this protects / does NOT protect" cards (default ON)

Shown once at first launch, dismissible but re-readable from settings; **lead with the honest bottle
metaphor**, never "leave no durable trace."

- **Protects:** *what's in the bottle* and *who it's for* are hidden (content sealed end-to-end, recipient
  unlinkable on the wire); a **single** message in a dense crowd blends into the crowd (origin ≈ 1/concurrent
  originators). It does **not** make *who threw it* anonymous — see below.
- **Does NOT protect:** the finder can keep your message (screenshots, backups, a hostile relay); a
  **persistent** author is deanonymizable under multi-session intersection + device fingerprinting (B2);
  running the app is itself detectable as mesh membership (mitigated by blending toward ordinary
  BLE — constant ID-free advertisements, parent §8 — but **not** eliminated; no undetectability claim);
  needs a dense gathering to deliver at all.
- **One-line honest promise**, verbatim from the parent v0.6: *"We hide **what's in the bottle** and **who
  it's for**. We **cannot fully hide who threw it** — a one-off throw blends into the crowd, but a persistent
  thrower or a dense sensor grid can localize the origin. And we can't stop the finder from keeping it."*
- **Acceptance gate:** the card set must be reviewed against the **measured B2 numbers** before any build
  ships; no card may imply sender-unlinkability or undetectability.

## 3. Per-feature inline honesty (at the point of action)

Honesty travels with the control, not buried in a help page. **Avoid "self-destruct/disappears"**
(FTC/Snapchat deceptive-labeling precedent — parent §13).

| Control | Required inline copy (intent) |
|---|---|
| **TTL picker** | *"The person you send to can keep it. This only controls how long it circulates."* |
| **Shred / panic-wipe** | *"Erases it from THIS phone — it can't reach copies on other phones, screenshots, or backups."* **Caveat (surfaced where it applies):** the on-phone crypto-erase is **computational and construction-conditional** — it holds where the secure element honors crypto-erase (SE/TEE/StrongBox) **and** the forward-secure KEM/AEAD are sound (P5 §3); it is **not** an information-theoretic "probability-1" erase. On a device without SE/TEE, on-device erasure is **best-effort** and may leave NAND remnants (surface in-app where SE/TEE is unavailable). |
| **Origination / send** | *"At this density, your being the origin is identifiable with probability ≈ p"* — `p` is the **live, measured** source-estimator number (§10/B2), not a flattering cover-ratio. |
| **"Anonymous" anywhere** | never unqualified; links to the protect/not-protect card. |

`p` is surfaced as a **live value**, computed from the current realized density/coverage estimate — it
must degrade visibly as the user re-originates across sessions (the intersection effect), never shown as
a fixed reassuring constant.

## 4. Honest send/trust states (the state machine)

The send pipeline shows **what is actually known**, never a false "delivered." Private delivery
confirmation exists **only** via the recipient's optional sealed ack (no read receipts otherwise).

- `Emitted — no confirmed pickup yet` — the ID-free advertisement is going out, but **no peer has
  pulled it** (the connectionless-first transport, parent §8, cannot confirm pickup on pure broadcast).
  This is the honest default after sending into a venue.
- `Released to the soup` — **only on an OBSERVED handoff**: a peer actually pulled the symmetric
  difference / a reconciliation or connection event occurred (parent §8). Absent that, the UI must
  **not** claim "handed to a peer." (NOT "delivered.")
- `No peers nearby — holding` — no peer in range at all (sparse venue / cold start).
- `Expired before any peer saw it` — TTL elapsed with zero handoff (honest failure, not silent drop).
- `Acknowledged` — **only** on receipt of the recipient's sealed ack; absent otherwise (no inference).

**Forbidden states:** any "Delivered" / "Seen" / "Read" not backed by a sealed ack; any progress bar
implying guaranteed propagation; **`Released to the soup` on mere emission** (without an observed pull) —
that is the same false-positive family as a false "Delivered."

## 5. Mutual-presence pairing + persistent trust badges

- **Mutual-presence pairing** (parent §4): identities exchanged **out-of-band, in person** (QR / NFC tap
  while co-located) — never via a server/directory. Pairing establishes the opaque recipient ID **and**
  the static pairwise key `K_pair` used for deniable sender-authentication (research-stop-2 memo §1.1):
  each side exchanges an identity bundle (`mlkemPub ‖ x25519Pub`); a single ML-KEM-768 ciphertext
  (responder→initiator) is added; both derive `K_pair = HKDF(X25519(static,static) ‖ ML-KEM ss)` and
  `K_auth = HKDF(K_pair, …)`.
- **Mutual SAS confirmation is required, not optional.** Pairing completes only when **both** people
  confirm a short authentication string (the SAS — **its exact construction, bit length, and active-MITM
  bound are pinned in §5.1**), each tapping "matches" — this is what upgrades a contact from
  merely-scanned to verified, and defeats a relay/MITM at the ceremony. **A scan/tap WITHOUT a completed
  mutual SAS does NOT verify** (parent §4 notes a real ~13–14% one-way-scan completion gap), so such a
  contact stays `Unverified`. SAS-completion rate is an explicit acceptance concern.

### 5.1 The SAS as a security parameter (normative — closes red-team F1)

The SAS is the app's strongest trust signal, so it is specified as a quantified parameter, not a vibe.

- **Definition.** The SAS is a fixed-length **truncation of `SHA-256(pairing_transcript)`** (transcript
  defined in §5.2) rendered for human compare. Both devices compute it independently from the same
  transcript bytes; the two humans read their screens to each other and each taps "matches."
- **Canonical form = 6 decimal digits.** Entropy and the active-MITM bound, shown explicitly:
  - `log₂(10) = 3.3219 bits/digit` ⇒ **6 digits = 6 × 3.3219 = 19.93 bits**; value space `10⁶ = 1 000 000`.
  - **Active-MITM bound = 2⁻ᵇⁱᵗˢ per pairing attempt ≈ 2⁻¹⁹·⁹³ ≈ 1 / 10⁶ ≈ 1.0 × 10⁻⁶.**
  - **Why ~20 bits is a defensible floor (honest reasoning):** the SAS is compared **live, in person**, so
    a relay attacker who substitutes keys gets **~one online guess per ceremony** — there is no offline
    iteration against the human check (subject to the no-grinding assumption flagged below and in §5.6).
    Against one online guess, `1-in-10⁶` is a reasonable floor. This is **NOT cryptographic-collision
    strength** (that would need ≥128 bits); it is only **online-guess resistance** — do not conflate the two.
  - **Higher-assurance option:** **8 decimal digits = 8 × 3.3219 = 26.58 bits**, space `10⁸`, bound
    `≈ 2⁻²⁶·⁶ ≈ 1 × 10⁻⁸` — offered as an optional high-threat mode; **6 digits is canonical** because it is
    the as-built form and clears the floor with acceptable human-compare effort.
- **Recommended floor: ≥ ~20 bits (6 digits).** Any rendering of the SAS MUST deliver at least this.
- **Optional entropy-matched alternative forms (UX completion, per parent §4 "higher completion than
  digits").** If an emoji/word rendering is offered it MUST be **entropy-matched to the canonical 6-digit
  floor**, sizing the alphabet × count so it delivers ≥ 19.93 bits — with the math shown:
  - **Emoji:** a fixed **1024-symbol** curated set ⇒ `log₂(1024) = 10 bits/symbol` ⇒ **2 emoji = 20.00
    bits** (space 1 048 576; bound `≈ 9.5 × 10⁻⁷`). ✓ ≥ floor.
  - **Words:** a fixed **2048-word PGP-wordlist-style** list ⇒ `log₂(2048) = 11 bits/word` ⇒ **2 words =
    22.00 bits** (space 4 194 304; bound `≈ 2.4 × 10⁻⁷`). ✓ ≥ floor (over-delivers; whole-word counts
    cannot hit 19.93 exactly — stronger is fine).
  - The informal **"3-emoji / 4-word"** in parent design §4 had **unstated alphabets** (spans ~18–44 bits,
    not entropy-matched — red-team F1) and is **superseded** by the entropy-pinned forms above (reconcile
    in design at the next sync — cross-ref only, design not edited here). If matched alphabets are deemed
    too awkward to maintain, **drop the alt forms and standardize on 6 digits** — that is the safe default.
- **Rendering (deterministic, low-bias).** `SAS_int = big-endian-uint(SHA-256(transcript)[0..7])` (leading
  64 bits); digit form `= SAS_int mod 10ᵈ` zero-padded to `d` digits; symbol forms read successive
  base-`N` digits of `SAS_int` (`N = 1024` or `2048`). Taking ≥ 8 digest bytes keeps the modulo/base
  reduction bias `< 2⁻⁶⁴` (negligible).
- **Computed over the COMPLETE transcript (no grindable leftover).** Commit-before-reveal of a *SAS value*
  is **not applicable** — there is no human-entered nonce; the SAS is a pure display of a hash. The
  anti-grind property instead comes from hashing the **entire** transcript (both identity bundles **and**
  the ML-KEM ciphertext, §5.2): **no honest party and no tamperer can leave any field free to steer the
  displayed value** — every input is fixed and included before the SAS is shown. (This closes the
  "partial-transcript" grind where only identity keys were bound and the ciphertext could be chosen
  afterward.)
- **HONEST load-bearing caveat (audit item, §5.6).** The clean "~one online guess per ceremony" bound
  (hence `2⁻¹⁹·⁹³`) holds **only if a relay/wormhole attacker cannot *adaptively* grind its substituted
  key contribution toward a SAS collision.** Key contributions are public and cheap to regenerate, so an
  attacker that can choose its *second-direction* substitution **after** learning the peer's contribution
  can run an in-window target search (~`2ᵇⁱᵗˢ` work — seconds of compute at 20 bits), which 6 digits does
  **NOT** withstand. The one-guess bound therefore requires the ceremony to **fix (commit) each side's
  contribution before the peer's is revealed.** Whether the as-built sequential bundle exchange already
  provides this, or whether an explicit **commit-before-reveal of each bundle** must be added, is a **B1
  audit item (§5.6)**; if it is not provided, the SAS must be **lengthened** to withstand in-window
  grinding rather than relying on the one-guess bound. *(This is the line between online-guess resistance
  and grinding resistance — keep them distinct.)*

### 5.2 The pairing transcript the SAS binds (normative — closes red-team F2 + DSA-04)

Both `K_pair` **and** the SAS must bind the **full exchanged material** so that any tamper produces a
divergent SAS the humans catch. The transcript is the **identical byte string** feeding both — only the
domain label / KDF differs — so a tamper diverges **both** `K_pair` (pairing silently fails) and the SAS
(humans see a mismatch).

```
let (lo, hi) = order_by_x25519(bundle_A, bundle_B)     # canonical ordering, §5.3

pairing_transcript :=
      lo.mlkemPub      [1206 B]      # ML-KEM-768 identity pubkey, as carried in the bundle
    ‖ lo.x25519Pub     [  44 B]      # X25519 identity pubkey,  as carried in the bundle
    ‖ hi.mlkemPub      [1206 B]
    ‖ hi.x25519Pub     [  44 B]
    ‖ kem_ct                         # ML-KEM-768 ciphertext, responder→initiator
                                     #   (1088 B per FIPS 203; exact on-wire encoded length = the spike's
                                     #    — confirm byte-for-byte at audit)

SAS_digest := SHA-256( "polleneus-pair-sas-v0" ‖ pairing_transcript )   # 32 B, domain-separated
SAS_int    := big-endian-uint( SAS_digest[0..7] )
SAS_6dig   := decimal( SAS_int mod 10⁶ ), zero-padded to 6 digits        # canonical (§5.1)
```

- Field byte-lengths shown (`mlkemPub = 1206 B`, `x25519Pub = 44 B`) are the **bundle's as-carried**
  sizes (memo §1.1); the ML-KEM ciphertext length is the spike's on-wire form. The transcript byte-layout
  and ordering MUST be **byte-for-byte identical to the spike's `K_pair` derivation input across both
  roles** — that agreement is itself a conformance/audit item (§5.6).
- **Integrity note (DSA-04).** Today the ML-KEM ciphertext has **no integrity check at establishment
  except via this SAS** — folding it into the transcript **is** the integrity mechanism. Therefore
  **"pairing key-agreement integrity" is flagged for addition to the P5 §10 audit list** (cross-ref only;
  P5 not edited here).

### 5.3 Canonical ordering, idempotent re-pair, race handling (normative — closes red-team F6)

- **Canonical ordering.** `order_by_x25519(A, B)` = byte-wise **unsigned big-endian comparison
  (`memcmp`) of the two `x25519Pub` fields exactly as carried in the bundle**; the smaller is `lo`, the
  larger is `hi`. This **same ordering is used identically for both** `K_pair` derivation **and** the §5.2
  SAS transcript, so both roles compute identical `K_pair` and identical SAS regardless of who initiated.
  Equal pubkeys (a tie) ⇒ **abort** (same identity on both sides = misconfig or attack). *(Contribution
  validation such as low-order / identity-point rejection is tracked separately — red-team DSA-03 / P5 §6
  — not duplicated here.)*
- **Idempotent re-pair.** A second **successful** pairing (mutual SAS confirmed) with an existing contact
  **REPLACES** that contact's stored identity keys + `K_pair` atomically — it **never creates a duplicate
  contact entry.**
- **Abort-and-restart on race / partial exchange.** If a race or partial/incomplete exchange is detected
  (missing ciphertext, truncated bundle, or — decisively — a **divergent SAS**), **neither side commits
  any state**: no `K_pair` persisted, no contact created or modified, until **both** humans confirm the
  SAS. **Divergent SAS ⇒ neither side commits** and the ceremony restarts.

### 5.4 Persistent trust states & badges (extends parent §4 — closes red-team F5)

With `K_pair`, two situations that previously both read "Unverified" are **cryptographically different** and
MUST be shown distinctly. None of the non-verified states may look like a positive "trusted" mark.

- **`Cannot authenticate — no shared key` (pairing incomplete).** A one-way / scanned-only contact with
  **NO `K_pair`** (e.g. you scanned them but the bundle/ciphertext exchange never completed). You
  **cannot authenticate any sender-auth from them at all.** Neutral/muted indicator — **not** red, **not**
  trusted. The **verified/authenticated-send affordance is DISABLED** here (gated on `K_pair` presence —
  see below). *(New state — red-team F5.)*
- **`Unverified` (pairing pending SAS).** `K_pair` **is present** but the mutual SAS is **not yet
  confirmed**. `K_auth` exists (an authenticated send is cryptographically possible), but a relay-MITM at
  the ceremony has **not** been ruled out, so trust is unverified. Neutral/muted; **must NOT** look like
  or be mistaken for verified.
- **`Verified-in-person`.** `K_pair` present **AND** mutual SAS confirmed (§5.1).
- **`Key-changed!`.** The contact's **pinned identity public key** (the Ed25519 signing key per parent §4
  — and/or the X25519 / ML-KEM identity keys) **no longer matches** the stored one, **detected at a direct
  contact / in-person key exchange** (see §5.5 for the precise trigger). Potential MITM / re-pair / duress
  rotation.
- **Gate verified-send on `K_pair`.** The "send authenticated (recipient sees `from <you> [verified]`)"
  control is available **iff `K_pair` is present.** Without `K_pair` it is disabled with the
  cannot-authenticate indicator; a plain sealed message may still be sendable to that contact's address
  but **arrives unauthenticated** (no sender-MAC), and the UI must say so.
- **On `Key-changed!`: quarantine, never silently drop or silently accept.** Hold the contact's traffic
  behind an explicit tap with a clear warning (parent §4) — the user decides to re-pair or reject.
- **Red is reserved** strictly for **`Key-changed!`** — never for ordinary states (no-peers, expired,
  emitted, unverified, cannot-authenticate), so its meaning stays unambiguous and alarming. (`Unverified`
  and `Cannot authenticate` are neutral/muted, not red and not a positive "trusted" mark.)

### 5.5 Duress identity-rotation vs. trust state (normative — closes red-team F4; two halves, do not conflate)

A peer's **duress / panic rotation** (parent §6 "duress variant wipes + rotates identity") replaces their
identity keys, so the `K_pair` you stored is now **stale**: any sender-auth MAC they send under their new
`K_auth` will **fail** to verify against your stored key. Required behavior has **two distinct halves**:

1. **A failed sender-MAC on a FLOODED blob does NOTHING to trust state.** A single — or many — flooded
   message whose sender-tag fails verification is **silently dropped / shown unverified**, and is **never
   attributed to the contact and never raises `Key-changed!`.** Anyone can flood a byte-uniform blob that
   *claims* to be from contact X with a bad tag; auto-flipping the most alarming state on that would be a
   **trivial remote false-alarm / DoS.** (Mirrors red-team F3.)
2. **`Key-changed!` is driven ONLY by identity-key-change detection at a DIRECT contact / key exchange.**
   When you next exchange identity bundles **in person** with that contact and their **pinned identity
   public key** (Ed25519 signing key per parent §4 — and/or X25519 / ML-KEM identity keys) no longer
   matches the stored one, the contact moves to **`Key-changed!` / needs-re-verify** (red, quarantine,
   §5.4) — **never silently remains green `Verified-in-person`.** The only path back to
   `Verified-in-person` is a fresh mutual-SAS ceremony (§5.1–5.3), which **replaces** the contact
   idempotently (§5.3).

**Honest residual.** Between a peer's rotation and your next in-person exchange there is **no in-band
signal**: the badge stays `Verified-in-person`-but-stale while that peer's authenticated flood traffic
simply fails to verify (and is dropped/unverified per half 1). polleneus has **no key-transparency
server**, so detection is necessarily **local + at-next-contact**; this gap is **disclosed, not closed**
(red-team F4).

### 5.6 B1 audit items & residual limits (pairing / SAS)

**Audit items this spec ADDS (P5 §10 currently omits them — cross-ref only; P5 not edited here):**

- **SAS construction.** Confirm the §5.2 transcript byte-layout is **byte-for-byte identical** to the
  spike's `K_pair` derivation input across both roles; confirm the digit/symbol rendering + modulo
  reduction bias; ratify the ≥ 19.93-bit floor and the `2⁻ᵇⁱᵗˢ` bound.
- **SAS grinding-resistance / commitment property.** Confirm whether the as-built sequential bundle
  exchange prevents a relay attacker from **adaptively grinding** its substitution toward a SAS collision
  (§5.1). If not: **either** add explicit **commit-before-reveal of each bundle**, **or** lengthen the
  SAS. This determines whether the bound is the clean one-guess `2⁻¹⁹·⁹³` or degrades toward in-window
  grinding.
- **Pairing key-agreement integrity.** The ML-KEM ciphertext has **no integrity check at establishment
  except the human SAS compare** (§5.2). **Add "pairing key-agreement integrity" to P5 §10** (red-team
  DSA-04 / F2).

**Residual limits (disclosed, behind B1):**

- A **relay/wormhole active attacker present during the pairing ceremony** is defeated **only** by the
  humans' SAS compare — there is no automatic channel-authentication fallback.
- **Shoulder-surfing / coercion at the ceremony** (an observer who reads both screens, or who forces a
  "matches" tap) is out of scope for the SAS.
- The **~13–14% real-world SAS-completion gap** (above) remains a UX risk: entropy is worthless if people
  skip the compare. Completion rate stays an explicit acceptance concern.
- Everything here stays behind **B1**: no client ships before the independent security audit ratifies the
  SAS + pairing-key-agreement constructions.

## 6. In-app "red-team reality" mode

A built-in, always-reachable screen that states the §12 limitations in plain language with **live**
numbers. Get the deletion framing right (**P5 §3 supersedes the parent §5.2 "exact/w.p.1" wording**): **shred of
your own copy is a *computational, construction-conditional* crypto-erase — there is no "your message
survives with probability p" to display** (the old inverted framing), but it is **not** an
information-theoretic "probability-1" guarantee either: it holds *assuming* the secure element honors the
erase **and** the forward-secure KEM/AEAD are sound (P5 §3). The real limit is that it is **device-local**. So the live numbers to surface are: the **source-estimator
origination `p`** (the same live value as §3, degrading across re-originations), and the **device-linkage
posture** — shown as the **conservative ≈ 1.0 until the B2 USRP self-audit publishes the measured
value**, after which it becomes a live measured number (consistent with §3/B2). This is the running-app
counterpart to the spec's honesty: the user can always see what the tool does **not** do, with current
numbers — and is never told its own-copy deletion "might survive with probability p" (the old inverted
error), **nor** promised an unbreakable "probability-1" erase; it is a **computational,
hardware-and-crypto-conditional** guarantee (P5 §3).

## 7. Invariant & honesty check

- **No invariant touched** (no crypto/transport/protocol change): this is presentation + a local state
  machine. It cannot weaken inv 1–7; it can only make the *realized* honesty match the *designed*
  honesty.
- **It directly serves release-blocker B3** ("honest anonymity posture in all user-facing copy") — this
  spec is the concrete content B3 will be reviewed against, and it inherits B2's measured numbers as the
  live values §3/§6 must display.
- **Strictly honesty-positive:** the spec only *removes* potential overclaims; there is no state or
  string here that promises more than the measured guarantees.

## 8. Out of scope / deferred

- **The client implementation itself** — B1-gated (no build before audit). This spec is the contract a
  future client honors.
- **Visual design / specific strings** — final copy is a copywriting + B3-review task against the live
  numbers; this spec fixes *intent and forbidden claims*, not pixel-level wording.
- **Sealed-ack protocol details** — covered by the parent §5/§7 crypto (and P5); referenced here only as
  the sole legitimate source of an `Acknowledged` state.
- **The SAS + pairing-key-agreement crypto constructions** — the bit-floor, transcript, and ordering are
  *pinned* here (§5.1–5.3), but their **cryptographic ratification** (grinding/commitment resistance,
  pairing key-agreement integrity, contribution validation) is **B1 audit work** (§5.6); the standing
  cross-doc action is to add **"pairing key-agreement integrity" to P5 §10**.

## 9. Acceptance (when this spec is "done")

- Every card/state/string above maps to a measured guarantee or an explicit "does not protect."
- No forbidden state/claim (§4) appears anywhere; `Released to the soup` only on an **observed** handoff.
- A contact without a completed mutual SAS renders as **`Unverified`**, never as a positive "trusted"
  indicator; `Key-changed!` quarantines (never silently drops or accepts).
- The SAS is specified as a **quantified parameter** (§5.1): canonical **6 decimal digits ≈ 19.93 bits**,
  active-MITM bound **≈ 2⁻¹⁹·⁹³ ≈ 1-in-10⁶ per ceremony**, floor **≥ ~20 bits**; any alt (emoji/word) form
  is **entropy-matched** to that floor (or dropped). The SAS hashes the **complete** transcript (§5.2).
- The pairing **transcript** (§5.2) binds **both identity bundles + the ML-KEM ciphertext** under a
  canonical **lower/higher x25519 ordering** used **identically** for `K_pair` and the SAS; the layout is
  byte-for-byte the spike's `K_pair` input.
- A **scanned-but-no-`K_pair`** contact renders as a distinct **`Cannot authenticate`** state (not
  `Unverified`, not trusted), and the **verified-send UI is gated on `K_pair` presence** (§5.4).
- **Re-pair is idempotent (replace, never duplicate); a detected race / divergent SAS commits nothing on
  either side** (§5.3).
- A **failed sender-MAC on a flooded blob never raises `Key-changed!`**; `Key-changed!` / needs-re-verify
  is driven **only** by identity-key-change detection at a **direct** key exchange (duress rotation) — a
  green-but-stale `Verified-in-person` is corrected there, never left silently (§5.5).
- The **SAS construction, SAS grinding/commitment resistance, and pairing key-agreement integrity** are
  recorded as **B1 audit items**, with "pairing key-agreement integrity" flagged for **P5 §10** (§5.6).
- The shred control surfaces the **SE/TEE caveat** where the secure element is unavailable; the red-team
  screen frames own-copy deletion as **computational & construction-conditional** (P5 §3) — neither a survival-"probability" nor an unbreakable "probability-1" claim.
- The `p` value and red-team-reality device-linkage number are wired to **live** B2 measurements
  (device-linkage shown as the conservative ≈1.0 until the B2 USRP self-audit publishes the measured
  value), not reassuring constants.
- B3 (honest posture in user-facing copy) can be reviewed directly against this document.
