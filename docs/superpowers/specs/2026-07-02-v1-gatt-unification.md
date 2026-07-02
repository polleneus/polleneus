# polleneus — V1: unify pairing + mesh onto one GATT service (spec)

**Status:** Phase V pre-audit debt **V1** · **Date:** 2026-07-02 ·
**Human gate: SPEC SIGN-OFF required before build** — this restructures the security-critical
pairing transport (the SAS ceremony), so it is exactly the "spec sign-off / invariant-adjacent"
gate, not a routine change.
**Builds on:** the spike's proven single-service design (`spike/src/.../MeshService.java`,
already validated on the lab fleet) — this is a **port, not a redesign** (kickoff D3).
**Closes:** V1 (pairing/mesh serialization) and **root-fixes V9** (advertiser `INTERNAL_ERROR`
churn — PR #62 masked it with retry; unification removes the churn).

---

## 1. The problem (why serialization exists today)

The client runs pairing and mesh as **two fully separate BLE stacks**:

| | Pairing (`PairingManager.kt`) | Mesh (`MeshTransport.kt`) |
|---|---|---|
| GATT service | `b1c2` w/ `CHR_PAIR` (`b1c4`) | `b2b2` w/ `CHR_OFFER/REQUEST/DATA` |
| Advertiser | `PAIR_SVC` (`b1b3`) + token | `SVC` (`b2b2`) |
| Scanner | filter `b1b3` | filter `b2b2` |
| Own GATT server | yes | yes |

Two GATT servers + two advertisers + two scanners collide on the BLE stack, so
`RealMeshController.setPairingMode(on)` **stops the mesh transport** while pairing is open and
restarts it after — the serialization the runbook has flagged since X2b. Two costs:

1. **No relaying during pairing.** A phone mid-ceremony drops out of the mesh entirely.
2. **Advertiser churn → V9.** The rapid stop-mesh-adv → start-pair-adv → stop-pair-adv →
   start-mesh-adv handoff is what wedges the Samsung advertiser into `ADVERTISE_FAILED_INTERNAL_ERROR`
   (code 4), observed on the Tab A9+ during V2 verification.

## 2. The target (the spike's proven design)

The spike runs **one** node that does both. Ported to the client:

- **One GATT service** `SVC` hosting **four** characteristics: `CHR_OFFER`, `CHR_REQUEST`,
  `CHR_DATA` (mesh reconciliation) **+ `CHR_PAIR`** (the commit-before-reveal ceremony).
  `CHR_PAIR` is READ|WRITE, same framing it has today (`[round:1][totalLen:4][offset:4][chunk≤180]`).
- **One advertiser.** Always advertises `SVC`. When pairing mode is on, it **additionally** adds
  `PAIR_SVC` (an **advert-only flag UUID** — NOT a second GATT service) plus the 8-byte tiebreak
  token as service data. Both are Bluetooth-base 16-bit UUIDs, so `SVC + PAIR_SVC + 8B token`
  fits one legacy advert (spike-verified).
- **One scanner**, filtered on `SVC`. A pair-mode peer is recognized by the `PAIR_SVC` flag +
  token present in its scan record; a plain mesh peer has only `SVC`.
- **One duty cycler** (already ported in V2): `DutyPolicy.continuous(pairMode, screenOn)` — pairing
  forces continuous scanning; otherwise the screen-off windowing applies. **`pairMode` is the only
  new input to wire; the policy code is unchanged.**

## 3. Connection routing (the load-bearing addition)

On discovering a peer in a scan result, the single central decides by scan-record contents:

```
onScan(result):
  hasPairFlag = result.scanRecord has PAIR_SVC service-data (token)
  if pairMode && hasPairFlag && !pairingBusy:
      peerToken = token; emit PeerFound      // ceremony path — human taps "Begin"
      # lower-token side connects to CHR_PAIR and runs COMMIT→REVEAL→CT→KC (unchanged sequence)
  else if !flooding && freshPeer:
      # mesh path — connect, OFFER/REQUEST/DATA reconcile (unchanged)
```

The GATT **server** already demultiplexes by characteristic UUID — a write to `CHR_PAIR` drives the
ceremony state machine; a write to `CHR_OFFER`/`CHR_DATA` drives reconciliation. They coexist on one
server with **no protocol change to either**; only the host object merges.

**Concurrency guard (the one genuinely new invariant):** a single central connection at a time
(the transport findings' `≤1 concurrent central-op` rule already holds for mesh). While a ceremony
is running (`pairingBusy`), the mesh central path must not also connect — the existing
`flooding`/`ceremonyRunning` flags become one shared `centralBusy` gate so pairing and flooding
never contend for the single central GATT client. The **server** side already binds a ceremony to
one central address (`ServerState.deviceAddr`) and ignores ambient noise — that logic is preserved
verbatim.

## 4. Migration (how the code moves)

- `MeshTransport` becomes the single BLE owner: it gains `CHR_PAIR` on its service, the pair-mode
  advertiser branch, the scan-record pair-flag detection, and a `setPairingMode(on)` that flips the
  advert + duty policy **without tearing down the mesh**.
- `PairingManager`'s **ceremony state machine is moved, not rewritten** — the central `cStage`
  machine and the `ServerState` responder machine (COMMIT→REVEAL→CT→KC, all `Crypto.*` calls) port
  in verbatim as the `CHR_PAIR` handlers of the unified server/central. This is the security-critical
  part and it must be a **line-for-line move with an adversarial diff review** at the boundary.
- `RealMeshController.setPairingMode` stops calling `transport?.stop()` — it calls
  `transport.setPairingMode(on)`. The mesh keeps running throughout.
- Old `PAIR_SVC`/`SVC`/`CHR_PAIR` client UUIDs are retained (already distinct from the spike's, so
  a stray spike node can't interfere); they simply move onto one service.

## 5. Verification plan (DoD)

All on the lab fleet (S21U/A13 + Tab A9+/A16), each an explicit pass/fail:

1. **Ceremony unchanged:** two phones pair on-screen, SAS matches on both, `VERIFIED-BY-HUMAN` —
   and the **reject path** still fires on a forced commitment mismatch (security abort, not a calm
   fail). The crypto is untouched (13 JVM tests) — this proves the *transport move* preserved it.
2. **Concurrency (the whole point):** phone A relays a mesh blob **while** phone B–C run a pairing
   ceremony nearby — A's `carrying`/relay logging continues through the ceremony (no mesh pause).
3. **No advertiser churn (V9):** pair → finish → pair again, 3× in a row, with **zero**
   `ADVERTISE_FAILED_INTERNAL_ERROR` in logcat (the retry from PR #62 should never have to fire).
4. **Mission test intact:** seal on A → `DECRYPTED verified=true` on B, screen-off (V2 duty cycler
   unaffected).
5. **Gates:** 25 JVM tests + lint green; client CI green.

## 6. Risks & honest limits

- **The ceremony is the risk surface.** A transport move that subtly reorders the COMMIT-before-REVEAL
  sequence, or lets a second central interleave on `CHR_PAIR`, would weaken the SAS binding. Mitigation:
  verbatim state-machine move + the `centralBusy` single-central gate + adversarial boundary review +
  the on-device reject-path test (DoD #1). **This is why the spec is human-gated before build.**
- **Two-device concurrency test is thin.** DoD #2 ideally wants a third device so A relays while B↔C
  pair; the lab has S21U + Tab (+ the S10+ ferry, install-flaky). If only two are healthy, #2 is
  demonstrated as "mesh keeps advertising/serving during a ceremony" (server-side, single device)
  and the full three-node concurrency is recorded as owed.
- **No protocol/crypto change.** V1 is transport topology only; wire formats, UUIDs, and every
  `Crypto.*` call are unchanged. B1 unweakened.

## 7. Non-goals

- No change to the pairing UX, the SAS, or the copy.
- No multi-hop work (V6), no payload-cap decision (V5).
- No release. B1 gates all shipping.
