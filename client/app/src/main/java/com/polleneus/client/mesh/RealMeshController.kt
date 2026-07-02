package com.polleneus.client.mesh

import android.content.Context
import com.polleneus.client.mesh.ble.PairingManager
import com.polleneus.client.mesh.crypto.Crypto
import com.polleneus.client.mesh.store.ContactStore
import com.polleneus.client.mesh.store.IdentityStore
import com.polleneus.client.mesh.store.Vault
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.Duration
import java.time.Instant

/**
 * The real controller: real identity (H4-wrapped, restart-stable), real trust store, real
 * commit-before-reveal pairing over BLE. Honest about what is NOT real yet:
 * the message loop is X3 — send() refuses, the inbox is empty, nearby/carrying stay 0 and
 * the state is LISTENING. No number on screen is invented.
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

    private val _maxPlaintext = MutableStateFlow(2048) // Q2 placeholder until transport pins it (X3)
    override val maxPlaintextBytes: StateFlow<Int> = _maxPlaintext.asStateFlow()

    private var pairingManager: PairingManager? = null
    @Volatile private var pendingIdHex: String? = null

    // ---------------- lifecycle ----------------

    override fun start() {
        scope.launch(Dispatchers.IO) {
            val id = identityStore.load()               // mint-once; ML-KEM keygen is ms-scale
            _deviceKey.value = IdentityStore.keyChunk(Crypto.contactId(id))
            publishContacts()
            _meshState.value = MeshState.LISTENING
        }
    }

    override fun pause() {
        setPairingMode(false)
        _meshState.value = MeshState.PAUSED
    }

    override fun resume() {
        if (_deviceKey.value.isEmpty()) start() else _meshState.value = MeshState.LISTENING
    }

    // ---------------- pairing ----------------

    override fun setPairingMode(on: Boolean) {
        if (on == _pairingMode.value && (on == (pairingManager != null))) return
        _pairingMode.value = on
        if (on) {
            scope.launch(Dispatchers.IO) {
                val id = identityStore.load()
                val pm = PairingManager(ctx, id, Crypto.contactId(id)) { e -> onCeremonyEvent(e) }
                pairingManager = pm
                pm.start()
            }
        } else {
            pairingManager?.stop()
            pairingManager = null
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

    // ---------------- messages (X3) ----------------

    override fun send(toContactId: String, body: String, ttl: Duration): ReleaseResult =
        ReleaseResult.Refused("messaging lands in X3 — pairing came first")

    override fun wipeMyCopy(messageId: String) { /* no messages exist before X3 */ }

    // ---------------- panic ----------------

    override fun panicWipe() {
        scope.launch(Dispatchers.IO) {
            setPairingMode(false)
            identityStore.panicWipe()      // wrap-key first (H4 contract), then file overwrite+delete
            contactStore.panicWipe()
            pendingIdHex = null
            _contacts.value = emptyList()
            _inbox.value = emptyList()
            _deviceKey.value = ""          // NOTHING STORED
            _meshState.value = MeshState.PAUSED
        }
    }
}
