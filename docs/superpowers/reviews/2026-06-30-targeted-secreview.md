# Security Review: meldingx

## Scope

Deep repository scan focused on the Android spike pairing trust fixes and frozen crypto/protocol design, with explicit exclusions for forward secrecy, the non-existent production client, raw-at-rest spike keys, plaintext/SAS debug logging, and the exported adb control surface.

- Scan mode: deep_repository
- Target kind: git_revision
- Target ID: target_sha256_f1aa669cf0577aa46b3136e7a3634401e76a6fa8e39dca358c877b16c6f6d536
- Revision: d0e929b64b52ab89bda1a03da6cdab8786eb418e
- Inventory strategy: repository
- Included paths: .
- Excluded paths: none
- Runtime or test status: Static validation only for Android/BLE paths; no hardware or emulator reproduction was run. Python simulator tests were not rerun for this focused validation tail.
- Artifacts reviewed: spike/src/com/polleneus/mesh/Crypto.java, spike/src/com/polleneus/mesh/MeshService.java, spike/src/com/polleneus/mesh/MainActivity.java, spike/AndroidManifest.xml, docs/superpowers/specs/2026-06-27-p1-pairing-ux-spec.md, docs/superpowers/specs/2026-06-28-p5-key-management-spec.md, spike/design-commit-before-reveal-pairing.md, spike/secreview-triage.md, sim/
- Scan context: Severity is calibrated for a pre-B1 prototype with no shipped production client. Known open items supplied by the user were not re-filed unless a scoped fix claim needed a caveat.

Limitations and exclusions:
- No Android device, BLE radio, or GATT runtime reproduction was performed.
- The exported Activity/adb extras surface was treated as known/open and out of scope except for explaining trust-gate caveats.
- Cryptographic construction review is source/design analysis, not a formal proof.
- Excluded Forward secrecy implementation/spec: Out of scope until implemented/specced.
- Excluded Production client: User stated it does not exist yet.
- Excluded SE/TEE key wrapping for spike raw keys: Known pre-B1 hardening item.
- Excluded Plaintext/SAS debug logging: Intentional validation-spike logging.
- Excluded Exported --es adb control surface: Acknowledged known/open test surface.

### Scan Summary

| Field | Value |
| --- | --- |
| Reportable findings | 3 |
| Severity mix | medium: 1, low: 2 |
| Confidence mix | high: 3 |
| Coverage | complete |
| Validation mode | Deep discovery with centralized static validation and attack-path calibration. |

Canonical artifacts: `scan-manifest.json`, `findings.json`, and `coverage.json`. This report is a deterministic projection of those files.

## Threat Model

The reviewed prototype is a BLE store-carry-forward mesh node. Important assets are identity keys, contact trust state, pairing SAS integrity, sender-auth keys, sealed message confidentiality, and prototype availability.

### Assets

- Pairing identity bundles and persistent contact records
- Durable verified and pq trust flags
- K_pair/K_auth sender-auth material
- Sealed message blobs and plaintext after local decrypt
- BLE node availability

### Trust Boundaries

- Unauthenticated BLE GATT writes/reads into MeshService
- Exported MainActivity forwarding into non-exported MeshService (known open)
- Android broadcast event channel from service to UI
- Human SAS comparison boundary

### Attacker Capabilities

- Nearby BLE peer can write protocol characteristics
- Same-device app can launch exported Activity and, on older Android, send matching broadcasts unless protected
- Pairing MITM can relay and substitute protocol messages subject to commit/KC checks

### Security Objectives

- Do not send to a contact until human SAS verification is durably recorded
- Reject inbound pairing when pair mode is off
- Keep no-contact sends fail-closed
- Make PQ-vs-classical contact state durable and visible
- Avoid practical SAS grinding and partitioning-oracle behavior

### Assumptions

- Pre-B1 spike is not shipped as a production client
- Raw key wrapping and debug log redaction are deferred by design
- Forward secrecy is out of scope until implemented

## Findings

| Finding | Severity | Confidence |
| --- | --- | --- |
| [BLE DATA intake lacks an aggregate memory and store budget](#finding-1) | medium | high |
| [Contact trust operations accept ambiguous prefixes](#finding-2) | low | high |
| [Pre-API-33 UI event receiver accepts spoofed mesh events](#finding-3) | low | high |

### Confidence Scale

| Label | Meaning |
| --- | --- |
| high | Direct evidence supports the finding with no material unresolved blocker. |
| medium | Evidence supports a plausible issue, but material runtime or reachability proof remains. |
| low | Evidence is incomplete and the item is retained only for explicit follow-up. |

<a id="finding-1"></a>

### [1] BLE DATA intake lacks an aggregate memory and store budget

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The source trace shows the per-blob cap, allocation, and unbounded store insertion. |
| Category | resource exhaustion |
| CWE | CWE-400 |
| Affected lines | spike/src/com/polleneus/mesh/MeshService.java:1082-1090, spike/src/com/polleneus/mesh/MeshService.java:685-690, spike/src/com/polleneus/mesh/MeshService.java:137-138 |

#### Summary

Rank: real-bug. CHR_DATA enforces MAX_BLOB per blob, but each new (peer,id) allocates a full declared reassembly buffer and completed valid blobs are retained in an unbounded in-memory store.

#### Root Cause

Unauthenticated BLE input is bounded per message but not in aggregate. The code allocates and stores attacker-influenced blobs without a global budget.

**Only a per-blob cap exists** — `spike/src/com/polleneus/mesh/MeshService.java:137-138`

MAX_BLOB limits one declared blob but not total live reassembly or stored bytes.

```java
    static final int MAX_BLOB = 64 * 1024;        // reassembly sanity cap
    static final long REASM_STALE_MS = 30000;     // drop partial reassembly buffers idle this long
```

**Fresh DATA ids allocate declared length** — `spike/src/com/polleneus/mesh/MeshService.java:1082-1090`

A new addr/id key allocates new byte\[totalLen\] after only the per-blob check.

```java
        String key = addr + "|" + idHex;
        pruneReasm();
        Reasm rs = reasm.get(key);
        if (rs == null || rs.totalLen != totalLen || rs.buf == null) {
            rs = new Reasm();
            rs.buf = new byte[totalLen];
            rs.totalLen = totalLen;
            rs.received = 0;
            reasm.put(key, rs);
```

**Completed blobs enter an unbounded store** — `spike/src/com/polleneus/mesh/MeshService.java:685-690`

addMessage inserts payloads without a count cap, byte cap, or spend gate.

```java
    /** Returns true if this id was new to the store. */
    boolean addMessage(byte[] id, byte[] payload) {
        String hex = bytesToHex(id);
        byte[] prev = store.putIfAbsent(hex, payload != null ? payload : new byte[0]);
        if (prev != null) return false;
        firstAcquire.put(hex, SystemClock.elapsedRealtime() - serviceStart);
```

#### Validation

handleInject is capped, but the separate CHR_DATA path still has no aggregate reassembly or store budget.

Validation method: static source trace

**Fresh DATA ids allocate declared length** — `spike/src/com/polleneus/mesh/MeshService.java:1082-1090`

A new addr/id key allocates new byte\[totalLen\] after only the per-blob check.

```java
        String key = addr + "|" + idHex;
        pruneReasm();
        Reasm rs = reasm.get(key);
        if (rs == null || rs.totalLen != totalLen || rs.buf == null) {
            rs = new Reasm();
            rs.buf = new byte[totalLen];
            rs.totalLen = totalLen;
            rs.received = 0;
            reasm.put(key, rs);
```

**Completed blobs enter an unbounded store** — `spike/src/com/polleneus/mesh/MeshService.java:685-690`

addMessage inserts payloads without a count cap, byte cap, or spend gate.

```java
    /** Returns true if this id was new to the store. */
    boolean addMessage(byte[] id, byte[] payload) {
        String hex = bytesToHex(id);
        byte[] prev = store.putIfAbsent(hex, payload != null ? payload : new byte[0]);
        if (prev != null) return false;
        firstAcquire.put(hex, SystemClock.elapsedRealtime() - serviceStart);
```

#### Dataflow

DATA frame -\> per-blob check -\> reassembly allocation -\> store insertion

- **Source:** Unauthenticated BLE CHR_DATA write frames

- **Sink:** new byte\[totalLen\] and store.putIfAbsent

- **Outcome:** Process memory pressure or OOM in the validation spike

**Fresh DATA ids allocate declared length** — `spike/src/com/polleneus/mesh/MeshService.java:1082-1090`

A new addr/id key allocates new byte\[totalLen\] after only the per-blob check.

```java
        String key = addr + "|" + idHex;
        pruneReasm();
        Reasm rs = reasm.get(key);
        if (rs == null || rs.totalLen != totalLen || rs.buf == null) {
            rs = new Reasm();
            rs.buf = new byte[totalLen];
            rs.totalLen = totalLen;
            rs.received = 0;
            reasm.put(key, rs);
```

**Completed blobs enter an unbounded store** — `spike/src/com/polleneus/mesh/MeshService.java:685-690`

addMessage inserts payloads without a count cap, byte cap, or spend gate.

```java
    /** Returns true if this id was new to the store. */
    boolean addMessage(byte[] id, byte[] payload) {
        String hex = bytesToHex(id);
        byte[] prev = store.putIfAbsent(hex, payload != null ? payload : new byte[0]);
        if (prev != null) return false;
        firstAcquire.put(hex, SystemClock.elapsedRealtime() - serviceStart);
```

#### Reachability

Reachability was not recorded beyond the canonical finding summary and affected locations.

- **Attacker:** Nearby BLE peer

- **Entry point:** Mesh GATT service CHR_DATA characteristic

- **Outcome:** Availability loss for the prototype node

#### Severity

**Medium** — For the pre-B1 prototype this is a nearby-BLE availability issue, not key disclosure or code execution. A peer in radio range can create memory pressure through unauthenticated DATA writes.

Severity rises if this ships without quotas or spend gates, and falls if production enforces aggregate byte budgets before allocation.

#### Remediation

Add global and per-peer reassembly byte budgets before allocation; reject or evict over-budget entries; add stored-blob count/byte quotas tied to the intended spend/TTL policy; track contiguous chunk coverage instead of only max offset.

Tests:
- Send many distinct IDs with totalLen=MAX_BLOB and assert live reassembly bytes stay capped.
- Assert valid blobs stop being admitted once the store quota is reached.

Preventive controls:
- Review unauthenticated parsers for both per-message and aggregate resource budgets.

<a id="finding-2"></a>

### [2] Contact trust operations accept ambiguous prefixes

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | high |
| Confidence rationale | The shared prefix resolver is directly used by seal, verify, and forget. |
| Category | trust-state confusion |
| CWE | CWE-20 |
| Affected lines | spike/src/com/polleneus/mesh/MeshService.java:786-789, spike/src/com/polleneus/mesh/MeshService.java:619-627, spike/src/com/polleneus/mesh/MeshService.java:758-768, spike/src/com/polleneus/mesh/MainActivity.java:552-557 |

#### Summary

Rank: real-bug. send, verify, and forget resolve a caller-supplied contact prefix by returning the first map key that starts with it. The normal UI passes full IDs, but the preserved prefix/test path can act on an arbitrary matching contact.

#### Root Cause

A display convenience prefix is used as a security identifier for send targeting and trust-state mutation.

**Prefix resolver returns first match** — `spike/src/com/polleneus/mesh/MeshService.java:786-789`

The resolver has no minimum length, exact-match requirement, or uniqueness check.

```java
    /** First contact whose id hex starts with {@code prefix} (lowercase), or null. */
    String findContactIdByPrefix(String prefix) {
        for (String idHex : contacts.keySet()) if (idHex.startsWith(prefix)) return idHex;
        return null;
```

**Send resolves the caller supplied prefix** — `spike/src/com/polleneus/mesh/MeshService.java:619-627`

handleSeal applies the verified gate after selecting a contact by prefix.

```java
        String pfx = to.trim().toLowerCase();
        String matchId = findContactIdByPrefix(pfx);
        if (matchId == null) {
            Log.e(TAG, "SEAL failed: unknown contact prefix=" + pfx + " (contacts=" + contacts.size() + ")");
            return;
        }
        Contact c = contacts.get(matchId);
        // H1: gate sending on the durable human-SAS-match state — refuse to seal to a PENDING/unverified contact.
        if (c == null || !c.verified) {
```

**Verify flips durable trust by prefix** — `spike/src/com/polleneus/mesh/MeshService.java:758-768`

verifyContact persists verified=true for the selected prefix match.

```java
    void verifyContact(String prefix) {
        if (prefix == null) return;
        String pfx = prefix.trim().toLowerCase();
        if (pfx.isEmpty()) return;
        String matchId = findContactIdByPrefix(pfx);
        if (matchId == null) { Log.w(TAG, "VERIFY no contact for prefix=" + pfx); return; }
        Contact c = contacts.get(matchId);
        if (c == null) return;
        if (c.verified) { Log.i(TAG, "VERIFY contact already verified=" + matchId); return; }
        contacts.put(matchId, new Contact(c.mlkemPub, c.x25519Pub, c.kAuth, true, c.pq));
        saveContacts();
```

#### Validation

The shared prefix resolver reaches handleSeal, verifyContact, and forgetContact. The UI full-ID path reduces normal-use reachability but does not fix the service API.

Validation method: static source trace

**Prefix resolver returns first match** — `spike/src/com/polleneus/mesh/MeshService.java:786-789`

The resolver has no minimum length, exact-match requirement, or uniqueness check.

```java
    /** First contact whose id hex starts with {@code prefix} (lowercase), or null. */
    String findContactIdByPrefix(String prefix) {
        for (String idHex : contacts.keySet()) if (idHex.startsWith(prefix)) return idHex;
        return null;
```

**Send resolves the caller supplied prefix** — `spike/src/com/polleneus/mesh/MeshService.java:619-627`

handleSeal applies the verified gate after selecting a contact by prefix.

```java
        String pfx = to.trim().toLowerCase();
        String matchId = findContactIdByPrefix(pfx);
        if (matchId == null) {
            Log.e(TAG, "SEAL failed: unknown contact prefix=" + pfx + " (contacts=" + contacts.size() + ")");
            return;
        }
        Contact c = contacts.get(matchId);
        // H1: gate sending on the durable human-SAS-match state — refuse to seal to a PENDING/unverified contact.
        if (c == null || !c.verified) {
```

**Verify flips durable trust by prefix** — `spike/src/com/polleneus/mesh/MeshService.java:758-768`

verifyContact persists verified=true for the selected prefix match.

```java
    void verifyContact(String prefix) {
        if (prefix == null) return;
        String pfx = prefix.trim().toLowerCase();
        if (pfx.isEmpty()) return;
        String matchId = findContactIdByPrefix(pfx);
        if (matchId == null) { Log.w(TAG, "VERIFY no contact for prefix=" + pfx); return; }
        Contact c = contacts.get(matchId);
        if (c == null) return;
        if (c.verified) { Log.i(TAG, "VERIFY contact already verified=" + matchId); return; }
        contacts.put(matchId, new Contact(c.mlkemPub, c.x25519Pub, c.kAuth, true, c.pq));
        saveContacts();
```

**Normal UI sends full IDs** — `spike/src/com/polleneus/mesh/MainActivity.java:552-557`

The primary in-app send path uses the selected full contact ID.

```java
    /** Seal + flood a message to a contact (same path as `--es text … --es to <id>`). */
    void sendToService(String contactId, String text) {
        Intent s = new Intent(this, MeshService.class);
        s.setAction(MeshService.ACTION_INJECT);
        s.putExtra("text", text);
        s.putExtra("to", contactId);
```

#### Dataflow

prefix -\> findContactIdByPrefix -\> trust-state mutation or send target

- **Source:** Caller-controlled contact prefix

- **Sink:** contacts.put verified=true, contacts.remove, or Crypto.seal target selection

- **Outcome:** Wrong contact verified, deleted, or selected for sending

**Prefix resolver returns first match** — `spike/src/com/polleneus/mesh/MeshService.java:786-789`

The resolver has no minimum length, exact-match requirement, or uniqueness check.

```java
    /** First contact whose id hex starts with {@code prefix} (lowercase), or null. */
    String findContactIdByPrefix(String prefix) {
        for (String idHex : contacts.keySet()) if (idHex.startsWith(prefix)) return idHex;
        return null;
```

**Send resolves the caller supplied prefix** — `spike/src/com/polleneus/mesh/MeshService.java:619-627`

handleSeal applies the verified gate after selecting a contact by prefix.

```java
        String pfx = to.trim().toLowerCase();
        String matchId = findContactIdByPrefix(pfx);
        if (matchId == null) {
            Log.e(TAG, "SEAL failed: unknown contact prefix=" + pfx + " (contacts=" + contacts.size() + ")");
            return;
        }
        Contact c = contacts.get(matchId);
        // H1: gate sending on the durable human-SAS-match state — refuse to seal to a PENDING/unverified contact.
        if (c == null || !c.verified) {
```

**Verify flips durable trust by prefix** — `spike/src/com/polleneus/mesh/MeshService.java:758-768`

verifyContact persists verified=true for the selected prefix match.

```java
    void verifyContact(String prefix) {
        if (prefix == null) return;
        String pfx = prefix.trim().toLowerCase();
        if (pfx.isEmpty()) return;
        String matchId = findContactIdByPrefix(pfx);
        if (matchId == null) { Log.w(TAG, "VERIFY no contact for prefix=" + pfx); return; }
        Contact c = contacts.get(matchId);
        if (c == null) return;
        if (c.verified) { Log.i(TAG, "VERIFY contact already verified=" + matchId); return; }
        contacts.put(matchId, new Contact(c.mlkemPub, c.x25519Pub, c.kAuth, true, c.pq));
        saveContacts();
```

#### Reachability

Reachability was not recorded beyond the canonical finding summary and affected locations.

- **Attacker:** Local caller or test operator using the preserved prefix surface

- **Entry point:** Forwarded Activity extras or service helper methods

- **Outcome:** Trust-state confusion in the spike

#### Severity

**Low** — The main UI uses full contact IDs and the exported adb control surface is already known open. The remaining risk is trust-state confusion in service/test APIs.

Severity rises if shortened prefixes become a production UX/API feature or external intents remain accepted.

#### Remediation

Require exact 64-hex contact IDs for service operations, or reject prefixes that are too short or non-unique. Bind verification to a current pending SAS ceremony record or nonce.

Tests:
- Create two contacts with the same short prefix and assert verify, forget, and send reject it.
- Assert legacy loaded contacts cannot become verified without a fresh pending SAS ceremony if that is the invariant.

Preventive controls:
- Keep display abbreviations separate from service identifiers.

<a id="finding-3"></a>

### [3] Pre-API-33 UI event receiver accepts spoofed mesh events

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | high |
| Confidence rationale | Source shows the API 33-only non-exported registration and pre-33 unprotected fallback. |
| Category | UI event spoofing |
| CWE | CWE-925 |
| Affected lines | spike/src/com/polleneus/mesh/MainActivity.java:119-123, spike/src/com/polleneus/mesh/MainActivity.java:341-361, spike/src/com/polleneus/mesh/MeshService.java:735-737 |

#### Summary

Rank: real-bug. On API 26-32 the Activity registers its dynamic receiver without RECEIVER_NOT_EXPORTED or a sender permission, then updates pairing, SAS, decrypted-message, and pair-mode UI state directly from broadcast extras.

#### Root Cause

The UI event channel treats package-scoped broadcasts as authenticated. Older supported Android versions need an explicit permission or in-process-only channel.

**Pre-API-33 receiver is not protected** — `spike/src/com/polleneus/mesh/MainActivity.java:119-123`

Only API 33+ uses RECEIVER_NOT_EXPORTED; older supported versions register without a permission.

```java
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(rx, f, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(rx, f);
        }
```

**Broadcast extras directly drive trust UI state** — `spike/src/com/polleneus/mesh/MainActivity.java:341-361`

The receiver accepts pairing, decrypted text, relay, identity, and pair-mode extras.

```java
    final BroadcastReceiver rx = new BroadcastReceiver() {
        // Dynamically-registered receiver -> onReceive runs on the main thread, so UI updates are direct.
        public void onReceive(Context c, Intent i) {
            String a = i.getAction();
            if (a == null) return;
            if (MeshService.EVT_IDENTITY.equals(a)) {
                onIdentity(i.getStringExtra("contactId"));
            } else if (MeshService.EVT_CONTACTS.equals(a)) {
                refreshContacts();
            } else if (MeshService.EVT_PAIRED.equals(a)) {
                onPaired(i.getStringExtra("contactId"), i.getStringExtra("sas"),
                         i.getStringExtra("side"), i.getStringExtra("peer"),
                         i.getBooleanExtra("pq", false));
            } else if (MeshService.EVT_DECRYPTED.equals(a)) {
                onDecrypted(i.getStringExtra("id"), i.getStringExtra("text"),
                            i.getStringExtra("from"), i.getBooleanExtra("verified", false));
            } else if (MeshService.EVT_RELAYED.equals(a)) {
                onRelayed();
            } else if (MeshService.EVT_PAIRMODE.equals(a)) {
                onPairMode(i.getBooleanExtra("on", false));
            }
```

#### Validation

Public action strings reach a pre-33 dynamic receiver fallback and then SAS/inbox/pair-mode UI updates. Service durable state remains a countercontrol.

Validation method: static source trace

**Pre-API-33 receiver is not protected** — `spike/src/com/polleneus/mesh/MainActivity.java:119-123`

Only API 33+ uses RECEIVER_NOT_EXPORTED; older supported versions register without a permission.

```java
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(rx, f, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(rx, f);
        }
```

**Broadcast extras directly drive trust UI state** — `spike/src/com/polleneus/mesh/MainActivity.java:341-361`

The receiver accepts pairing, decrypted text, relay, identity, and pair-mode extras.

```java
    final BroadcastReceiver rx = new BroadcastReceiver() {
        // Dynamically-registered receiver -> onReceive runs on the main thread, so UI updates are direct.
        public void onReceive(Context c, Intent i) {
            String a = i.getAction();
            if (a == null) return;
            if (MeshService.EVT_IDENTITY.equals(a)) {
                onIdentity(i.getStringExtra("contactId"));
            } else if (MeshService.EVT_CONTACTS.equals(a)) {
                refreshContacts();
            } else if (MeshService.EVT_PAIRED.equals(a)) {
                onPaired(i.getStringExtra("contactId"), i.getStringExtra("sas"),
                         i.getStringExtra("side"), i.getStringExtra("peer"),
                         i.getBooleanExtra("pq", false));
            } else if (MeshService.EVT_DECRYPTED.equals(a)) {
                onDecrypted(i.getStringExtra("id"), i.getStringExtra("text"),
                            i.getStringExtra("from"), i.getBooleanExtra("verified", false));
            } else if (MeshService.EVT_RELAYED.equals(a)) {
                onRelayed();
            } else if (MeshService.EVT_PAIRMODE.equals(a)) {
                onPairMode(i.getBooleanExtra("on", false));
            }
```

**Service sends package-scoped broadcasts** — `spike/src/com/polleneus/mesh/MeshService.java:735-737`

setPackage limits the intended recipient but does not authenticate arbitrary senders to a dynamic receiver.

```java
    /** Fire an EXPLICIT, package-scoped broadcast to the in-process Activity (best-effort, never throws). */
    void emitUi(Intent i) {
        try { i.setPackage(getPackageName()); sendBroadcast(i); } catch (Exception e) {}
```

#### Dataflow

external broadcast -\> dynamic receiver -\> UI event handler -\> visible state

- **Source:** Same-device app broadcast extras

- **Sink:** onPaired, onDecrypted, and onPairMode UI handlers

- **Outcome:** Spoofed SAS panel, pair mode, or inbox display

**Pre-API-33 receiver is not protected** — `spike/src/com/polleneus/mesh/MainActivity.java:119-123`

Only API 33+ uses RECEIVER_NOT_EXPORTED; older supported versions register without a permission.

```java
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(rx, f, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(rx, f);
        }
```

**Broadcast extras directly drive trust UI state** — `spike/src/com/polleneus/mesh/MainActivity.java:341-361`

The receiver accepts pairing, decrypted text, relay, identity, and pair-mode extras.

```java
    final BroadcastReceiver rx = new BroadcastReceiver() {
        // Dynamically-registered receiver -> onReceive runs on the main thread, so UI updates are direct.
        public void onReceive(Context c, Intent i) {
            String a = i.getAction();
            if (a == null) return;
            if (MeshService.EVT_IDENTITY.equals(a)) {
                onIdentity(i.getStringExtra("contactId"));
            } else if (MeshService.EVT_CONTACTS.equals(a)) {
                refreshContacts();
            } else if (MeshService.EVT_PAIRED.equals(a)) {
                onPaired(i.getStringExtra("contactId"), i.getStringExtra("sas"),
                         i.getStringExtra("side"), i.getStringExtra("peer"),
                         i.getBooleanExtra("pq", false));
            } else if (MeshService.EVT_DECRYPTED.equals(a)) {
                onDecrypted(i.getStringExtra("id"), i.getStringExtra("text"),
                            i.getStringExtra("from"), i.getBooleanExtra("verified", false));
            } else if (MeshService.EVT_RELAYED.equals(a)) {
                onRelayed();
            } else if (MeshService.EVT_PAIRMODE.equals(a)) {
                onPairMode(i.getBooleanExtra("on", false));
            }
```

#### Reachability

Reachability was not recorded beyond the canonical finding summary and affected locations.

- **Attacker:** Same-device app on API 26-32

- **Entry point:** Context-registered broadcast receiver actions

- **Outcome:** UI deception that can influence user action

#### Severity

**Low** — This requires a same-device app while the UI is active, and service state still gates actual sends. Impact is UI deception in the validation spike.

Severity rises if production keeps broadcast-delivered trust UI events without a signature permission.

#### Remediation

Replace broadcasts with an in-process observer or bound-service callback, or protect every event with a signature-level permission. For API levels below 33, register with a receiver permission.

Tests:
- On an API 30 emulator, send each mesh event action from a different package and assert the Activity does not update.

Preventive controls:
- Do not use package-scoped broadcasts as authentication.

## Reviewed Surfaces

| Surface | Risk Area | Outcome | Notes |
| --- | --- | --- | --- |
| H1 pairing trust gate | Pairing trust | No issue found | Verified fixed for the intended UI/send path: addContact persists PENDING, handleSeal refuses unverified contacts, updateSendEnabled reads service UI_VERIFIED, and v2 contacts persist verified. Caveats: --es verify is part of the known exported control surface, and prefix ambiguity is reported. Evidence: artifacts/05_findings/validation_summary.md |
| H2 inbound pairing consent | Pairing consent | No issue found | Pair writes reject before state creation when pair mode is off, and CHR_PAIR reads also fail. Evidence: artifacts/05_findings/validation_summary.md |
| C1 handleInject allocation bound | Local IPC/test surface | No issue found | handleInject rejects sizes above MAX_BLOB. Separate BLE aggregate budgeting is reported. Evidence: artifacts/05_findings/validation_summary.md |
| H3 fixed recipient removal | Recipient selection | No issue found | No-contact sends fail closed and the deterministic fixed-recipient helper is removed. Evidence: artifacts/05_findings/validation_summary.md |
| H5 durable PQ-vs-classical marker | Pairing key state | No issue found | Contact.pq is saved, loaded, and shown. Classical fallback remains a visible policy choice. Evidence: artifacts/05_findings/validation_summary.md |
| Frozen commit-before-reveal pairing design | Protocol design | No issue found | Commit-before-reveal, bundles-only SAS, CT key-confirmation, abort behavior, and K_pair ordering match the reconciled design. Some stale wording remains in the design note and P1 acceptance bullets. Evidence: artifacts/05_findings/validation_summary.md |
| Key-committing AEAD construction | Envelope crypto | No issue found | The explicit pre-decrypt SHA-256 key commitment blocks the practical partitioning-oracle path reviewed here. Formal proof and exact CMT scope remain B1 audit items. Evidence: artifacts/05_findings/validation_summary.md |
| BLE DATA resource budgets | Transport availability | Reported | Reported as BLE DATA aggregate memory/store DoS. Evidence: artifacts/05_findings/CANON-R1-005A/validation_report.md, artifacts/05_findings/CANON-R1-005A/attack_path_analysis_report.md |
| Contact prefix resolution | Trust-state integrity | Reported | Reported as ambiguous prefix trust operation confusion. Evidence: artifacts/05_findings/CANON-R2-013/validation_report.md, artifacts/05_findings/CANON-R2-013/attack_path_analysis_report.md |
| UI event broadcasts | Trust UI integrity | Reported | Reported as pre-API-33 UI event spoofing. Evidence: artifacts/05_findings/CANON-R1-002/validation_report.md, artifacts/05_findings/CANON-R1-002/attack_path_analysis_report.md |
| Raw-at-rest spike keys | Known deferred hardening | Not applicable | Out of scope per user: SE/TEE key wrapping is a known deferred spike item. Evidence: artifacts/05_findings/validation_summary.md |
| Plaintext/SAS debug logging | Known deferred hardening | Not applicable | Out of scope per user: intentional validation-spike logging. Evidence: artifacts/05_findings/validation_summary.md |
| Exported Activity adb control surface | Known open test affordance | Not applicable | Out of scope per user, except as a caveat for scoped fix verification. Evidence: artifacts/05_findings/validation_summary.md |
| Simulator model-fidelity candidates | Model integrity | Rejected | Not treated as app/runtime security findings in this focused pre-B1 crypto/Android review. Evidence: artifacts/05_findings/validation_summary.md |

## Open Questions And Follow Up

- Should B1 allow the marked classical fallback, or should production refuse pq=false contacts?
  - Follow-up prompt: Review MeshService classical fallback paths at lines 1279-1282 and 1735-1746 against authorize-and-mark versus PQ-required policy.
- Should verifyContact require a current pending SAS ceremony nonce or exact full ID?
  - Follow-up prompt: Review MeshService.verifyContact and contact loading at lines 758-768 and 799-838; decide whether verification must be bound to a current EVT_PAIRED ceremony record.
- Clean up stale wording in spike/design-commit-before-reveal-pairing.md line 41 and P1 acceptance bullets around lines 333-340.
  - Follow-up prompt: Patch the P1 pairing acceptance bullets and design rationale to say contacts persist PENDING on KC, send is gated on durable verified, SAS covers ordered bundles only, and CT integrity is KC.
- Should the already-known mutable wire-header sender-auth gap be fixed now?
  - Follow-up prompt: Extend Crypto.senderTag and the wire transcript to bind version, global-TTL, message ID, ephemeral key, and creation timestamp; update MeshService verification and P5 section 6.
