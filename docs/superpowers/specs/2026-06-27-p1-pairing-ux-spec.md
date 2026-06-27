# polleneus — P1: Pairing & truth-in-labeling UX (honest send/trust states)

**Version:** v0.1 — 2026-06-27 · **Roadmap:** P1 (*highest-ROI, zero-tradeoff wins* — the UX half)
**Parent design:** [polleneus v0.5 §13](2026-06-25-polleneus-design.md#13-ux--operational-security-truth-in-labeling)
· **Sibling:** [P1 reconciliation](2026-06-27-p1-reconciliation-spec.md).

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

- **Protects:** *who threw the bottle* and *who it's for* are hidden; a single message in a dense crowd
  is roughly anonymous; content is sealed end-to-end.
- **Does NOT protect:** the finder can keep your message (screenshots, backups, a hostile relay); a
  **persistent** author is deanonymizable under multi-session intersection + device fingerprinting (B2);
  running the app is itself detectable as mesh membership (mitigated by blending toward ordinary
  BLE — constant ID-free advertisements, parent §8 — but **not** eliminated; no undetectability claim);
  needs a dense gathering to deliver at all.
- **One-line honest promise**, verbatim from the parent: *"We hide who threw the bottle and who it's
  for. We can't stop the finder from keeping it."*
- **Acceptance gate:** the card set must be reviewed against the **measured B2 numbers** before any build
  ships; no card may imply sender-unlinkability or undetectability.

## 3. Per-feature inline honesty (at the point of action)

Honesty travels with the control, not buried in a help page. **Avoid "self-destruct/disappears"**
(FTC/Snapchat deceptive-labeling precedent — parent §13).

| Control | Required inline copy (intent) |
|---|---|
| **TTL picker** | *"The person you send to can keep it. This only controls how long it circulates."* |
| **Shred / panic-wipe** | *"Erases it from THIS phone — it can't reach copies on other phones, screenshots, or backups."* **Caveat (surfaced where it applies):** the exact (probability-1) on-phone erase holds only where the secure element honors crypto-erase (SE/TEE/StrongBox); on a device without it, on-device erasure is **best-effort** and may leave NAND remnants (parent §5.2 — surface in-app where SE/TEE is unavailable). |
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
  while co-located) — never via a server/directory. Pairing establishes the opaque recipient ID.
- **Mutual SAS confirmation is required, not optional.** Pairing completes only when **both** people
  confirm a short authentication string (3-emoji / 4-word SAS), each tapping "matches" — this is what
  upgrades a contact from merely-scanned to verified, and defeats a MITM. **A scan/tap WITHOUT a
  completed mutual SAS does NOT verify** (parent §4 notes a real ~13–14% one-way-scan completion gap),
  so such a contact stays `Unverified`. SAS-completion rate is an explicit acceptance concern.
- **Persistent trust badges render the parent §4 three-state set explicitly** — never a generic
  "trusted" indicator:
  - `Verified-in-person` — mutual SAS completed.
  - `Unverified` — paired/scanned but SAS not completed (must NOT look like, or be mistaken for,
    verified; this is the default for a one-way scan).
  - `Key-changed!` — the contact's key no longer matches the paired one (potential MITM / re-pair).
- **On `Key-changed!`: quarantine, never silently drop or silently accept.** Hold the contact's traffic
  behind an explicit tap with a clear warning (parent §4) — the user decides to re-pair or reject.
- **Red is reserved** strictly for **`Key-changed!`** — never for ordinary states (no-peers, expired,
  emitted, unverified), so its meaning stays unambiguous and alarming. (`Unverified` is a neutral/muted
  indicator, not red and not a positive "trusted" mark.)

## 6. In-app "red-team reality" mode

A built-in, always-reachable screen that states the §12 limitations in plain language with **live**
numbers. Get the deletion framing right (parent §5.2 de-inverted it): **shred of your own copy is EXACT
(probability 1, where SE/TEE honors crypto-erase) — there is no "shred probability"** to display; the
real limit is that it is **device-local**. So the live numbers to surface are: the **source-estimator
origination `p`** (the same live value as §3, degrading across re-originations), and the **device-linkage
posture** — shown as the **conservative ≈ 1.0 until the B2 USRP self-audit publishes the measured
value**, after which it becomes a live measured number (consistent with §3/B2). This is the running-app
counterpart to the spec's honesty: the user can always see what the tool does **not** do, with current
numbers — and is never told its own-copy deletion is merely probabilistic when it is exact.

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

## 9. Acceptance (when this spec is "done")

- Every card/state/string above maps to a measured guarantee or an explicit "does not protect."
- No forbidden state/claim (§4) appears anywhere; `Released to the soup` only on an **observed** handoff.
- A contact without a completed mutual SAS renders as **`Unverified`**, never as a positive "trusted"
  indicator; `Key-changed!` quarantines (never silently drops or accepts).
- The shred control surfaces the **SE/TEE caveat** where the secure element is unavailable; the red-team
  screen frames own-copy deletion as **exact**, not a "shred probability."
- The `p` value and red-team-reality device-linkage number are wired to **live** B2 measurements
  (device-linkage shown as the conservative ≈1.0 until the B2 USRP self-audit publishes the measured
  value), not reassuring constants.
- B3 (honest posture in user-facing copy) can be reviewed directly against this document.
