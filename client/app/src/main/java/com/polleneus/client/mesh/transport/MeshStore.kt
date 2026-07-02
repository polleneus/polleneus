package com.polleneus.client.mesh.transport

import com.polleneus.client.mesh.crypto.Crypto
import java.security.MessageDigest
import java.util.concurrent.ConcurrentHashMap

/**
 * The content-addressed store-carry-forward store (client build of the spike's M1 store).
 * id (hex) -> full wire blob = [ttlHdr(12)] ‖ sealed ‖ tag. id == SHA-256(wire), so the store
 * is self-verifying and naturally deduplicating. TTL expiry + aggregate budgets bound it.
 *
 * Everything a phone holds — messages for it AND relayed-blind blobs for others — lives here.
 */
class MeshStore {
    companion object {
        const val ID_LEN = 32
        const val MAX_BLOBS = 2000
        const val MAX_BYTES = 64L * 1024 * 1024
        // TTL bounds (ms): 1 minute .. 30 days, matching the spike's accepted range.
        const val MIN_TTL_MS = 60_000L
        const val MAX_TTL_MS = 30L * 24 * 60 * 60 * 1000
        const val MAX_FUTURE_SKEW_MS = 5L * 60 * 1000

        fun sha256(b: ByteArray): ByteArray = MessageDigest.getInstance("SHA-256").digest(b)
        fun hex(b: ByteArray): String = b.joinToString("") { "%02x".format(it) }
        fun unhex(s: String): ByteArray =
            ByteArray(s.length / 2) { ((s[it * 2].digitToInt(16) shl 4) or s[it * 2 + 1].digitToInt(16)).toByte() }
    }

    private data class Entry(val wire: ByteArray, val expiryAt: Long, val addedAt: Long)

    private val lock = Any()
    private val map = LinkedHashMap<String, Entry>()  // insertion-ordered → oldest-first eviction
    private val expiredSeen = ConcurrentHashMap<String, Long>()  // recently-expired ids (don't re-accept)
    private var bytes = 0L
    private var seq = 0L

    val count: Int get() = synchronized(lock) { map.size }

    /** Add a wire blob under its content-address id. Returns true if fresh (not a dup / not expired). */
    fun add(id: String, wire: ByteArray, expiryAt: Long): Boolean = synchronized(lock) {
        if (map.containsKey(id)) return false
        enforceBudget(wire.size)
        map[id] = Entry(wire, expiryAt, seq++)
        bytes += wire.size
        true
    }

    fun get(id: String): ByteArray? = synchronized(lock) { map[id]?.wire }

    fun has(id: String): Boolean = synchronized(lock) { map.containsKey(id) }

    fun wasExpired(id: String): Boolean = expiredSeen.containsKey(id)

    fun rememberExpired(id: String) { expiredSeen[id] = nowSeq() }

    /** All live ids, for the OFFER inventory. */
    fun inventory(): List<ByteArray> = synchronized(lock) { map.keys.map { unhex(it) } }

    /** Drop everything whose absolute expiry has passed. Returns dropped ids (for a "faded" tick). */
    fun sweep(now: Long): List<String> = synchronized(lock) {
        val dead = map.filter { it.value.expiryAt <= now }.keys.toList()
        dead.forEach { id -> map.remove(id)?.let { bytes -= it.wire.size }; expiredSeen[id] = 0 }
        dead
    }

    fun wipe() = synchronized(lock) { map.clear(); expiredSeen.clear(); bytes = 0 }

    private fun enforceBudget(incoming: Int) {
        // evict oldest until within both caps (linked-hash iteration order = oldest first)
        while ((map.size + 1 > MAX_BLOBS || bytes + incoming > MAX_BYTES) && map.isNotEmpty()) {
            val oldest = map.keys.first()
            map.remove(oldest)?.let { bytes -= it.wire.size }
        }
    }

    private fun nowSeq() = seq
}

/**
 * Validate a freshly-received wire blob before storing: content-address integrity + TTL sanity.
 * Returns the absolute expiry (creationMs+ttl) if acceptable, or null to drop.
 */
fun validateWire(id: ByteArray, wire: ByteArray, now: Long): Long? {
    if (wire.size < Crypto.TTL_HDR_LEN) return null
    if (!MessageDigest.isEqual(MeshStore.sha256(wire), id)) return null  // id != SHA-256(wire)
    val creationMs = Crypto.ttlCreationMs(wire)
    val ttlMs = Crypto.ttlTtlMs(wire).toLong() and 0xffffffffL
    if (ttlMs < MeshStore.MIN_TTL_MS || ttlMs > MeshStore.MAX_TTL_MS) return null
    if (creationMs > now + MeshStore.MAX_FUTURE_SKEW_MS) return null
    val expiry = creationMs + ttlMs
    if (now >= expiry) return null  // already expired in flight
    return expiry
}
