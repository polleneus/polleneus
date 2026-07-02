package com.polleneus.client.mesh.store;

/**
 * H4: at-rest envelope framing for keystore-wrapped files — pure logic, no Android imports, so the
 * format is JVM-testable (spike/vaulttest/VaultSelfTest.java).
 *
 * Envelope = [MAGIC 'PLV1' 4B][flags 1B][ivLen 1B][iv][ct...]   (ct = AES-256-GCM, tag appended by GCM)
 *
 * Collision safety of MAGIC vs the legacy raw formats this replaces:
 *   - legacy identity.dat starts with a 4-byte big-endian length prefix (first byte 0x00),
 *   - legacy contacts.dat starts with 0xFFFFFFFF (v1+) or a small count (first byte 0x00),
 *   so a file starting with 'P' (0x50) is unambiguously an envelope.
 */
final class VaultFormat {
    private VaultFormat() {}

    static final byte[] MAGIC = { 'P', 'L', 'V', '1' };
    static final byte FLAG_STRONGBOX = 0x01;   // informational: which backend wrapped it

    static boolean isWrapped(byte[] data) {
        if (data == null || data.length < MAGIC.length + 2) return false;
        for (int i = 0; i < MAGIC.length; i++) if (data[i] != MAGIC[i]) return false;
        return true;
    }

    static byte[] pack(byte flags, byte[] iv, byte[] ct) {
        if (iv == null || iv.length < 1 || iv.length > 255) throw new IllegalArgumentException("bad iv");
        if (ct == null || ct.length == 0) throw new IllegalArgumentException("bad ct");
        byte[] out = new byte[MAGIC.length + 2 + iv.length + ct.length];
        int o = 0;
        System.arraycopy(MAGIC, 0, out, o, MAGIC.length); o += MAGIC.length;
        out[o++] = flags;
        out[o++] = (byte) iv.length;
        System.arraycopy(iv, 0, out, o, iv.length); o += iv.length;
        System.arraycopy(ct, 0, out, o, ct.length);
        return out;
    }

    /** Parsed envelope. */
    static final class Parsed {
        final byte flags;
        final byte[] iv;
        final byte[] ct;
        Parsed(byte flags, byte[] iv, byte[] ct) { this.flags = flags; this.iv = iv; this.ct = ct; }
    }

    /** Strict parse; throws on anything malformed (caller treats as corrupt-at-rest, never as legacy). */
    static Parsed parse(byte[] data) {
        if (!isWrapped(data)) throw new IllegalArgumentException("not an envelope");
        int o = MAGIC.length;
        byte flags = data[o++];
        int ivLen = data[o++] & 0xFF;
        if (ivLen < 1 || o + ivLen >= data.length) throw new IllegalArgumentException("bad iv length");
        byte[] iv = new byte[ivLen];
        System.arraycopy(data, o, iv, 0, ivLen); o += ivLen;
        byte[] ct = new byte[data.length - o];
        System.arraycopy(data, o, ct, 0, ct.length);
        return new Parsed(flags, iv, ct);
    }
}
