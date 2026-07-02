package com.polleneus.client.mesh.store

import android.content.Context
import android.util.Log
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.SecureRandom
import java.time.Instant
import java.util.Base64

/**
 * Trust store: the paired contacts, H4 keystore-wrapped at rest (contacts.dat).
 *
 * State machine per the parent design §5 / pairing design doc step 6:
 * kc-verify persists a contact PENDING (verified=false — NOT sendable); only the human
 * SAS-match flips verified=true. "Doesn't match" deletes the record entirely.
 */
class ContactStore(private val ctx: Context, private val vault: Vault) {

    data class Record(
        val idHex: String,          // full 64-hex contactId — the trust anchor
        val peerBundle: ByteArray,  // mlkemPub ‖ x25519Pub — needed to seal to them (X3)
        val kPair: ByteArray,       // 32B pairwise root (PQ when pq=true)
        val pq: Boolean,
        val verified: Boolean,
        val alias: String?,         // local-only; never serialized into any wire message
        val verifiedAt: Instant?,
    )

    companion object {
        private const val TAG = "PN-CONTACTS"
        private const val FILE = "contacts.dat"
        private val B64 = Base64.getEncoder()
        private val B64D = Base64.getDecoder()

        fun hex(b: ByteArray): String = b.joinToString("") { "%02x".format(it) }
    }

    private val lock = Any()
    private var cache: MutableList<Record>? = null

    fun all(): List<Record> = synchronized(lock) { loadLocked().toList() }

    /** kc-verified but not yet human-accepted: persisted PENDING. Replaces any prior record for the same id. */
    fun putPending(idHex: String, peerBundle: ByteArray, kPair: ByteArray, pq: Boolean) {
        synchronized(lock) {
            val l = loadLocked()
            l.removeAll { it.idHex == idHex }
            l.add(Record(idHex, peerBundle, kPair, pq, verified = false, alias = null, verifiedAt = null))
            persistLocked(l)
            Log.i(TAG, "contact PENDING ${idHex.take(12)} pq=$pq")
        }
    }

    /** The human tapped "It matches" — the only path to sendable. */
    fun verify(idHex: String): Record? = synchronized(lock) {
        val l = loadLocked()
        val i = l.indexOfFirst { it.idHex == idHex }
        if (i < 0) return null
        l[i] = l[i].copy(verified = true, verifiedAt = Instant.now())
        persistLocked(l)
        Log.i(TAG, "contact VERIFIED-BY-HUMAN ${idHex.take(12)}")
        l[i]
    }

    fun setAlias(idHex: String, alias: String?) {
        synchronized(lock) {
            val l = loadLocked()
            val i = l.indexOfFirst { it.idHex == idHex }
            if (i < 0) return
            l[i] = l[i].copy(alias = alias?.takeIf { it.isNotBlank() })
            persistLocked(l)
        }
    }

    fun forget(idHex: String) {
        synchronized(lock) {
            val l = loadLocked()
            if (l.removeAll { it.idHex == idHex }) persistLocked(l)
            Log.i(TAG, "contact FORGOTTEN ${idHex.take(12)}")
        }
    }

    fun panicWipe() {
        synchronized(lock) {
            cache = mutableListOf()
            val f = File(ctx.filesDir, FILE)
            if (f.exists()) {
                try {
                    val junk = ByteArray(f.length().toInt().coerceAtLeast(64))
                    SecureRandom().nextBytes(junk)
                    f.writeBytes(junk)
                } catch (_: Exception) { }
                f.delete()
            }
            Log.w(TAG, "contacts wiped (local erase)")
        }
    }

    // ---- persistence (JSON inside an H4 envelope; keys as Base64) ----

    private fun loadLocked(): MutableList<Record> {
        cache?.let { return it }
        val f = File(ctx.filesDir, FILE)
        val l = mutableListOf<Record>()
        if (f.exists()) {
            try {
                val plain = vault.unwrap(f.readBytes(), FILE)
                val arr = JSONArray(String(plain, Charsets.UTF_8))
                for (i in 0 until arr.length()) {
                    val o = arr.getJSONObject(i)
                    l.add(
                        Record(
                            idHex = o.getString("id"),
                            peerBundle = B64D.decode(o.getString("bundle")),
                            kPair = B64D.decode(o.getString("kpair")),
                            pq = o.getBoolean("pq"),
                            verified = o.getBoolean("verified"),
                            alias = if (o.isNull("alias")) null else o.getString("alias"),
                            verifiedAt = if (o.isNull("vat")) null else Instant.ofEpochMilli(o.getLong("vat")),
                        )
                    )
                }
            } catch (e: Exception) {
                Log.e(TAG, "contacts load failed: $e — starting empty (file kept for forensic honesty)")
            }
        }
        cache = l
        return l
    }

    private fun persistLocked(l: MutableList<Record>) {
        cache = l
        val arr = JSONArray()
        l.forEach { r ->
            arr.put(
                JSONObject()
                    .put("id", r.idHex)
                    .put("bundle", B64.encodeToString(r.peerBundle))
                    .put("kpair", B64.encodeToString(r.kPair))
                    .put("pq", r.pq)
                    .put("verified", r.verified)
                    .put("alias", r.alias ?: JSONObject.NULL)
                    .put("vat", r.verifiedAt?.toEpochMilli() ?: JSONObject.NULL),
            )
        }
        File(ctx.filesDir, FILE).writeBytes(
            vault.wrap(arr.toString().toByteArray(Charsets.UTF_8), FILE),
        )
    }
}
