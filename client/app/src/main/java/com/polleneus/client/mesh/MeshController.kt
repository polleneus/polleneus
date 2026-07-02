package com.polleneus.client.mesh

import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import java.time.Duration
import java.time.Instant

/**
 * MeshController v0 — the single UI-facing boundary (Phase X kickoff spec §4).
 *
 * NORMATIVE ABSENCE: there is no delivery or read concept anywhere in this contract.
 * That absence is load-bearing (design brief §4 — flooding makes receipts impossible;
 * showing them would be a lie). Adding any delivered/seen field requires amending the
 * kickoff spec first.
 */
interface MeshController {

    // ---- lifecycle ----
    fun start()
    fun pause()
    fun resume()

    /** RELAYING = active, ≥1 nearby · LISTENING = active, alone (a working state) · PAUSED */
    val meshState: StateFlow<MeshState>

    /** Radio fact. Copy law: "devices", never "people". */
    val nearbyDevices: StateFlow<Int>

    /** Sealed blobs held for others — relayed-blind ("carrying"). */
    val carryingCount: StateFlow<Int>

    /** Device-local facts only; never network-derived claims. */
    val activity: SharedFlow<LocalEvent>

    // ---- identity ----
    /** Display form "XXXX-XXXX-XXXX". No account semantics exist. */
    val deviceKey: StateFlow<String>

    // ---- contacts & trust (state machine per design brief §5) ----
    val contacts: StateFlow<List<Contact>>

    /** OFF = inbound requests are auto-rejected before the user ever sees them. */
    fun setPairingMode(on: Boolean)
    val pairingMode: StateFlow<Boolean>
    val pairing: SharedFlow<PairingEvent>
    fun beginExchange(peerId: String)
    fun confirmSasMatch()

    /** Discards the exchanged keys; nothing about the attempt persists. */
    fun rejectSasMismatch()

    /** Local-only. Never serialized into any wire message. */
    fun setAlias(contactId: String, alias: String)
    fun forget(contactId: String)

    // ---- messages ----
    val inbox: StateFlow<List<Message>>

    /** Fail-closed: refusing an unverified recipient is the contract's job, not just the UI's. */
    fun send(toContactId: String, body: String, ttl: Duration): ReleaseResult
    fun wipeMyCopy(messageId: String)

    /** Q2 pinned here: transport owns this value; the UI must never hardcode a cap. */
    val maxPlaintextBytes: StateFlow<Int>

    // ---- panic ----
    /** Wrap-key-first deletion order is a contract guarantee (H4). UI owns the two-step ceremony. */
    fun panicWipe()
}

enum class MeshState { RELAYING, LISTENING, PAUSED }

enum class TrustState { PENDING, VERIFIED }

data class Contact(
    val id: String,
    val keyChunk: String,          // "R4TN-88KV-2Q1P"
    val alias: String?,            // local-only; null until the human names them
    val pq: Boolean,               // post-quantum exchange marker (informational, not alarming)
    val state: TrustState,
    val verifiedAt: Instant?,
)

/** Sender identity exists ONLY as a cryptographic match against a paired key. */
sealed interface Sender {
    data class VerifiedContact(val contactId: String) : Sender
    data object Unproven : Sender
}

data class Message(
    val id: String,
    val sender: Sender,
    val body: String,
    val receivedAt: Instant,
    val fadesAt: Instant,
    /** Local fact for the unread marker. Named to stay receipt-free: nothing leaves the device. */
    val openedLocally: Boolean,
)

sealed interface LocalEvent {
    val at: Instant

    data class Relayed(override val at: Instant, val count: Int = 1) : LocalEvent
    data class PickedUp(override val at: Instant, val count: Int = 1) : LocalEvent
    data class Faded(override val at: Instant, val count: Int = 1) : LocalEvent
}

sealed interface PairingEvent {
    data class PeerFound(val peerId: String, val keyChunk: String) : PairingEvent
    /** code is the display-grouped SAS, e.g. "417 902 336" — identical on both devices. */
    data class SasReady(val code: String) : PairingEvent
    data class Verified(val contact: Contact) : PairingEvent
    data object Rejected : PairingEvent
    data class Failed(val reason: String) : PairingEvent
}

sealed interface ReleaseResult {
    /** The honest post-send state: released, not delivered. */
    data class Released(val at: Instant) : ReleaseResult
    data class Refused(val reason: String) : ReleaseResult
}
