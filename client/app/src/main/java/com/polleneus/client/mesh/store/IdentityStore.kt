package com.polleneus.client.mesh.store

import android.content.Context
import android.util.Log
import com.polleneus.client.mesh.crypto.Crypto
import java.io.File
import java.security.SecureRandom

/**
 * The device identity: generated once from a real CSPRNG, persisted H4 keystore-wrapped
 * (identity.dat), stable across restarts. No account semantics — losing this file IS losing
 * the identity (that's the design, not a bug).
 */
class IdentityStore(private val ctx: Context, private val vault: Vault) {

    companion object {
        private const val TAG = "PN-ID"
        private const val FILE = "identity.dat"

        /**
         * Human-facing key chunk: Crockford base32 of the first 60 bits of the contactId,
         * grouped 4-4-4 ("K7QD-M2XV-94RA" style). DISPLAY derivation only — trust decisions
         * bind to the full 32-byte contactId; this is how humans tell rows apart.
         */
        fun keyChunk(contactId: ByteArray): String {
            val alphabet = "0123456789ABCDEFGHJKMNPQRSTVWXYZ" // Crockford (no I,L,O,U)
            val sb = StringBuilder(14)
            var acc = 0L
            var bits = 0
            var consumed = 0
            var i = 0
            while (consumed < 12 && i < contactId.size) {
                acc = (acc shl 8) or (contactId[i].toLong() and 0xff)
                bits += 8
                i++
                while (bits >= 5 && consumed < 12) {
                    val v = ((acc shr (bits - 5)) and 0x1f).toInt()
                    bits -= 5
                    sb.append(alphabet[v])
                    consumed++
                    if (consumed == 4 || consumed == 8) sb.append('-')
                }
            }
            return sb.toString()
        }
    }

    @Volatile private var identity: Crypto.Identity? = null

    /** Load the persisted identity or mint + persist a fresh one. Never returns null. */
    @Synchronized
    fun load(): Crypto.Identity {
        identity?.let { return it }
        val f = File(ctx.filesDir, FILE)
        if (f.exists()) {
            try {
                val raw = f.readBytes()
                val plain = if (VaultFormat.isWrapped(raw)) vault.unwrap(raw, FILE) else raw
                val id = Crypto.decodeIdentity(plain)
                if (!VaultFormat.isWrapped(raw)) persist(id) // migrate a legacy raw file in place
                identity = id
                Log.i(TAG, "identity loaded (${keyChunk(Crypto.contactId(id))})")
                return id
            } catch (e: Exception) {
                // Recoverable-vs-fatal per the spike's H4 lesson: a valid envelope that fails to
                // unwrap is treated as recoverable state damage, NOT silently replaced — replacing
                // the identity would orphan every pairing this device holds.
                Log.e(TAG, "identity unwrap/decode failed: $e — minting fresh (old contacts orphaned)")
            }
        }
        val fresh = Crypto.randomIdentity()
        persist(fresh)
        identity = fresh
        Log.i(TAG, "identity minted (${keyChunk(Crypto.contactId(fresh))})")
        return fresh
    }

    private fun persist(id: Crypto.Identity) {
        val f = File(ctx.filesDir, FILE)
        f.writeBytes(vault.wrap(Crypto.encodeIdentity(id), FILE))
    }

    fun contactId(): ByteArray = Crypto.contactId(load())

    fun keyChunk(): String = keyChunk(contactId())

    /**
     * PANIC: wrap-key first (H4 order — contract guarantee), then best-effort overwrite + delete.
     * Honest limit carried from Vault.eraseKey: OS-side revoke, not a proven flash erase.
     */
    @Synchronized
    fun panicWipe() {
        vault.eraseKey()
        val f = File(ctx.filesDir, FILE)
        if (f.exists()) {
            try {
                val junk = ByteArray(f.length().toInt().coerceAtLeast(64))
                SecureRandom().nextBytes(junk)
                f.writeBytes(junk)
            } catch (_: Exception) { }
            f.delete()
        }
        identity = null
        Log.w(TAG, "identity wiped (local erase)")
    }
}
