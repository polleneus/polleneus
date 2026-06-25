# polleneus

> ⚠️ **DESIGN & RESEARCH — UNAUDITED — NOT A FINISHED PRODUCT.**
> This repository contains a **design specification and adversarial reviews only**. There is **no usable
> software here yet**, and nothing has been security-audited. **Do not rely on polleneus for real-world
> safety** — at a protest, under surveillance, or anywhere the stakes are real. Trusting an unaudited tool
> for high-stakes communication can get people hurt. We will **not** publish installable builds until an
> independent security audit. Read [§Honest Limitations](docs/superpowers/specs/2026-06-25-polleneus-design.md#12-honest-limitations) before forming any opinion about what this protects.

**polleneus** is a design for an **offline-first, anonymous, self-destructing "message in a bottle."**
You encrypt a short message to a friend's opaque ID. Your phone drops it into a *uniform soup* of
fixed-size encrypted blobs that every nearby phone carries and re-shares blindly over Bluetooth — spreading
like pollen. Only your friend can recognize and open it. Messages self-destruct on a timer. The internet is
an optional, anonymized accelerator, never required.

### The honest promise
> *"We hide **who threw the bottle** and **who it's for**. We can't stop the finder from keeping it."*

Concretely, the falsifiable guarantee the design aims for: **an attacker cannot deny service to, or
deanonymize, friend-to-friend traffic in a dense gathering without physically deploying O(crowd-size)
radios and sensors.** We do **not** claim "leaves no durable trace."

### Scope
Works at the scale of a **dense gathering** (stadium / protest / campus / blacked-out neighborhood), **not**
a metropolis. Undirected flooding *buys* the anonymity and *caps* the scale — and that trade is deliberate.

### How it works (in one breath)
No routing. A soup of fixed-size sealed blobs over BLE. Every phone carries others' blobs blindly, reshares
them via efficient set reconciliation, and emits cover traffic so a real send looks like any other. You
**trial-decrypt** to find messages addressed to you. Blobs die on an absolute, signed TTL (plus optional
crypto-shred-on-read). Sealed-sender hides both ends; identities are exchanged **out-of-band** only; there
is **no server and no account**.

## Status
Design stage. No code yet. The current artifact is the specification (**v0.3**), hardened across two
multi-agent adversarial red-team passes.

- **Design spec:** [`docs/superpowers/specs/2026-06-25-polleneus-design.md`](docs/superpowers/specs/2026-06-25-polleneus-design.md)
- **Red-team review (digest):** [`docs/superpowers/reviews/2026-06-25-redteam-v0.2.md`](docs/superpowers/reviews/2026-06-25-redteam-v0.2.md)
- **Red-team raw findings:** [`docs/superpowers/reviews/2026-06-25-redteam-v0.2-raw.json`](docs/superpowers/reviews/2026-06-25-redteam-v0.2-raw.json)

## Contributing
This is an **open design**, and the thing it needs most is scrutiny. Adversarial review, cryptography and
distributed-systems critique, and creative soul-preserving alternatives are all welcome — open an issue or a
PR against the spec. Please **do not** ship or promote usable builds; the project's first duty is to not give
anyone false confidence.

## Prior art we learn from
Briar/Bramble, Bridgefy (and its two published breaks), Signal sealed sender, FireChat, Secure Scuttlebutt,
Berty/Wesh, GNUnet Messenger, Bluetooth Mesh Private Beacons, Erlay/minisketch, Loopix. See the spec's
prior-art section for what each teaches.

## License
[GPL-3.0](LICENSE) — a privacy tool must be auditable, and every fork should stay open.

---
*Codename: originally "meldingx" (Norwegian* melding *= "message").*
