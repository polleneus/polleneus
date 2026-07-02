package com.polleneus.client.mesh

import android.content.Context
import android.util.Log
import com.polleneus.client.mesh.ble.PairingManager
import com.polleneus.client.mesh.crypto.Crypto
import com.polleneus.client.mesh.store.ContactStore
import com.polleneus.client.mesh.store.IdentityStore
import com.polleneus.client.mesh.store.Vault
import com.polleneus.client.mesh.transport.MeshStore
import com.polleneus.client.mesh.transport.MeshTransport
import com.polleneus.client.mesh.transport.validateWire
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.security.MessageDigest
import java.time.Duration
import java.time.Instant
import java.util.concurrent.ConcurrentHashMap

/**
 * The real controller: real identity (H4-wrapped, restart-stable), real trust store, real
 * commit-before-reveal pairing, and (X3b) real BLE flooding transport — send() seals & floods,
 * the inbox receives & trial-opens, carrying counts relayed-blind blobs. Honest limit: this is
 * SCREEN-ON interactive mesh; the pocket duty cycler + foreground-service notification are a
 * deferred increment.
 */
class RealMeshController(
    private val ctx: Context,
    private val scope: CoroutineScope,
) : MeshController {

    private val vault = Vault(ctx)
    private val identityStore = IdentityStore(ctx, vault)
    private val contactStore = ContactStore(ctx, vault)

    private val _meshState = MutableStateFlow(MeshState.PAUSED)
    override val meshState: StateFlow<MeshState> = _meshState.asStateFlow()

    private val _nearby = MutableStateFlow(0)          // real mesh discovery lands in X3
    override val nearbyDevices: StateFlow<Int> = _nearby.asStateFlow()

    private val _carrying = MutableStateFlow(0)        // real store-and-relay lands in X3
    override val carryingCount: StateFlow<Int> = _carrying.asStateFlow()

    private val _activity = MutableSharedFlow<LocalEvent>(replay = 8)
    override val activity: SharedFlow<LocalEvent> = _activity.asSharedFlow()

    private val _deviceKey = MutableStateFlow("")
    override val deviceKey: StateFlow<String> = _deviceKey.asStateFlow()

    private val _contacts = MutableStateFlow<List<Contact>>(emptyList())
    override val contacts: StateFlow<List<Contact>> = _contacts.asStateFlow()

    private val _pairingMode = MutableStateFlow(false)
    override val pairingMode: StateFlow<Boolean> = _pairingMode.asStateFlow()

    private val _pairing = MutableSharedFlow<PairingEvent>(extraBufferCapacity = 8)
    override val pairing: SharedFlow<PairingEvent> = _pairing.asSharedFlow()

    private val _inbox = MutableStateFlow<List<Message>>(emptyList())
    override val inbox: StateFlow<List<Message>> = _inbox.asStateFlow()

    // sealed-blob plaintext cap: X-Wing/AEAD overhead leaves room under a comfortable wire size.
    private val _maxPlaintext = MutableStateFlow(2048)
    override val maxPlaintextBytes: StateFlow<Int> = _maxPlaintext.asStateFlow()

    private var pairingManager: PairingManager? = null
    @Volatile private var pendingIdHex: String? = null

    private val meshStore = MeshStore()
    private var transport: MeshTransport? = null
    private val ID_LEN = 32   // contactId / content-address length
    // ids I decrypted (mine) vs ids I only relay (blind) — carrying = relayed-blind count (design §4)
    private val openedIds = ConcurrentHashMap.newKeySet<String>()
    private val relayedIds = ConcurrentHashMap.newKeySet<String>()
    private val messages = ConcurrentHashMap<String, Message>()

    // ---------------- lifecycle ----------------

    override fun start() {
        scope.launch(Dispatchers.IO) {
            val id = identityStore.load()               // mint-once; ML-KEM keygen is ms-scale
            _deviceKey.value = IdentityStore.keyChunk(Crypto.contactId(id))
            publishContacts()
            startTransport()
        }
    }

    /**
     * X4 (outside the contract, wired by the activity): onboarding step 1 shows the freshly
     * minted key, but the radio must not come up before the honest-deal gate — mint only.
     */
    fun ensureIdentity() {
        scope.launch(Dispatchers.IO) {
            val id = identityStore.load()
            _deviceKey.value = IdentityStore.keyChunk(Crypto.contactId(id))
            publishContacts()
        }
    }

    private fun startTransport() {
        if (transport != null) return
        if (!com.polleneus.client.system.Perms.ble(ctx)) {
            // Fresh installs reach here before the runtime grant: no radio, no transport.
            // PAUSED is the honest state — the home strip's resume retries once granted.
            Log.w("PN-CTRL", "transport not started — BLE permissions not granted")
            _meshState.value = MeshState.PAUSED
            return
        }
        val adapter = (ctx.getSystemService(Context.BLUETOOTH_SERVICE) as android.bluetooth.BluetoothManager).adapter
        if (adapter == null || !adapter.isEnabled) {
            // X5 degraded-signal guard: bluetooth off = no radio. PAUSED is honest (home
            // names the reason from the real adapter state); resume retries once it's on.
            Log.w("PN-CTRL", "transport not started — bluetooth is off")
            _meshState.value = MeshState.PAUSED
            return
        }
        val t = MeshTransport(
            ctx, meshStore,
            onBlob = { idHex, wire -> onBlobReceived(idHex, wire) },
            onPeers = { n ->
                _nearby.value = n
                if (_meshState.value != MeshState.PAUSED) {
                    _meshState.value = if (n > 0) MeshState.RELAYING else MeshState.LISTENING
                }
            },
        )
        transport = t
        t.start()
        _meshState.value = MeshState.LISTENING
        // periodic TTL sweep — faded blobs leave the store and tick the activity log
        scope.launch(Dispatchers.IO) {
            while (transport != null) {
                kotlinx.coroutines.delay(30_000)
                val dead = meshStore.sweep(System.currentTimeMillis())
                if (dead.isNotEmpty()) {
                    dead.forEach { relayedIds.remove(it); openedIds.remove(it); messages.remove(it) }
                    refreshCounts(); republishInbox()
                    _activity.emit(LocalEvent.Faded(Instant.now(), dead.size))
                }
            }
        }
    }

    override fun pause() {
        setPairingMode(false)
        transport?.stop(); transport = null
        _nearby.value = 0
        _meshState.value = MeshState.PAUSED
    }

    override fun resume() {
        if (_deviceKey.value.isEmpty()) start() else startTransport()
    }

    // ---------------- pairing ----------------

    override fun setPairingMode(on: Boolean) {
        if (on == _pairingMode.value && (on == (pairingManager != null))) return
        _pairingMode.value = on
        if (on) {
            // Free the radio for the ceremony. The client keeps pairing and mesh on separate GATT
            // services, so running both at once collides on BLE — serialize them for now. (The spike
            // unifies them onto one service; reconciling that is a follow-up.)
            transport?.stop(); transport = null; _nearby.value = 0
            _meshState.value = MeshState.PAUSED
            scope.launch(Dispatchers.IO) {
                val id = identityStore.load()
                val pm = PairingManager(ctx, id, Crypto.contactId(id)) { e -> onCeremonyEvent(e) }
                pairingManager = pm
                pm.start()
            }
        } else {
            pairingManager?.stop()
            pairingManager = null
            startTransport()   // resume the mesh once pairing closes
        }
    }

    override fun beginExchange(peerId: String) {
        pairingManager?.beginExchange()
    }

    private fun onCeremonyEvent(e: PairingManager.Event) {
        scope.launch {
            when (e) {
                is PairingManager.Event.PeerFound -> {
                    val tokenBytes = e.peerToken.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
                    _pairing.emit(
                        PairingEvent.PeerFound(e.peerToken, IdentityStore.keyChunk(tokenBytes)),
                    )
                }
                is PairingManager.Event.KcVerified -> {
                    // pairing design doc step 6: kc persists PENDING; the human SAS-match authorizes use
                    contactStore.putPending(e.idHex, e.peerBundle, e.kPair, e.pq)
                    pendingIdHex = e.idHex
                    publishContacts()
                    // ensure the SAS header names the peer even on the responder, which may not have
                    // discovered the initiator via scan yet (BLE discovery is directionally asymmetric).
                    val peerIdBytes = e.idHex.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
                    _pairing.emit(PairingEvent.PeerFound(e.idHex, IdentityStore.keyChunk(peerIdBytes)))
                    _pairing.emit(PairingEvent.SasReady(e.sas.substring(0, 3) + " " + e.sas.substring(3)))
                }
                is PairingManager.Event.Failed ->
                    // a failed commitment/key-confirmation = the reject screen (possible interception);
                    // a transport hiccup = the calm "couldn't connect" screen. Never conflate them.
                    if (e.security) _pairing.emit(PairingEvent.Rejected)
                    else _pairing.emit(PairingEvent.Failed(e.reason))
            }
        }
    }

    override fun confirmSasMatch() {
        scope.launch(Dispatchers.IO) {
            val id = pendingIdHex ?: return@launch
            val rec = contactStore.verify(id) ?: return@launch
            pendingIdHex = null
            publishContacts()
            _pairing.emit(PairingEvent.Verified(toContact(rec)))
        }
    }

    override fun rejectSasMismatch() {
        scope.launch(Dispatchers.IO) {
            pendingIdHex?.let { contactStore.forget(it) }   // discard — nothing about the attempt persists
            pendingIdHex = null
            publishContacts()
            _pairing.emit(PairingEvent.Rejected)
        }
    }

    override fun setAlias(contactId: String, alias: String) {
        scope.launch(Dispatchers.IO) {
            contactStore.setAlias(contactId, alias)
            publishContacts()
        }
    }

    override fun forget(contactId: String) {
        scope.launch(Dispatchers.IO) {
            contactStore.forget(contactId)
            publishContacts()
        }
    }

    private fun publishContacts() {
        _contacts.value = contactStore.all().map { toContact(it) }
    }

    private fun toContact(r: ContactStore.Record): Contact {
        val idBytes = r.idHex.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
        return Contact(
            id = r.idHex,
            keyChunk = IdentityStore.keyChunk(idBytes),
            alias = r.alias,
            pq = r.pq,
            state = if (r.verified) TrustState.VERIFIED else TrustState.PENDING,
            verifiedAt = r.verifiedAt,
        )
    }

    // ---------------- messages: seal & release ----------------

    override fun send(toContactId: String, body: String, ttl: Duration): ReleaseResult {
        val rec = contactStore.all().find { it.idHex == toContactId }
            ?: return ReleaseResult.Refused("recipient is not a contact")
        if (!rec.verified) return ReleaseResult.Refused("recipient is not verified — pairing comes first")
        val bytes = body.toByteArray()
        if (bytes.size > _maxPlaintext.value) return ReleaseResult.Refused("message is larger than the mesh can carry")

        val me = identityStore.load()
        val myId = Crypto.contactId(me)                       // 32B
        val split = Crypto.splitBundle(rec.peerBundle)         // [mlkemPub, x25519Pub]

        // inner plaintext = sender_contact_id(32) ‖ text — recipient learns the claimed sender on open
        val inner = myId + bytes
        val sealed = Crypto.seal(split[0], split[1], inner)
        val tag = Crypto.senderTag(Crypto.kAuth(rec.kPair), sealed)  // outer EtM sender-auth
        val bodyWire = sealed + tag
        val creationMs = System.currentTimeMillis()
        val ttlMs = ttl.toMillis().toInt()
        val wire = Crypto.withTtlHeader(creationMs, ttlMs, bodyWire)
        val id = MeshStore.hex(MeshStore.sha256(wire))

        meshStore.add(id, wire, creationMs + ttl.toMillis())
        openedIds.add(id)   // I authored it; it is not a relayed-blind carry
        refreshCounts()
        transport?.kick()
        Log.i("PN-CTRL", "SEALED+RELEASED id=${id.take(12)} to=${toContactId.take(12)} len=${wire.size}")
        scope.launch { _activity.emit(LocalEvent.Relayed(Instant.now())) }
        return ReleaseResult.Released(Instant.now())
    }

    /** A complete wire blob arrived from a peer: validate, store, trial-open. Returns true if fresh. */
    private fun onBlobReceived(idHex: String, wire: ByteArray): Boolean {
        val now = System.currentTimeMillis()
        val id = MeshStore.unhex(idHex)
        val expiry = validateWire(id, wire, now) ?: run {
            meshStore.rememberExpired(idHex); return false
        }
        if (!meshStore.add(idHex, wire, expiry)) return false   // dup

        // strip TTL header, split the outer tag, trial-open
        val bodyW = wire.copyOfRange(Crypto.TTL_HDR_LEN, wire.size)
        var sealed = bodyW
        var tag: ByteArray? = null
        if (bodyW.size >= Crypto.SENDER_TAG_LEN + Crypto.HEADER_LEN) {
            sealed = bodyW.copyOfRange(0, bodyW.size - Crypto.SENDER_TAG_LEN)
            tag = bodyW.copyOfRange(bodyW.size - Crypto.SENDER_TAG_LEN, bodyW.size)
        }
        val me = identityStore.load()
        val pt = Crypto.open(me, sealed)
        if (pt != null && pt.size >= ID_LEN) {
            val sid = pt.copyOfRange(0, ID_LEN)
            val claimedHex = MeshStore.hex(sid)
            val text = String(pt, ID_LEN, pt.size - ID_LEN, Charsets.UTF_8)
            val rec = contactStore.all().find { it.idHex == claimedHex }
            val verified = rec != null && tag != null &&
                runCatching { Crypto.verifySenderTag(Crypto.kAuth(rec.kPair), sealed, tag) }.getOrDefault(false)
            openedIds.add(idHex)
            val creationMs = Crypto.ttlCreationMs(wire)
            messages[idHex] = Message(
                id = idHex,
                sender = if (verified) Sender.VerifiedContact(claimedHex) else Sender.Unproven,
                body = text,
                receivedAt = Instant.ofEpochMilli(now),
                fadesAt = Instant.ofEpochMilli(expiry),
                openedLocally = false,
            )
            republishInbox()
            Log.i("PN-CTRL", "DECRYPTED id=${idHex.take(12)} verified=$verified")
            scope.launch { _activity.emit(LocalEvent.PickedUp(Instant.now())) }
        } else {
            relayedIds.add(idHex)   // carried, can't read — relayed-blind
            scope.launch { _activity.emit(LocalEvent.Relayed(Instant.now())) }
        }
        refreshCounts()
        return true
    }

    private fun refreshCounts() {
        _carrying.value = relayedIds.size
    }

    private fun republishInbox() {
        _inbox.value = messages.values.sortedByDescending { it.receivedAt }
    }

    override fun wipeMyCopy(messageId: String) {
        messages.remove(messageId)
        openedIds.remove(messageId)
        republishInbox()
    }

    // ---------------- panic ----------------

    override fun panicWipe() {
        scope.launch(Dispatchers.IO) {
            setPairingMode(false)
            transport?.stop(); transport = null
            meshStore.wipe(); openedIds.clear(); relayedIds.clear(); messages.clear()
            identityStore.panicWipe()      // wrap-key first (H4 contract), then file overwrite+delete
            contactStore.panicWipe()
            pendingIdHex = null
            _contacts.value = emptyList()
            _inbox.value = emptyList()
            _carrying.value = 0
            _nearby.value = 0
            _deviceKey.value = ""          // NOTHING STORED
            _meshState.value = MeshState.PAUSED
            // The order above is the X4 DoD evidence: VAULT wrap-key deleted → identity
            // wiped → contacts wiped → this line. Verified in logcat on hardware.
            Log.w("PN-CTRL", "PANIC COMPLETE — nothing stored (local erase only)")
        }
    }
}
