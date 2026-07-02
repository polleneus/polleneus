# polleneus — UX design system v0.1 ("Field Instrument")

**Status:** design-track hand-off artifact · **Date:** 2026-07-02 ·
**Builds on:** the UX/UI design brief (PR #50) — §3 honest-copy rulebook and §4 delivery model
were treated as frozen requirements throughout.
**Scope caveat:** this documents **mockups and a design contract**, not shipped UI. No client app
module exists; **nothing ships before B1 (independent security audit)**.

---

## 1. What this is

The durable output of design reviews 01–05: a direction decision, locked tokens, component law,
per-screen design decisions, a copy system, a motion spec, and a ledger of open questions routed
to their owners. High-fidelity HTML mockups (24 phone frames: 21 app screens/states + 3 Android
system surfaces, plus interactive motion demos) live in the design track's own tools per brief
§8; **this document is the interface**
— anything not written here should not be assumed from the mockups.

**Honesty note:** every flow below is designer-reasoned against the brief's threat model. None of
it is user-validated — no usability testing has occurred. Treat all interaction claims as
**UNTESTED** until a moderated test says otherwise.

## 2. Direction decision

Three directions were explored on the same Home screen (review 01): *Quiet Utility* (deliberately
ordinary), *Warm Civic* (mutual-aid warmth), *Field Instrument* (visible machinery). **Field
Instrument was chosen** — thesis: *a radio you trust because you can see it working.* Register is
instrument, not tactical: weather station, not war room. No olive drab, no stencil type, no
crosshairs — ever.

The brief-§7 tension ("plausibly ordinary — the visuals must not be an accusation on a seized lock
screen") is resolved **at the surface where it actually bites**: the in-app experience is
instrument-styled, but the surfaces a stranger can see (lock screen, notification) default to an
ordinary utility register — see §6 (discreet mode).

## 3. Tokens v0.1

```css
/* polleneus — Direction C "FIELD INSTRUMENT" — tokens v0.1 (locked 2026-07-02) */
:root {
  /* color */
  --bg:          #0C0E10;   /* near-black blue — app ground */
  --panel:       #121517;   /* raised tile fill (sparingly) */
  --panel-2:     #161B1D;   /* input fields, pressed states */
  --line:        #1F2426;   /* hairline dividers, tile borders */
  --line-strong: #2A3134;

  --ink:         #DCE3E3;   /* bone white — primary */
  --ink-dim:     #8FA0A2;   /* secondary data */
  --ink-faint:   #5C696B;   /* captions, honest micro-copy */
  --ink-ghost:   #414D4F;   /* disabled, watermarks */

  /* semantic triad — the entire trust language (see law below) */
  --accent:      #FF7A3D;   /* ATTENTION: needs-your-action, pending, unread, active nav */
  --data:        #7FB5B5;   /* VERIFIED / HEALTHY: live telemetry, verified trust, switches */
  --danger:      #FF4D3D;   /* DESTRUCTIVE / REJECT: panic, SAS mismatch — nothing else */
  --danger-text: #FF6B5A;

  --accent-dim:  rgba(255,122,61,.14);
  --data-dim:    rgba(127,181,181,.12);
  --danger-dim:  rgba(255,77,61,.10);

  /* type */
  --font-mono: 'Martian Mono', monospace;  /* labels, data, codes, status words */
  --font-body: 'Archivo', sans-serif;      /* message content, prose */

  /* shape */
  --radius: 0px;  /* faceplate aesthetic: sharp tiles, 1px hairline borders */
}
```

**Type scale (mono unless noted):** 8.5px honest captions (`t-foot`) · 9px labels (500,
tracking .16em, uppercase) · 10.5px buttons/row titles · 14.5px key codes / body (Archivo) ·
21–23px status words (700) · 30px data numerals (300) · 40px SAS code (300).

**Semantic triad law (non-negotiable):** orange = *needs your attention* (pending contacts,
unread, active nav, armed states). Teal = *verified / healthy / live* (SAS confirm, verified
badges, telemetry, toggles-on). **Red appears only for destructive or reject** (panic, "doesn't
match", wipe-my-copy). Because red is never spent on decoration, seeing it means exactly one
thing. Do not introduce a fourth semantic color without amending this spec.

**Font licensing/offline note:** Martian Mono and Archivo are OFL. Preview mockups load them from
Google Fonts; **the app must bundle fonts locally** — a blackout app cannot fetch fonts.

## 4. Component law

- **Honest micro-caption (`t-foot`):** every surfaced number carries a lowercase mono caption
  stating its limit ("unreadable by this phone", "varies as phones move", "this phone only").
  This is brief-§3 made ambient. A number without its caption is a review defect.
- **Faceplate grid:** content sits in hairline-bordered tile stacks (0 radius). Tiles:
  label → datum → caption.
- **Trust badges:** `VERIFIED` (teal outline) / `PENDING` (orange outline) / `UNVERIFIED`
  (faint outline) / `PQ` (teal fill) / `CLASSICAL` (faint dashed — informational, not alarming).
- **Fail-closed buttons:** disabled destructive-or-send actions render hatched with the reason
  inline; never silently missing.
- **TTL burn-down:** 34×4px bordered bar, fill = life remaining; switches to orange (`urgent`)
  under ~1h. Vocabulary: "fades in 2d 3h".
- **Radar:** the liveness motif (pulsing rings + node dots). Paused/alone states keep the
  instrument visible (static ring) rather than hiding it.
- **Destructive = hold:** nothing destructive happens on a tap, anywhere. Holds run 2s with a
  visible progress track that drains back at 2× on release.

## 5. Screen decisions (load-bearing only)

| Screen | Decisions that must survive reimplementation |
|---|---|
| **Home** | Status word (RELAYING / LISTENING / PAUSED) + radar; nearby & carrying tiles with captions; device key; local-activity log (device-local facts only); panic strip always present. Zero-nearby = **LISTENING**, styled as working, never as error. |
| **Inbox** | Rows labeled by **trust state**, never bare names; unread = orange edge; TTL bar per row; header states "no read receipts exist — senders never know". Local alias shown for sender-authenticated messages **(open Q1)**. |
| **Message detail** | Trust tile ("signature matched the key you verified in person on 06-28"); fades + route-unknown-by-design rows; **Wipe my copy** captioned "this phone only". |
| **Compose** | Verified-recipient-only picker (fail-closed with inline reason); TTL chips (1h/12h/**2d default**/7d) captioned "fades on every phone it reached"; byte counter **(open Q2)**; button = "Seal & release to mesh — no delivery promise". |
| **Post-send** | State = **RELEASED TO MESH**, never sent/delivered. Plain-words tile: "you won't be told when — or if — it arrives. Nobody is. That's the design." Local hints allowed, labeled "not delivery proof" (§4-permitted phrasing). |
| **Contacts** | Verified / Pending sections; pending = "cannot be sent to"; no presence indicators anywhere ("presence doesn't exist here"). |
| **Pairing** | 3 acts + reject. Act 1: pairing-mode toggle, "requests while OFF are auto-rejected". Act 2 (SAS): 3-3-3 digits at 40px, **no countdown timer** (time pressure = rushed compare), equal-size match/mismatch, confirm carries its own friction ("only after reading it aloud"). Act 3: VERIFIED — BY YOU; **alias is named here, local-only** ("never travels with a message"). Reject: keys discarded, "if it fails twice, take it seriously" — serious, not siren. |
| **Onboarding** | 3 steps: identity ("this phone just made its own key" — no account) → **the honest deal** (§3 must-disclose as a 2-sealed/3-visible ledger + "not enough if you're personally hunted"; gate tap = "I understand the limits", unskippable **(open Q3)**) → battery grant + notification reframe ("we make it useful"). |
| **Panic** | Two-step: strip/notification hold → confirm screen with **will-erase vs cannot-do** ("can't recall carried copies; can't undo a forensic image") → 2s hold. Post-wipe = "NOTHING STORED", factory-fresh look and **nothing more** — disguise/decoy is out of design scope pending security sign-off **(open Q4)**. |
| **What this protects** | The canonical B3 wording: 3 protected / 4 not-protected rows + north star ("what you say, and who you say it to, are hidden; that you're part of the network is not"). Store text and onboarding must **quote it, not paraphrase it**. One tap from settings. |
| **Settings** | Short by design. Deliberate absences are decisions: no backup/export (contradicts local-only deletion), no themes, **no "invisible mode"** (would be a lie). "Start over" routes through the panic ceremony. |
| **Notification** | First-class surface (§2). Unlocked shade: full instrument + Pause/Panic actions (Panic opens the step-2 confirm — the two-step survives the shortcut). **Locked: discreet mode, default ON — "polleneus · active" only**; counts/messages/actions hidden. Full-status-on-lock is opt-in with honest copy. RemoteViews constraint acknowledged: system fonts/shapes; we control content, hierarchy, icon, actions. |
| **Empty states** | Empty is the system working: inbox "an empty inbox is normal — nothing is archived, nothing is missing"; contacts "made in person"; paused home names the social cost ("people counting on this phone as a relay lose it") and **makes no stealth claim (open Q6)**. |

## 6. Copy system

**Voice:** an instrument that respects you — short declaratives, verbs over adjectives, zero
exclamation marks, zero emoji, never cute, never scared. Labels uppercase mono; body sentence
case; honest captions lowercase mono. **Every promise pairs with its limit** in the same breath.
Agency words: "you" = the human (trust decisions); "this phone" = the device (storage, radio).

**Formats:** 24h device-clock times ("02:14") · dates "06-28" · durations "2d 3h" / "40 min" ·
counts always name a unit and carry a caption · keys 4-4-4 ("K7QD-M2XV-94RA") · SAS 3-3-3 digits.

| Say | For | Never |
|---|---|---|
| sealed message | the unit of content, everywhere users look | blob (engineering term), chat, text, DM |
| released to the mesh | post-send state | sent ✓, delivered, "on its way" |
| fades | TTL expiry, everywhere copies reached | self-destructs, "deleted everywhere" |
| carrying | relayed-blind storage for others | syncing, downloading, hosting |
| verified — by you | trust state after a human SAS compare | trusted (passive), authenticated |
| pairing | the in-person ceremony | add friend, invite, connect |
| device key | the identity this phone generated | account, profile, username |
| panic wipe | the local two-step erase | delete account, nuke, self-destruct |
| the mesh | the network of phones, collectively | the cloud, the service, "our network" |
| devices | nearby counts — a radio fact | people / friends nearby |

**Banned everywhere (brief §3, restated as system law):** anonymous · untraceable · undetectable ·
invisible · can't be tracked · military-grade · unbreakable · NSA-proof · secure (unqualified) ·
guaranteed · delivered · seen/read (as receipts) · online/offline (about people) · any
forward-secrecy implication.

## 7. Motion

**Principle:** motion proves the machine is alive and marks state changes — it never decorates.
If removing an animation loses no information, remove the animation.

- **Telemetry loops:** slow + linear/stepped (radar 3.2s linear ∞; status blink 1.4s steps ∞).
- **State flips:** instant swap + 120ms color settle — no crossfades between truths.
- **Human-initiated reveals:** one ease-out, 240–300ms, cubic-bezier(.2,.7,.2,1); SAS digits
  stagger 120ms so both people read in the same grouped rhythm.
- **Destructive:** 2s hold, linear fill, 2× drain-back on release; completion = commit.
- **Never:** bounce, overshoot, parallax, celebration. Only the armed panic state may blink.
- **Reduced motion:** static ring + dot count replaces radar; blinks go solid; reveals appear
  instantly. All information survives.
- **Battery honesty:** loops run only screen-on + foregrounded **(open Q7)**.

## 8. Open questions ledger

| # | Question | Owner | Copy rule until answered |
|---|---|---|---|
| Q1 | Does sender-auth bind to the paired contact key, making local-alias inbox labels truthful? | engineering | fall back to key-chunk labels ("K7QD · verified") |
| Q2 | Real payload cap (mock shows 2048 B) | engineering | counter marked placeholder |
| Q3 | Unskippable onboarding honesty gate — accept? | CTO | designed unskippable |
| Q4 | Any duress/disguise beyond "factory-fresh look" post-panic | security track (brief §7) | honest-clean only |
| Q5 | Per-OEM battery-grant deep-links (Samsung "never sleeping apps" etc.) | engineering | copy stays OEM-generic |
| Q6 | Does pausing the mesh silence the radio entirely? | engineering | paused copy claims no stealth |
| Q7 | Animator pause on screen-off confirmed? | engineering | spec'd, unverified |

## 9. Non-claims & deferred

- **Mockups only.** No UI code exists; no screen has met a user; every flow is UNTESTED.
- **iOS degraded variant: DEFERRED** (brief §2 — foreground-only edge node; design after Android
  stabilizes).
- Accessibility beyond reduced-motion (TalkBack semantics, contrast audit against final rendering,
  font-scaling behavior): **DEFERRED**, required before any release candidate.
- Nothing in this document weakens the release gates: **B1 gates all shipping.**
