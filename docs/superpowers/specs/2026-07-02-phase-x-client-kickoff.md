# polleneus — Phase X kickoff: the client (spec)

**Status:** Phase X (Client + UX) kickoff · **Date:** 2026-07-02 · **Phase start human-gated:
approved 2026-07-02.**
**Builds on:** design brief (#50) + UX design system v0.1 (#51) · transport validation (#47–#49) ·
H4 at-rest hardening + M-FS3 verdict (#52).
**Gate unchanged:** **nothing installable ships before B1 (independent security audit).** This
phase produces code and lab builds, never a release.

---

## 1. Why now (entry criteria, with receipts)

- **Transport is platform-done.** Mission test passed (2026-06-30); background discovery solved by
  the screen-off duty cycler with all-dark delivery in ≤5–10s; valid-blob store-and-relay proven
  all-dark (#49); M10 overnight soak measured (~7.3h, 3 nodes, incl. a real failure + designed
  recovery); forced multi-hop ferry passed with a valid PQ blob (2026-07-02). What remains
  (M3 Samsung-penalty churn, M5 dedicated force-idle fidelity, advertising battery A/B) is
  **characterization** — it runs in parallel and does not reshape the UI-facing surface.
- **Crypto is built-or-parked, honestly.** X-Wing sealing + sender-auth validated on-device; at-rest
  keys keystore-wrapped and validated on both StrongBox and TEE paths, panic deletes the wrap key
  first (#52). FS remains **DEFERRED** with a recorded negative crypto-erase verdict (M-FS3) — the
  client makes no FS claims, which the design system already enforces.
- **Design is merged.** Direction, tokens, per-screen decisions, copy law, motion spec (#51).
- Phase X was pre-classified low guess-risk on the roadmap ("specs exist"); no research stop is
  triggered by this kickoff.

## 2. Scope / non-goals

**In scope:** an Android client module in the public repo; a versioned UI-facing service contract;
mock-first UI construction; progressive port of spike transport/crypto behind the contract;
integration on the lab fleet; honest-copy enforcement as a review gate.

**Out of scope:** any release or installable distribution (B1); iOS (deferred, brief §2); FS
claims or UI (deferred); duress/disguise beyond honest-clean (Q4 — security-track gate); store
listing / distribution copy (B3 work, later); usability studies (owed pre-pilot, see §8).

## 3. Architecture decisions

- **D1 — Client code is public.** New top-level `client/` Android project in the repo. The B1
  audit needs the client source; open development matches the project's posture. The spike under
  `spike/` **stays local** as the validation harness. CI builds debug APKs as artifacts of record
  but **never publishes releases**.
- **D2 — Process model v0: one app, in-process bound foreground service, Kotlin flows.** No
  AIDL/multi-process until a measured need appears. The FGS + duty cycler pattern is already
  validated; the client wraps it, not replaces it.
- **D3 — Port, don't copy.** Spike transport/crypto crosses into `client/` **behind the contract,
  file-by-file, sanitized and adversarially reviewed at the boundary** (no lab ties, no test
  shims). The spike's intent-command surface and test UI are explicitly left behind — per the
  brief, they were never a product interface.
- **D4 — UI: Jetpack Compose,** design-system tokens (#51) as the single theme source. Rationale:
  heavily state-machine-driven screens, previewability for design fidelity, standard toolchain.
- **D5 — minSdk 26 / target current** (inherits the spike's validated floor; the healthy lab fleet
  is Android 13 + 16).

## 4. Service contract v0 — `MeshController`

The single UI-facing boundary. Everything the UI shows must be derivable from this contract;
anything not exposed here is invisible to the UI by construction.

```kotlin
interface MeshController {
    // lifecycle
    fun start(); fun pause(); fun resume()
    val meshState: StateFlow<MeshState>        // RELAYING | LISTENING | PAUSED
    val nearbyDevices: StateFlow<Int>          // radio fact — "devices", never "people"
    val carryingCount: StateFlow<Int>          // relayed-blind blobs held for others
    val activity: SharedFlow<LocalEvent>       // Relayed | PickedUp | Faded — device-local facts only

    // identity
    val deviceKey: StateFlow<KeyChunk>         // display form "XXXX-XXXX-XXXX"; no account semantics

    // contacts & trust (state machine per parent design §5 / brief §5)
    val contacts: StateFlow<List<Contact>>     // keyChunk, localAlias?, pq, state: PENDING|VERIFIED, verifiedAt
    fun setPairingMode(on: Boolean)            // OFF = inbound requests auto-rejected before surfacing
    val pairing: SharedFlow<PairingEvent>      // PeerFound | SasReady(code: 3x3 digits) | Verified | Rejected | Failed
    fun beginExchange(peer: PeerId)
    fun confirmSasMatch(); fun rejectSasMismatch()   // reject discards keys; nothing persists
    fun setAlias(id: ContactId, alias: String) // local-only; never serialized into any wire message
    fun forget(id: ContactId)

    // messages
    val inbox: StateFlow<List<Message>>        // sender: VerifiedContact(id) | Unproven; body; receivedAt; fadesAt
    fun send(to: ContactId, body: ByteArray, ttl: Duration): ReleaseResult
                                               // fail-closed: to != VERIFIED -> refused with reason
    fun wipeMyCopy(id: MessageId)              // this device only
    val maxPlaintextBytes: StateFlow<Int>      // Q2 pinned HERE; UI reads it, never hardcodes

    // panic
    fun panicWipe()                            // wrap-key-first deletion order (H4); UI owns the two-step ceremony
}
```

**Load-bearing semantics (normative):**

- `RELAYING` = active with ≥1 nearby; `LISTENING` = active and alone (a working state, not an
  error); `PAUSED` = duty cycler stopped.
- **There is no delivery/read concept in the contract at all.** Its absence is deliberate and
  normative — a future field cannot be added without amending this spec (and it would violate
  brief §4). Local hints (`PickedUp`) are device-local facts, never delivery proof.
- `Message.sender = VerifiedContact(id)` **only** when sender-auth cryptographically matched the
  paired contact's key — this is what makes local-alias inbox labels truthful (Q1; the mission
  test already exercised VERIFIED resolution, but the exact binding is **to be confirmed and
  recorded at the X2 port review** — not treated as settled before that).
- `pause()` **intends** radio-quiet (advertise + scan + GATT server down). Until measured at X3,
  UI copy continues to make **no stealth claim** (Q6).
- Panic ordering is a contract guarantee: wrap key first, then stores (H4-validated behavior).

## 5. Mock-first construction

`MockMeshController` implements the contract with scripted scenarios: *alone*, *busy mesh*,
*pairing happy path*, *SAS reject*, *message burst*, *TTL fade-out*, *panic*. All UI milestones
develop and screenshot-review against the mock before touching the real service — the design
system (#51) is the fidelity reference. The mock ships in the repo as a permanent test fixture,
not scaffolding.

## 6. Milestones (each: spec'd DoD → build → adversarial review → PR)

| # | Deliverable | Definition of done |
|---|---|---|
| **X1** | `client/` scaffold: Compose, tokens ported from #51, mock controller, app shell (nav + Home) | Runs on S21U + Tab; Home matches design system in side-by-side screenshot review; CI builds it on every push |
| **X2** | Pairing ceremony end-to-end: UI vs mock, then **real port** of pairing + trust store | Two humans pair S21U↔Tab **on-screen, no adb** — first real SAS ceremony; reject path exercised on purpose; Q1 binding confirmed + recorded |
| **X3** | Messaging loop: compose/release/inbox/detail/TTL against the real service | **Mission test passes UI-only** on the lab fleet; UI latency copy consistent with measured all-dark truths; `pause()` radio behavior measured (Q6 closed) |
| **X4** | The honesty surfaces: onboarding (incl. battery grant, Q5), panic two-step (copy amended per M-FS3 — see Q8), "what this protects", FGS notification incl. discreet mode, settings | §3/§6 copy audit against the design-system law passes; panic wrap-key-first order verified in logs; discreet mode verified on a real lock screen |
| **X5** | Hardening: empty/degraded states on real signals, reduced-motion, TalkBack first pass, animator pause on screen-off (Q7), client CI gates (build/lint/unit) | Exit review produces the Phase V (verify + audit) prep list |

## 7. Open-questions ledger (delta vs #51 §8)

- **Q1** (alias↔key binding): likely already answered by the mission test's VERIFIED resolution —
  **confirm + record at X2**; until then inbox mock uses alias labels, real UI falls back to
  key-chunk labels if the port review says otherwise.
- **Q2** (payload cap): pinned to `maxPlaintextBytes` in the contract; transport owns the value,
  UI never hardcodes. Mock placeholder stays 2048 B.
- **Q3** (unskippable honesty gate): unchanged, with CTO; built as designed (unskippable) unless
  overruled before X4.
- **Q4** (duress/disguise): unchanged — out of scope, security-track gate.
- **Q5** (per-OEM battery deep-links): resolved during X4 with a device-tested OEM table (lab
  covers Samsung + stock-ish).
- **Q6** (pause = radio silence?): contract documents intent; **measured at X3**; no-stealth copy
  until closed.
- **Q7** (animator pause on screen-off): implemented + verified at X5.
- **Q8 (new, from #52/M-FS3):** panic's "cannot do" copy gains the flash-residual truth — a
  well-equipped forensic lab may recover traces from storage chips even after a wipe, because
  keystore deletion is not a proven flash erase. Folded into X4's copy audit.

## 8. Risks & honest limits

- **The port is the risk surface.** Spike code moving into the public client gets fresh
  adversarial review at the boundary; lab ties must not leak; B1 audits the client, and the spike
  never substitutes for it.
- **Two-device lab.** The S10+ is dead for installs (scanner failure); multi-node UI testing runs
  thin on S21U + Tab. A third healthy device is a standing human action item.
- **Everything remains UNTESTED with real users.** X2/X3 put insiders (n=2) in the loop — that
  validates mechanics, not usability. A moderated usability pass with outsiders is **owed before
  any pilot** and is now recorded as a pre-pilot requirement alongside B3.
- **No release artifacts.** CI produces debug builds for the lab only. B1 gates all shipping;
  nothing in Phase X weakens B1–B5.
