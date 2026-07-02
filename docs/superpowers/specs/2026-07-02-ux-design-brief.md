# polleneus — UX/UI Design Brief (hand-off contract)

**Status:** design contract for a parallel UX/UI track · **Date:** 2026-07-02 · **Audience:** an
external UX/UI team starting with zero prior context.

This document is the **contract** between the security/transport engineering (in progress) and the
visual/interaction design. Design **to this brief**, not to any existing code: the prototype's on-screen
UI is throwaway test scaffolding and its internal event API is not a product interface. Everything here
that reads as a *constraint* is load-bearing — it comes from the protocol's threat model and cannot be
designed away.

---

## 1. What the product is (and is not)

polleneus is an **offline-first, Bluetooth-LE mesh messenger** for conditions where normal
infrastructure is down or hostile — blackouts, protests, disasters. Phones relay sealed messages to
each other directly over BLE, with **no servers, no accounts, no phone numbers, no internet**. The
mission test is concrete: *two phones with no internet still exchange a message, and the network keeps
working as nodes come and go.*

It is **not** a mainstream secure messenger and must never be presented as one. It has no cloud, no
contact discovery, no "seen"/read receipts, no real-time presence, and — critically — it makes
**different and narrower privacy promises** than Signal/WhatsApp-class apps (see §3). The design's job
is to make those real promises legible and the limits honest, in a UI a stressed non-expert can use.

---

## 2. Platform frame (the fixed canvas)

- **Android-first.** Android phones are the mesh backbone. Design Android screens first.
- **A permanent foreground-service notification is unavoidable.** The mesh only runs as an ongoing
  foreground service, so there is always a persistent notification while the app is active. Treat it as
  a **first-class UI surface** (status, quick panic access), not an afterthought to hide.
- **Runs locked and in a pocket.** The core value is relaying while the screen is off. The UI is what
  people see in bursts when they pick the phone up; the *work* happens dark. Nothing critical can
  require the screen to be on.
- **Battery-optimization onboarding is required.** On many phones (especially Samsung) the OS will kill
  or throttle the app unless the user grants "unrestricted battery" / "never sleeping app." This is an
  **onboarding flow you must design**, with plain-language justification — it's a known adoption cliff.
- **iOS is a later, degraded edge node** (foreground-only; two backgrounded iPhones can't find each
  other). Design Android as the full experience; iOS is a reduced-capability follow-up, not parity.

---

## 3. The honest-copy rulebook  ⚠️ LOAD-BEARING — read before sketching anything

This is the part that will force a redo if ignored. The protocol protects a **specific, narrower** set
of things than users expect from "secure messenger," and the project has a hard rule (release-blocker
B3) against copy that overpromises. A failure here isn't a polish issue — it can get a user hurt, because
they act on a false promise in exactly the settings where exposure is dangerous.

### What IS protected (say this clearly, it's the real value)
- **Content secrecy.** Messages are end-to-end sealed; only the intended recipient can read them.
- **Recipient privacy.** Because every message floods to ~everyone nearby, *receiving* a message does
  not reveal that you were its intended recipient. "It landed on my phone" ≠ "it was for me."

### What is NOT protected (must be disclosed, never implied away)
- **You are not anonymous as a persistent author.** A single message blends into the crowd, but someone
  who repeatedly transmits and is technically surveilled **can be identified over time**. This is a
  permanent, architectural limit shared by every mesh tool — not a bug to be fixed. The app is **not**
  for a specifically-hunted individual under heavy surveillance, and the copy must say so.
- **Running the app is itself detectable.** Participating in the mesh is a radio signal; a capable
  observer can tell the app is in use. There is no "invisible mode." (A subtle related fact: the app's
  scanning pattern can even leak whether your screen is on — so "undetectable" is simply false.)
- **Deletion is local only.** Wiping a message removes it from *your* device. It cannot reach copies
  already carried by other phones, screenshots, or a seized device's forensic image.

### DO-NOT-SAY list (hard bans in all copy, labels, store text, onboarding)
- "Anonymous," "untraceable," "undetectable," "invisible," "can't be tracked."
- "Military-grade," "unbreakable," "perfectly secure," "NSA-proof."
- Anything implying guaranteed delivery, real-time chat, or that the network hides *that* you're using it.
- Anything implying forward secrecy (that feature is deferred — see §7).

### MUST-DISCLOSE, in plain language, at the right moments
- The persistent-author limit and the "using it is detectable" limit — surfaced in onboarding and
  reachable from a "What this protects / what it doesn't" screen, not buried in a EULA.
- That delivery is best-effort and may never happen (§4).
- That "verified" is a human action the user performed, not a system guarantee (§5).

**A good north star:** the honest pitch is *"what you say and who you say it to are hidden; that you're
part of the network is not."* Design to make people confident in the first half and unsurprised by the
second.

---

## 4. The delivery model (design for opportunistic, not real-time)

This is not a chat app's send→delivered→read→typing loop. Bake the following into every messaging screen:

- **Opportunistic store-carry-forward.** A message hops phone to phone as they come into range. When
  everyone is nearby it can feel quick; when phones are pocketed and asleep, convergence can take on the
  order of a minute or more, or wait until devices next meet. Design for **"sent into the mesh,"** not
  "delivered at 10:42."
- **No delivery or read receipts — ever.** Flooding means the sender fundamentally cannot know who
  received a message. Do not design checkmarks/"seen" states; they'd be lies. The honest status is
  "released to the mesh." (You *may* show local, non-authoritative hints like "a nearby device
  acknowledged carrying this," but never frame it as "delivered to <person>.")
- **Messages expire (TTL).** Every message has a lifetime (default on the order of days, sender-set);
  after it, the message disappears everywhere it can reach. **Ephemerality is a feature to surface**, not
  hide — think "this message will fade," and let the sender choose shorter lifetimes for sensitive notes.
- **No sender name on received messages.** The sealed envelope carries **no authenticated sender
  identity**. The inbox therefore labels a message by its **trust state** (see §5), not by "From: Alice."
  The strongest truthful label is *"from a verified contact"* (when sender-auth succeeds against a
  contact you paired with) vs *"unverified"* — never a free-text name the wire can't prove.
- **Relayed-blind is normal and worth showing.** Your phone constantly carries other people's sealed
  messages it cannot read. A subtle indicator ("carrying N messages for the mesh, unreadable") both
  explains battery use and communicates the recipient-privacy property viscerally.

---

## 5. Trust model & state machine (stable — safe to design against)

Trust is built by a **human pairing ceremony**, not a directory. This is the most security-critical
interaction; get it unambiguous.

### Contact / pairing states
```
   (stranger)
      │  both users turn Pairing mode ON, in proximity
      ▼
   PAIRING  ── devices exchange keys, each shows the SAME short code ──►  SAS COMPARE
      │                                                                      │
      │  users read the two codes aloud / screen-to-screen                   │
      ├───────────────── codes DIFFER → user taps "Doesn't match" ──────────┤→ REJECT (discard, warn: possible interception)
      │                                                                      │
      └───────────────── codes MATCH  → user taps "It matches"  ────────────┘→ VERIFIED
```
- **PENDING** — keys exchanged but the human has not yet confirmed the code match. **Cannot be sent to.**
  Must be visually distinct from verified (e.g., muted, "unverified — compare codes to finish").
- **VERIFIED** — the human compared the short code and confirmed. Sendable. Persisted across restarts.
  "Verified" means *"you personally checked this,"* and the copy should frame it that way, not as an
  automatic system stamp.
- **PQ vs classical marker** — a per-contact indicator of whether the strongest (post-quantum) key
  exchange was used. Design a small, non-alarming badge; most contacts will be PQ. (Don't over-explain
  it; a tap-through detail is enough.)

### Rules the UI must enforce
- **Send is fail-closed:** no verified contact selected → sending is blocked with a clear reason, never
  a silent default recipient.
- **Inbound pairing requires consent:** if someone tries to pair while your Pairing mode is **off**, it
  is rejected. Pairing is never something that "just happens" to a user.
- The **short code compare is the security boundary.** Make it prominent, unhurried, and symmetric on
  both screens (same grouped digits). A rushed or skippable compare defeats the whole protection.

---

## 6. Screen inventory (what to design)

Each is a design surface; states in parentheses come from §4–§5.

1. **Onboarding / first-run** — the honest-expectations flow (§3 must-disclose), identity generation
   ("your device just made a fresh key — there's no account"), and the **battery-optimization grant**
   (§2). This flow carries the ethical weight; treat it as core, not a skippable intro.
2. **Home / status** — my identity (a fingerprint/short code, not a name), mesh state (nearby devices,
   running/paused), the carrying-for-the-mesh indicator, and fast access to Panic. Mirror key status
   into the **persistent notification**.
3. **Pairing** — the Pairing-mode toggle, discovery of a nearby pairing peer, and the **SAS compare
   ceremony** (§5) with match / doesn't-match and the resulting verified/reject states.
4. **Contacts** — list with **verified vs pending** clearly separated, the PQ badge, a way to open a
   contact, and **forget/remove**. No presence/online dots (there is no presence).
5. **Compose / send** — pick a **verified** contact, write, choose a **message lifetime (TTL)**, send.
   Show the honest post-send state ("released to the mesh"), not "delivered." Block on unverified.
6. **Inbox / message view** — messages labeled by **trust state** (§4), TTL/"fading" indication, and the
   relayed-blind context. No sender names, no read receipts.
7. **Panic / duress** — a deliberate **two-tap** wipe (guard against accidental taps) that erases local
   identity, contacts, and stored messages and returns to a clean state. Copy must be honest: it's a
   best-effort local wipe, strong but **not a guarantee against a forensic adversary** who already has
   the device — and it cannot recall messages other phones already carry.
8. **"What this protects / what it doesn't"** — a always-reachable plain-language honesty screen (§3).
   This is a feature, not fine print.

---

## 7. Explicit non-goals & off-limits

- **No feature that implies real-time presence, delivery/read receipts, typing indicators, or
  guaranteed delivery.** They cannot be true here.
- **No forward-secrecy claims.** That capability is deferred; do not surface it in copy or icons.
- **Do not design against, or expose, the wire format, cryptography, or the service's internal API** —
  those are owned by the engineering track and are gated by an independent security audit. Design
  screens, states, copy, and flows; not protocol.
- **No installable/shipping build ships before the independent security audit (release-blocker B1),**
  regardless of how finished the visuals are. Deliverables in this phase are **mockups and prototypes**,
  not a release.
- Keep it **plausibly ordinary.** In the threat setting, an app that screams "protest tool" is a
  liability; the visual language should not itself be an accusation on a seized lock screen. (Discuss a
  duress/disguise direction with the security track before committing to it.)

---

## 8. Working agreement / hand-back

- **Design lives in your tools (Figma/etc.), not in this repo.** When something becomes repo content
  (design tokens, redlines, later UI code), it is contributed **through the project's pull-request flow
  and committed under the project identity** — individual contributors' real-world identities are kept
  out of the repository by policy. Coordinate the actual commit/hand-back with the maintainer; don't
  push under personal accounts.
- **Branch, don't worktree**, for anything that does become code — one feature branch per UI work item,
  merged via PR — but note there is **no client app module yet** to build UI code into, so early work is
  design artifacts only.
- **Treat §3 and §4 as frozen requirements**; treat §5–§6 as stable but open to interaction-design
  proposals; flag anything in §2 that seems to block a good experience so the engineering track can
  weigh it. When in doubt about whether a claim is truthful, ask before shipping the pixels — the
  honesty bar is the one that bites late.
