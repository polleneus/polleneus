package com.polleneus.client.mesh

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
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
 * Permanent test fixture (kickoff spec §5), not scaffolding. Scripts the design-system
 * scenarios so every screen can be exercised without radio: a phone that wakes alone,
 * finds a small mesh, carries for others, and receives the seeded inbox.
 */
class MockMeshController(private val scope: CoroutineScope) : MeshController {

    private val _meshState = MutableStateFlow(MeshState.PAUSED)
    override val meshState: StateFlow<MeshState> = _meshState.asStateFlow()

    private val _nearby = MutableStateFlow(0)
    override val nearbyDevices: StateFlow<Int> = _nearby.asStateFlow()

    private val _carrying = MutableStateFlow(0)
    override val carryingCount: StateFlow<Int> = _carrying.asStateFlow()

    private val _activity = MutableSharedFlow<LocalEvent>(replay = 8)
    override val activity: SharedFlow<LocalEvent> = _activity.asSharedFlow()

    private val _deviceKey = MutableStateFlow("K7QD-M2XV-94RA")
    override val deviceKey: StateFlow<String> = _deviceKey.asStateFlow()

    private val now: Instant = Instant.now()

    private val _contacts = MutableStateFlow(
        listOf(
            Contact("c1", "K7QD-M2XV-94RA", "Ash", pq = true, state = TrustState.VERIFIED,
                verifiedAt = now.minus(Duration.ofDays(4))),
            Contact("c2", "T8VN-4KQJ-77CD", "Mira", pq = true, state = TrustState.VERIFIED,
                verifiedAt = now.minus(Duration.ofDays(7))),
            Contact("c3", "9WXR-PL2M-K3FA", "Dr. Halim", pq = false, state = TrustState.VERIFIED,
                verifiedAt = now.minus(Duration.ofDays(13))),
            Contact("c4", "R4TN-88KV-2Q1P", null, pq = true, state = TrustState.PENDING,
                verifiedAt = null),
        )
    )
    override val contacts: StateFlow<List<Contact>> = _contacts.asStateFlow()

    private val _pairingMode = MutableStateFlow(false)
    override val pairingMode: StateFlow<Boolean> = _pairingMode.asStateFlow()

    // replay = 0: pairing is a live ceremony — a re-entering screen must never see a stale event
    private val _pairing = MutableSharedFlow<PairingEvent>(extraBufferCapacity = 4)
    override val pairing: SharedFlow<PairingEvent> = _pairing.asSharedFlow()

    private val _inbox = MutableStateFlow(
        listOf(
            Message("m1", Sender.VerifiedContact("c1"),
                "Generator running at the library basement — charge phones tonight.",
                receivedAt = now.minus(Duration.ofMinutes(8)),
                fadesAt = now.plus(Duration.ofHours(51)), openedLocally = false),
            Message("m2", Sender.VerifiedContact("c2"),
                "North entrance moved to 9. Pass it on in person, not over the mesh.",
                receivedAt = now.minus(Duration.ofMinutes(17)),
                fadesAt = now.plus(Duration.ofMinutes(40)), openedLocally = false),
            Message("m3", Sender.Unproven,
                "Water point at the school is confirmed open until morning.",
                receivedAt = now.minus(Duration.ofHours(2)),
                fadesAt = now.plus(Duration.ofHours(36)), openedLocally = true),
            Message("m4", Sender.VerifiedContact("c1"),
                "All good here. Lights out but everyone's calm. Save your battery.",
                receivedAt = now.minus(Duration.ofHours(5)),
                fadesAt = now.plus(Duration.ofDays(6)), openedLocally = true),
        )
    )
    override val inbox: StateFlow<List<Message>> = _inbox.asStateFlow()

    private val _maxPlaintext = MutableStateFlow(2048) // Q2 placeholder — transport owns the real value
    override val maxPlaintextBytes: StateFlow<Int> = _maxPlaintext.asStateFlow()

    private var script: Job? = null

    override fun start() {
        if (script != null) return
        _meshState.value = MeshState.LISTENING
        script = scope.launch {
            // a phone that wakes alone, then finds a small mesh
            delay(2_500)
            _nearby.value = 1; _meshState.value = MeshState.RELAYING
            delay(1_500)
            _nearby.value = 3
            _carrying.value = 9
            _activity.emit(LocalEvent.PickedUp(Instant.now(), 2))
            while (true) {
                delay(6_000)
                _carrying.value = (_carrying.value + 1).coerceAtMost(14)
                _activity.emit(LocalEvent.Relayed(Instant.now()))
                delay(9_000)
                _activity.emit(LocalEvent.PickedUp(Instant.now(), 2))
                delay(12_000)
                _carrying.value = (_carrying.value - 1).coerceAtLeast(0)
                _activity.emit(LocalEvent.Faded(Instant.now()))
            }
        }
    }

    override fun pause() {
        script?.cancel(); script = null
        _meshState.value = MeshState.PAUSED
        _nearby.value = 0
    }

    override fun resume() = start()

    override fun setPairingMode(on: Boolean) {
        _pairingMode.value = on
        if (on) scope.launch {
            delay(3_000)
            _pairing.emit(PairingEvent.PeerFound("p1", "R4TN-88KV-2Q1P"))
        }
    }

    override fun beginExchange(peerId: String) {
        scope.launch {
            delay(1_200)
            _pairing.emit(PairingEvent.SasReady("417 902 336"))
        }
    }

    override fun confirmSasMatch() {
        scope.launch {
            val c = Contact("c5", "R4TN-88KV-2Q1P", null, pq = true,
                state = TrustState.VERIFIED, verifiedAt = Instant.now())
            _contacts.value = _contacts.value.filter { it.keyChunk != c.keyChunk } + c
            _pairing.emit(PairingEvent.Verified(c))
        }
    }

    override fun rejectSasMismatch() {
        scope.launch { _pairing.emit(PairingEvent.Rejected) }
    }

    override fun setAlias(contactId: String, alias: String) {
        _contacts.value = _contacts.value.map {
            if (it.id == contactId) it.copy(alias = alias) else it
        }
    }

    override fun forget(contactId: String) {
        _contacts.value = _contacts.value.filterNot { it.id == contactId }
    }

    override fun send(toContactId: String, body: String, ttl: Duration): ReleaseResult {
        val to = _contacts.value.find { it.id == toContactId }
        if (to == null || to.state != TrustState.VERIFIED) {
            return ReleaseResult.Refused("recipient is not verified — pairing comes first")
        }
        if (body.toByteArray().size > _maxPlaintext.value) {
            return ReleaseResult.Refused("message is larger than the mesh can carry")
        }
        return ReleaseResult.Released(Instant.now())
    }

    override fun wipeMyCopy(messageId: String) {
        _inbox.value = _inbox.value.filterNot { it.id == messageId }
    }

    override fun panicWipe() {
        pause()
        _contacts.value = emptyList()
        _inbox.value = emptyList()
        _carrying.value = 0
        _deviceKey.value = "" // NOTHING STORED state
    }
}
