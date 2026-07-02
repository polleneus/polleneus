package com.polleneus.client.mesh.crypto;

import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.bouncycastle.jcajce.spec.MLKEMParameterSpec;
import org.bouncycastle.jcajce.spec.KEMGenerateSpec;
import org.bouncycastle.jcajce.spec.KEMExtractSpec;
import org.bouncycastle.jcajce.SecretKeyWithEncapsulation;
import org.bouncycastle.crypto.generators.HKDFBytesGenerator;
import org.bouncycastle.crypto.params.HKDFParameters;
import org.bouncycastle.crypto.digests.SHA256Digest;

import javax.crypto.Cipher;
import javax.crypto.KeyAgreement;
import javax.crypto.KeyGenerator;
import javax.crypto.Mac;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.MessageDigest;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.security.Security;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.io.ByteArrayOutputStream;
import java.util.Arrays;

/**
 * Phase C / C4 — END-TO-END SEALED ENVELOPE for the polleneus BLE flooding mesh.
 *
 * This is the VALIDATED on-device crypto from {@code cryptotest/MainActivity.java} (Phase C / C3,
 * BouncyCastle 1.79 JCA) lifted verbatim into a reusable sealing API:
 *   X-Wing hybrid KEM = ML-KEM-768 (PQ) + X25519 (classical), combined SHA3-256("polleneus-xwing-v0"
 *   ‖ ssM ‖ ssX ‖ ctM ‖ ephX_pub), then a key-committing AEAD = ChaCha20-Poly1305 with a SHA-256
 *   key-commitment as the AAD (Hash-then-Encrypt; the commitment binds the key so a wrong key is rejected).
 *
 * PURE JAVA: no Android imports — so it compiles for Android AND can be unit-tested on a plain JVM
 * with only bcprov-jdk18on-1.79.jar on the classpath. The mesh layer (MeshService) does the logging.
 *
 * SEALED BLOB WIRE FORMAT (big bytes first, no length fields — every field but the AEAD ciphertext is fixed):
 *   mlkem_ct(1088) ‖ ephX25519_pub(44) ‖ commit(32) ‖ nonce(12) ‖ aead_ct(plaintext+16 tag)
 *   => fixed overhead = 1176 header + 16 Poly1305 tag = 1192 B + payload  (matches LAB §8d/§8c).
 */
public final class Crypto {

    static final java.nio.charset.Charset UTF8 = java.nio.charset.StandardCharsets.UTF_8;

    // ---- sealed-blob fixed field sizes (ML-KEM-768 + X25519, BC encodings) ----
    public static final int MLKEM_CT_LEN = 1088; // ML-KEM-768 ciphertext
    public static final int EPHX_PUB_LEN = 44;   // X25519 SubjectPublicKeyInfo (12B hdr + 32B key)
    public static final int COMMIT_LEN   = 32;   // SHA-256 key commitment
    public static final int NONCE_LEN    = 12;   // ChaCha20-Poly1305 nonce
    /** Bytes preceding the AEAD ciphertext; a valid sealed blob is at least this long (+16B tag). */
    public static final int HEADER_LEN   = MLKEM_CT_LEN + EPHX_PUB_LEN + COMMIT_LEN + NONCE_LEN; // 1176

    // H3: the world-known fixed-recipient test seed (RECIPIENT_SEED) and the deterministic recipient identity
    // it derived have been REMOVED. There is no default/world-known recipient key; the sender fails closed when
    // no contact is selected (see MeshService.handleSeal). Real recipients come only from Phase X pairing/SAS.

    // ============================================================= provider

    private static volatile boolean provInserted = false;

    /** Insert BouncyCastle once, ahead of the platform's stripped legacy "BC" (gone on API 28+). */
    public static synchronized void init() {
        if (provInserted) return;
        Security.removeProvider("BC");
        Security.insertProviderAt(new BouncyCastleProvider(), 1);
        provInserted = true;
    }
    static { init(); }

    // ============================================================= identity

    /** A node identity = an (ML-KEM-768 keypair, X25519 keypair). */
    public static final class Identity {
        public final KeyPair mlkem;
        public final KeyPair x25519;
        Identity(KeyPair mlkem, KeyPair x25519) { this.mlkem = mlkem; this.x25519 = x25519; }
        public PrivateKey mlkemPriv()  { return mlkem.getPrivate(); }
        public PrivateKey x25519Priv() { return x25519.getPrivate(); }
        public byte[] mlkemPubEnc()    { return mlkem.getPublic().getEncoded(); }
        public byte[] x25519PubEnc()   { return x25519.getPublic().getEncoded(); }
    }

    /** Fresh random identity (relay-only node: cannot open messages sealed to the fixed recipient). */
    public static Identity randomIdentity() {
        try { return identity(new SecureRandom()); }
        catch (Exception e) { throw new RuntimeException("randomIdentity failed: " + e, e); }
    }

    // ============================================================= Phase X / PAIRING: identity persistence,
    //                                                              contact ids, pairing bundles, SAS.

    /** X25519 SubjectPublicKeyInfo length (12B hdr + 32B key) — same as {@link #EPHX_PUB_LEN}. */
    public static final int X25519_PUB_LEN = EPHX_PUB_LEN; // 44

    /**
     * Serialize an Identity to a self-describing byte[] so it can be persisted and reloaded across restarts:
     *   [4B len]mlkemPriv(PKCS8) [4B len]mlkemPub(X509) [4B len]x25519Priv(PKCS8) [4B len]x25519Pub(X509).
     * Reloading reconstructs the SAME keypairs, so a node's identity (and contact id) is STABLE.
     */
    public static byte[] encodeIdentity(Identity id) {
        try {
            ByteArrayOutputStream bos = new ByteArrayOutputStream();
            putBlob(bos, id.mlkem.getPrivate().getEncoded());   // PKCS8
            putBlob(bos, id.mlkem.getPublic().getEncoded());    // X509
            putBlob(bos, id.x25519.getPrivate().getEncoded());  // PKCS8
            putBlob(bos, id.x25519.getPublic().getEncoded());   // X509
            return bos.toByteArray();
        } catch (Exception e) {
            throw new RuntimeException("encodeIdentity failed: " + e, e);
        }
    }

    /** Inverse of {@link #encodeIdentity}; throws on any corruption so callers can fall back to regenerating. */
    public static Identity decodeIdentity(byte[] data) throws Exception {
        init();
        int[] o = {0};
        byte[] mlkemPriv  = getBlob(data, o);
        byte[] mlkemPub   = getBlob(data, o);
        byte[] x25519Priv = getBlob(data, o);
        byte[] x25519Pub  = getBlob(data, o);

        KeyFactory mf = KeyFactory.getInstance("ML-KEM", "BC");
        KeyPair mlkem = new KeyPair(
                mf.generatePublic(new X509EncodedKeySpec(mlkemPub)),
                mf.generatePrivate(new PKCS8EncodedKeySpec(mlkemPriv)));

        KeyFactory xf = KeyFactory.getInstance("X25519", "BC");
        KeyPair x = new KeyPair(
                xf.generatePublic(new X509EncodedKeySpec(x25519Pub)),
                xf.generatePrivate(new PKCS8EncodedKeySpec(x25519Priv)));

        return new Identity(mlkem, x);
    }

    /** This node's stable fingerprint = SHA-256(x25519Pub ‖ mlkemPub). */
    public static byte[] contactId(Identity id) {
        return contactId(id.x25519PubEnc(), id.mlkemPubEnc());
    }

    /** Contact id = SHA-256(x25519Pub ‖ mlkemPub) (both X509-encoded public keys). */
    public static byte[] contactId(byte[] x25519Pub, byte[] mlkemPub) {
        try {
            MessageDigest d = MessageDigest.getInstance("SHA-256");
            d.update(x25519Pub);
            d.update(mlkemPub);
            return d.digest();
        } catch (Exception e) {
            throw new RuntimeException("contactId failed: " + e, e);
        }
    }

    /** Pairing bundle = mlkemPub(X509) ‖ x25519Pub(X509) — the ~1250B blob exchanged during pairing. */
    public static byte[] bundle(Identity id) {
        return concat(id.mlkemPubEnc(), id.x25519PubEnc());
    }

    /** Split a pairing bundle into {mlkemPub, x25519Pub}; x25519 is the trailing {@link #X25519_PUB_LEN} bytes. */
    public static byte[][] splitBundle(byte[] bundle) {
        if (bundle == null || bundle.length <= X25519_PUB_LEN)
            throw new IllegalArgumentException("bundle too short: " + (bundle == null ? -1 : bundle.length));
        byte[] mlkemPub  = Arrays.copyOfRange(bundle, 0, bundle.length - X25519_PUB_LEN);
        byte[] x25519Pub = Arrays.copyOfRange(bundle, bundle.length - X25519_PUB_LEN, bundle.length);
        return new byte[][] { mlkemPub, x25519Pub };
    }

    /** Contact id derived from a peer's pairing bundle. */
    public static byte[] contactIdFromBundle(byte[] bundle) {
        byte[][] p = splitBundle(bundle);
        return contactId(p[1], p[0]); // (x25519Pub, mlkemPub)
    }

    /**
     * The 6-decimal-digit Short Authentication String, IDENTICAL on both peers because it hashes the two
     * bundles in lexicographic (unsigned) order so {seal,open} ordering is irrelevant:
     *   SHA-256("polleneus-sas-v0" ‖ lower(a,b) ‖ higher(a,b)), first 8 bytes mod 1_000_000, zero-padded.
     */
    public static String sas(byte[] a, byte[] b) {
        try {
            byte[] lo, hi;
            if (compareUnsigned(a, b) <= 0) { lo = a; hi = b; } else { lo = b; hi = a; }
            MessageDigest d = MessageDigest.getInstance("SHA-256");
            d.update("polleneus-sas-v0".getBytes(UTF8));
            d.update(lo);
            d.update(hi);
            byte[] h = d.digest();
            long v = 0;
            for (int i = 0; i < 8; i++) v = (v << 8) | (h[i] & 0xffL);
            v &= Long.MAX_VALUE;                 // force non-negative
            // Locale.ROOT (X5 port deviation, deliberate): default-locale %d can render
            // non-Latin digit glyphs — two phones in different locales would then SHOW
            // different-looking codes for the SAME SAS, sabotaging the human compare.
            return String.format(java.util.Locale.ROOT, "%06d", v % 1000000L);
        } catch (Exception e) {
            throw new RuntimeException("sas failed: " + e, e);
        }
    }

    /** Unsigned lexicographic byte-array comparison (shorter array sorts first on a common prefix). */
    public static int compareUnsigned(byte[] a, byte[] b) {
        int n = Math.min(a.length, b.length);
        for (int i = 0; i < n; i++) {
            int x = a[i] & 0xff, y = b[i] & 0xff;
            if (x != y) return x - y;
        }
        return a.length - b.length;
    }

    // ============================================================= COMMIT-BEFORE-REVEAL PAIRING (SAS hardening)
    //
    // Hardens the SAS against an ACTIVE wormhole MITM that could otherwise adaptively grind a substituted bundle
    // to force the two displayed 6-digit SASes to collide (~2^20 search, seconds). Both sides exchange a HASH
    // COMMITMENT to their identity bundle BEFORE either bundle is revealed (Vaudenay CRYPTO'05 / ZRTP RFC 6189
    // §4.2): a MITM must fix its substitution before seeing the real bundles, so per-attempt collision success
    // drops to 2^-20. The SAS now authenticates the two BUNDLES ONLY; the ML-KEM ciphertext rides on the
    // now-authenticated identities and is bound by an explicit KEY-CONFIRMATION (HMAC over K_pair). The K_pair /
    // K_auth derivation (deriveKpairPq) is UNCHANGED. See design-commit-before-reveal-pairing.md.

    /** Domain label for the bundle commitment hash. */
    public static final String DOMAIN_PAIR_COMMIT = "polleneus-pair-commit-v1";
    /** Domain label for the bundles-only SAS (distinct from the legacy {@code sas()} "polleneus-sas-v0"). */
    public static final String DOMAIN_PAIR_SAS    = "polleneus-pair-sas-v0";
    /** Domain label for the key-confirmation HMAC. */
    public static final String DOMAIN_PAIR_KC     = "polleneus-pair-kc-v1";
    /** SHA-256 commitment length. */
    public static final int PAIR_COMMIT_LEN = 32;
    /** HMAC-SHA-256 key-confirmation length. */
    public static final int PAIR_KC_LEN     = 32;

    /** Bundle commitment {@code C = SHA-256("polleneus-pair-commit-v1" ‖ bundle)} (32 B) — sent before the bundle. */
    public static byte[] commit(byte[] bundle) {
        try {
            MessageDigest d = MessageDigest.getInstance("SHA-256");
            d.update(DOMAIN_PAIR_COMMIT.getBytes(UTF8));
            d.update(bundle);
            return d.digest();
        } catch (Exception e) { throw new RuntimeException("commit failed: " + e, e); }
    }

    /** Constant-time check that {@code bundle} matches a previously-received {@code commitment}. */
    public static boolean verifyCommit(byte[] bundle, byte[] commitment) {
        if (bundle == null || commitment == null || commitment.length != PAIR_COMMIT_LEN) return false;
        return MessageDigest.isEqual(commit(bundle), commitment);
    }

    /**
     * The 6-digit SAS over the two IDENTITY BUNDLES ONLY (the ML-KEM ciphertext is NOT in the SAS):
     * <pre>
     *   SAS = decimal( be_uint( SHA-256("polleneus-pair-sas-v0" ‖ lower ‖ higher)[0..7] ) mod 10^6 )
     * </pre>
     * where {@code lower}/{@code higher} are the two FULL bundles ordered by their trailing x25519 public key
     * (unsigned-lexicographic, matching {@link #deriveKpair}/{@link #sas}), so BOTH roles compute the IDENTICAL
     * value regardless of who initiated.
     */
    public static String sasOverBundles(byte[] bundleA, byte[] bundleB) {
        try {
            byte[] xa = splitBundle(bundleA)[1];   // trailing X25519 pubkey
            byte[] xb = splitBundle(bundleB)[1];
            byte[] lo, hi;
            if (compareUnsigned(xa, xb) <= 0) { lo = bundleA; hi = bundleB; }
            else                              { lo = bundleB; hi = bundleA; }
            MessageDigest d = MessageDigest.getInstance("SHA-256");
            d.update(DOMAIN_PAIR_SAS.getBytes(UTF8));
            d.update(lo);
            d.update(hi);
            byte[] h = d.digest();
            long v = 0;
            for (int i = 0; i < 8; i++) v = (v << 8) | (h[i] & 0xffL);
            // Locale.ROOT: same deliberate deviation as sasFromKm — the SAS must render
            // identical glyphs on both phones regardless of device locale.
            return String.format(java.util.Locale.ROOT, "%06d", Long.remainderUnsigned(v, 1000000L));   // true be_uint mod 10^6
        } catch (Exception e) { throw new RuntimeException("sasOverBundles failed: " + e, e); }
    }

    /** Key-confirmation tag {@code kc = HMAC-SHA256(K_pair, "polleneus-pair-kc-v1" ‖ role)}; role = "I" / "R". */
    public static byte[] kc(byte[] kPair, String role) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(kPair, "HmacSHA256"));
            mac.update(DOMAIN_PAIR_KC.getBytes(UTF8));
            mac.update(role.getBytes(UTF8));
            return mac.doFinal();
        } catch (Exception e) { throw new RuntimeException("kc failed: " + e, e); }
    }

    /** Constant-time verify of a peer's key-confirmation tag for {@code role} under {@code kPair}. */
    public static boolean verifyKc(byte[] kPair, String role, byte[] tag) {
        if (kPair == null || tag == null || tag.length != PAIR_KC_LEN) return false;
        return MessageDigest.isEqual(kc(kPair, role), tag);
    }

    /** True iff every byte is zero (an all-zero X25519 shared secret == peer sent a low-order/identity point). */
    static boolean isAllZero(byte[] b) {
        int acc = 0;
        for (byte x : b) acc |= (x & 0xff);
        return acc == 0;
    }

    // ============================================================= DENIABLE SENDER AUTH (Phase 1 + Phase 2)
    //
    // Adds an authenticated-but-deniable "from": a paired recipient can verify WHICH contact sent a message
    // (and cannot transfer that proof — both peers hold the same symmetric key, so either could have forged
    // it). Construction per research-stop-2-memo.md §1: a STATIC PAIRWISE root key established at pairing,
    // domain-separated to a MAC key, used as an OUTER Encrypt-then-MAC (HMAC-SHA-256) over the existing
    // X-Wing + key-committing-AEAD sealed blob, with the sender's contactId carried INSIDE the seal.
    //
    // *** PHASE 2 — POST-QUANTUM KEY ESTABLISHMENT (this build). ***
    // K_pair now binds the X25519 static-static shared secret TOGETHER WITH a stored ML-KEM-768 shared secret
    // established by a one-time KEM-ciphertext exchange at pairing (memo §1.1/§2): the responder encapsulates
    // to the INITIATOR's ML-KEM-768 identity key and returns the ciphertext on the pairing READ; both peers
    // end up holding the SAME ss, so both derive an IDENTICAL K_pair that is post-quantum. See deriveKpairPq().
    // The classical X25519-only deriveKpair() is RETAINED only as a fallback for an old/no-ct peer (re-pair on
    // this build to upgrade a contact to PQ). The MAC primitive (HMAC-SHA-256) was already PQ-fine; now the
    // KEY ESTABLISHMENT leg is post-quantum too. Domain labels + the lower/higher ordering are UNCHANGED from
    // Phase 1 so the derivation stays symmetric across the initiator/responder roles.

    /** 32-byte outer Encrypt-then-MAC sender-auth tag appended to every wire blob. */
    public static final int SENDER_TAG_LEN = 32;
    /** Domain label for both the K_auth derivation and the MAC binding (memo §1.2 — HARD RULE: HMAC, never Poly1305/GMAC). */
    public static final String DOMAIN_SENDERAUTH = "polleneus-senderauth-v0";
    /** HKDF salt for the static-pairwise root key (memo §1.1). */
    static final String DOMAIN_PAIR = "polleneus-pair-v0";

    /**
     * Derive the static pairwise root key K_pair from the CLASSICAL (X25519 static-static) leg only (Phase 1):
     * <pre>
     *   K_pair = HKDF-SHA256( ikm  = X25519(my_x25519_priv, peer_x25519_pub),
     *                         salt = "polleneus-pair-v0",
     *                         info = lower(myX25519Pub, peerX25519Pub) ‖ higher(myX25519Pub, peerX25519Pub) )
     * </pre>
     * The public keys are ordered by unsigned-lexicographic min/max (mirroring {@link #sas}) so BOTH peers
     * derive the IDENTICAL key regardless of pairing role (initiator/responder). Inputs are the X509-encoded
     * X25519 public keys (44 B each), exactly as carried in the pairing bundle.
     *
     * NOTE: This CLASSICAL derivation is now a FALLBACK only (old/no-ct peer). The Phase-2 post-quantum path
     * {@link #deriveKpairPq} mixes in a stored ML-KEM-768 shared secret; prefer it whenever a ct is available.
     */
    public static byte[] deriveKpair(Identity me, byte[] peerX25519PubEnc) {
        try {
            PublicKey peerPub = KeyFactory.getInstance("X25519", "BC")
                    .generatePublic(new X509EncodedKeySpec(peerX25519PubEnc));
            byte[] ss = ecdh(me.x25519Priv(), peerPub);        // X25519 static-static (== libsodium crypto_box / Noise ss)
            if (isAllZero(ss)) throw new SecurityException("peer X25519 low-order/identity point (all-zero DH)"); // RFC 7748 §6.1
            byte[] myPub = me.x25519PubEnc();
            byte[] lo, hi;
            if (compareUnsigned(myPub, peerX25519PubEnc) <= 0) { lo = myPub; hi = peerX25519PubEnc; }
            else                                               { lo = peerX25519PubEnc; hi = myPub; }
            return hkdf(ss, DOMAIN_PAIR.getBytes(UTF8), concat(lo, hi), 32);
        } catch (Exception e) {
            throw new RuntimeException("deriveKpair failed: " + e, e);
        }
    }

    // ---------------------------------------------------------- Phase 2: ML-KEM leg for a POST-QUANTUM K_pair

    /** Result of an ML-KEM-768 encapsulation: the ciphertext (1088 B, sent to the peer) + the shared secret. */
    public static final class KemResult {
        public final byte[] ct;   // 1088 (ML-KEM-768 ciphertext)
        public final byte[] ss;   // 32  (shared secret)
        KemResult(byte[] ct, byte[] ss) { this.ct = ct; this.ss = ss; }
    }

    /**
     * ML-KEM-768 encapsulate to a peer's X509-encoded ML-KEM public key, using the SAME BouncyCastle path the
     * seal uses ({@code KeyGenerator "ML-KEM"} + {@link KEMGenerateSpec} -> {@link SecretKeyWithEncapsulation}).
     * Returns {@code {ct(1088), ss(32)}}. The responder calls this at pairing against the initiator's bundle pub.
     */
    public static KemResult kemEncapsulateTo(byte[] mlkemPubEncoded) {
        try {
            init();
            PublicKey pub = KeyFactory.getInstance("ML-KEM", "BC")
                    .generatePublic(new X509EncodedKeySpec(mlkemPubEncoded));
            KeyGenerator enc = KeyGenerator.getInstance("ML-KEM", "BC");
            enc.init(new KEMGenerateSpec(pub, "Secret"), new SecureRandom());
            SecretKeyWithEncapsulation out = (SecretKeyWithEncapsulation) enc.generateKey();
            return new KemResult(out.getEncapsulation(), out.getEncoded());
        } catch (Exception e) {
            throw new RuntimeException("kemEncapsulateTo failed: " + e, e);
        }
    }

    /**
     * ML-KEM-768 decapsulate a ciphertext with my private key, using the SAME BC path the open() uses
     * ({@link KEMExtractSpec}). Returns the 32-byte shared secret. The initiator calls this on the responder's
     * returned ciphertext to recover the SAME ss the responder holds.
     */
    public static byte[] kemDecapsulate(Identity me, byte[] ct) {
        try {
            init();
            KeyGenerator dec = KeyGenerator.getInstance("ML-KEM", "BC");
            dec.init(new KEMExtractSpec(me.mlkemPriv(), ct, "Secret"));
            return ((SecretKeyWithEncapsulation) dec.generateKey()).getEncoded();
        } catch (Exception e) {
            throw new RuntimeException("kemDecapsulate failed: " + e, e);
        }
    }

    /**
     * Phase 2 POST-QUANTUM pairwise root key — exactly {@link #deriveKpair} plus the stored ML-KEM-768 leg:
     * <pre>
     *   K_pair = HKDF-SHA256( ikm  = X25519(my_x25519_priv, peer_x25519_pub) ‖ mlkem_ss,   // X25519 leg FIRST
     *                         salt = "polleneus-pair-v0",
     *                         info = lower(myX25519Pub, peerX25519Pub) ‖ higher(myX25519Pub, peerX25519Pub) )
     * </pre>
     * The IKM order is FIXED (X25519 static-static ‖ ML-KEM ss). {@code mlkem_ss} is the single shared secret
     * BOTH peers hold (responder encapsulated it to the initiator's ML-KEM key; initiator decapsulated it), so
     * BOTH roles compute byte-identical K_pair. The salt + lower/higher(x25519Pub) info are IDENTICAL to the
     * Phase-1 classical {@link #deriveKpair}, keeping the derivation symmetric across initiator/responder.
     */
    public static byte[] deriveKpairPq(Identity me, byte[] peerX25519PubEnc, byte[] mlkemSs) {
        try {
            PublicKey peerPub = KeyFactory.getInstance("X25519", "BC")
                    .generatePublic(new X509EncodedKeySpec(peerX25519PubEnc));
            byte[] ssX = ecdh(me.x25519Priv(), peerPub);       // X25519 static-static (classical leg)
            if (isAllZero(ssX)) throw new SecurityException("peer X25519 low-order/identity point (all-zero DH)"); // RFC 7748 §6.1
            byte[] myPub = me.x25519PubEnc();
            byte[] lo, hi;
            if (compareUnsigned(myPub, peerX25519PubEnc) <= 0) { lo = myPub; hi = peerX25519PubEnc; }
            else                                               { lo = peerX25519PubEnc; hi = myPub; }
            byte[] ikm = concat(ssX, mlkemSs);                 // X25519 leg ‖ ML-KEM-768 ss (FIXED order)
            return hkdf(ikm, DOMAIN_PAIR.getBytes(UTF8), concat(lo, hi), 32);
        } catch (Exception e) {
            throw new RuntimeException("deriveKpairPq failed: " + e, e);
        }
    }

    /** Derive the MAC key: {@code K_auth = HKDF-SHA256(ikm=K_pair, salt="", info="polleneus-senderauth-v0")} (32 B). */
    public static byte[] kAuth(byte[] kPair) {
        return hkdf(kPair, new byte[0], DOMAIN_SENDERAUTH.getBytes(UTF8), 32);
    }

    /**
     * Outer sender-auth tag (Encrypt-then-MAC over the sealed blob):
     * {@code tag = HMAC-SHA256( K_auth, SHA-256(sealedBlob) ‖ "polleneus-senderauth-v0" )}.
     * The MAC is HMAC-SHA-256 (collision-resistant/committing); NEVER Poly1305/GMAC (partitioning-oracle risk).
     * {@code sealedBlob} is the INNER X-Wing/AEAD ciphertext (NOT the wire blob, which is sealedBlob ‖ tag).
     */
    public static byte[] senderTag(byte[] kAuth, byte[] sealedBlob) {
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256").digest(sealedBlob);
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(kAuth, "HmacSHA256"));
            mac.update(hash);
            mac.update(DOMAIN_SENDERAUTH.getBytes(UTF8));
            return mac.doFinal();
        } catch (Exception e) {
            throw new RuntimeException("senderTag failed: " + e, e);
        }
    }

    /** Constant-time verify of an outer sender-auth tag against a candidate contact's K_auth. */
    public static boolean verifySenderTag(byte[] kAuth, byte[] sealedBlob, byte[] tag) {
        if (kAuth == null || tag == null || tag.length != SENDER_TAG_LEN) return false;
        byte[] expect = senderTag(kAuth, sealedBlob);
        return MessageDigest.isEqual(expect, tag);   // constant-time compare
    }

    /** 32 cryptographically-random bytes — used as a byte-uniform filler tag when there is no K_auth
     *  (the fixed-recipient test path / a legacy contact). Indistinguishable on the wire from a real HMAC tag. */
    public static byte[] randomTag() {
        byte[] t = new byte[SENDER_TAG_LEN];
        new SecureRandom().nextBytes(t);
        return t;
    }

    // ============================================================= TTL / EPHEMERALITY (message expiry)
    //
    // A fixed 12-byte TTL header is PREPENDED to the WIRE blob, in front of the existing bytes:
    //     wire = [creation_ms : 8B big-endian][ttl_ms : 4B big-endian] ‖ sealed_blob ‖ tag
    //     id   = SHA-256(wire)
    // creation_ms = the sender's System.currentTimeMillis() at inject; ttl_ms = the chosen lifetime. Both are
    // SENDER-SET + IMMUTABLE (no per-hop mutation), so including them in the content-address id is correct.
    //
    // SECURITY LIMIT (DSA-02): the outer sender-auth tag binds the sealed_blob ONLY (see senderTag) — it does
    // NOT cover this TTL header. A malicious relay could therefore shorten/extend a message's TTL undetected.
    // This is the BASIC local-clock spike version; the hardened form (signed TTL + gossip-median clock +
    // hop-energy) is design P3/P5 and is OUT OF SCOPE here.

    /** Length of the prepended TTL header: 8B creation_ms (BE) + 4B ttl_ms (BE). */
    public static final int TTL_HDR_LEN = 12;

    /** Pack the 12-byte TTL header: creation_ms (8B big-endian) ‖ ttl_ms (4B big-endian). */
    public static byte[] packTtlHeader(long creationMs, int ttlMs) {
        byte[] h = new byte[TTL_HDR_LEN];
        for (int i = 7; i >= 0; i--) { h[i] = (byte) (creationMs & 0xff); creationMs >>>= 8; }
        h[8]  = (byte) (ttlMs >>> 24);
        h[9]  = (byte) (ttlMs >>> 16);
        h[10] = (byte) (ttlMs >>> 8);
        h[11] = (byte) (ttlMs);
        return h;
    }

    /** Read creation_ms (the leading 8B big-endian) from a wire blob's TTL header. */
    public static long ttlCreationMs(byte[] wire) {
        long v = 0;
        for (int i = 0; i < 8; i++) v = (v << 8) | (wire[i] & 0xffL);
        return v;
    }

    /** Read the raw ttl_ms (bytes 8..11 big-endian) from a wire blob's TTL header. Returned as a signed int;
     *  callers treat it as UNSIGNED (mask with 0xffffffffL) and range-validate before trusting it. */
    public static int ttlTtlMs(byte[] wire) {
        return ((wire[8] & 0xff) << 24) | ((wire[9] & 0xff) << 16)
             | ((wire[10] & 0xff) << 8) | (wire[11] & 0xff);
    }

    /** Prepend a 12-byte TTL header to a body ({@code sealed_blob ‖ tag}), producing the wire blob whose
     *  SHA-256 is the content-address id. */
    public static byte[] withTtlHeader(long creationMs, int ttlMs, byte[] body) {
        byte[] wire = new byte[TTL_HDR_LEN + body.length];
        byte[] h = packTtlHeader(creationMs, ttlMs);
        System.arraycopy(h, 0, wire, 0, TTL_HDR_LEN);
        System.arraycopy(body, 0, wire, TTL_HDR_LEN, body.length);
        return wire;
    }

    /** HKDF-SHA256 (RFC 5869). Empty/null salt defaults to HashLen zeros per the RFC. */
    static byte[] hkdf(byte[] ikm, byte[] salt, byte[] info, int len) {
        HKDFBytesGenerator g = new HKDFBytesGenerator(new SHA256Digest());
        g.init(new HKDFParameters(ikm, salt, info));
        byte[] out = new byte[len];
        g.generateBytes(out, 0, len);
        return out;
    }

    private static void putBlob(ByteArrayOutputStream bos, byte[] b) {
        int n = b.length;
        bos.write((n >>> 24) & 0xff); bos.write((n >>> 16) & 0xff);
        bos.write((n >>> 8) & 0xff);  bos.write(n & 0xff);
        bos.write(b, 0, n);
    }

    private static byte[] getBlob(byte[] data, int[] o) {
        int p = o[0];
        if (p + 4 > data.length) throw new IllegalArgumentException("truncated length");
        int n = ((data[p] & 0xff) << 24) | ((data[p + 1] & 0xff) << 16)
              | ((data[p + 2] & 0xff) << 8) | (data[p + 3] & 0xff);
        p += 4;
        if (n < 0 || p + n > data.length) throw new IllegalArgumentException("truncated blob len=" + n);
        byte[] out = Arrays.copyOfRange(data, p, p + n);
        o[0] = p + n;
        return out;
    }

    /** Generate an (ML-KEM-768, X25519) identity consuming randomness from {@code rnd}, ML-KEM then X25519. */
    static Identity identity(SecureRandom rnd) throws Exception {
        init();
        KeyPairGenerator mlkemKpg = KeyPairGenerator.getInstance("ML-KEM", "BC");
        mlkemKpg.initialize(MLKEMParameterSpec.ml_kem_768, rnd);
        KeyPair mlkem = mlkemKpg.generateKeyPair();

        KeyPairGenerator xKpg = KeyPairGenerator.getInstance("X25519", "BC");
        xKpg.initialize(255, rnd);   // BC: strength 255 -> X25519; consumes our (deterministic) randomness
        KeyPair x = xKpg.generateKeyPair();
        return new Identity(mlkem, x);
    }

    // ============================================================= seal / open

    /**
     * Seal {@code plaintext} to a recipient's public keys. Returns the sealed blob:
     * {@code mlkem_ct(1088) ‖ ephX25519_pub(44) ‖ commit(32) ‖ nonce(12) ‖ aead_ct}.
     */
    public static byte[] seal(byte[] recipMlkemPubEncoded, byte[] recipX25519PubEncoded, byte[] plaintext) {
        try {
            init();
            PublicKey recipMlkemPub = KeyFactory.getInstance("ML-KEM", "BC")
                    .generatePublic(new X509EncodedKeySpec(recipMlkemPubEncoded));
            PublicKey recipX25519Pub = KeyFactory.getInstance("X25519", "BC")
                    .generatePublic(new X509EncodedKeySpec(recipX25519PubEncoded));

            // ML-KEM-768 encapsulate to the recipient.
            KeyGenerator enc = KeyGenerator.getInstance("ML-KEM", "BC");
            enc.init(new KEMGenerateSpec(recipMlkemPub, "Secret"), new SecureRandom());
            SecretKeyWithEncapsulation encOut = (SecretKeyWithEncapsulation) enc.generateKey();
            byte[] ssM = encOut.getEncoded();
            byte[] ctM = encOut.getEncapsulation();          // 1088

            // Ephemeral X25519 -> ECDH with the recipient's static X25519 public key.
            KeyPair ephX = KeyPairGenerator.getInstance("X25519", "BC").generateKeyPair();
            byte[] ephPub = ephX.getPublic().getEncoded();   // 44
            byte[] ssX = ecdh(ephX.getPrivate(), recipX25519Pub);

            byte[] K = combine(ssM, ssX, ctM, ephPub);

            byte[] commit = MessageDigest.getInstance("SHA-256").digest(concat("commit".getBytes(UTF8), K));
            byte[] nonce = new byte[NONCE_LEN];
            new SecureRandom().nextBytes(nonce);
            Cipher c = Cipher.getInstance("ChaCha20-Poly1305", "BC");
            c.init(Cipher.ENCRYPT_MODE, new SecretKeySpec(K, "ChaCha20"), new IvParameterSpec(nonce));
            c.updateAAD(commit);
            byte[] aeadCt = c.doFinal(plaintext == null ? new byte[0] : plaintext);

            if (ctM.length != MLKEM_CT_LEN || ephPub.length != EPHX_PUB_LEN) {
                throw new IllegalStateException("unexpected field size ctM=" + ctM.length
                        + " ephPub=" + ephPub.length);
            }

            byte[] blob = new byte[HEADER_LEN + aeadCt.length];
            int o = 0;
            System.arraycopy(ctM,    0, blob, o, MLKEM_CT_LEN); o += MLKEM_CT_LEN;
            System.arraycopy(ephPub, 0, blob, o, EPHX_PUB_LEN); o += EPHX_PUB_LEN;
            System.arraycopy(commit, 0, blob, o, COMMIT_LEN);   o += COMMIT_LEN;
            System.arraycopy(nonce,  0, blob, o, NONCE_LEN);    o += NONCE_LEN;
            System.arraycopy(aeadCt, 0, blob, o, aeadCt.length);
            return blob;
        } catch (Exception e) {
            throw new RuntimeException("seal failed: " + e, e);
        }
    }

    /**
     * Trial-decrypt a sealed blob with {@code me}. Returns the plaintext if this node is the recipient,
     * or {@code null} on ANY failure (wrong recipient, malformed blob, commitment/AEAD reject). Never throws.
     */
    public static byte[] open(Identity me, byte[] sealed) {
        try {
            init();
            if (me == null || sealed == null || sealed.length < HEADER_LEN) return null;
            int o = 0;
            byte[] ctM    = Arrays.copyOfRange(sealed, o, o + MLKEM_CT_LEN); o += MLKEM_CT_LEN;
            byte[] ephPub = Arrays.copyOfRange(sealed, o, o + EPHX_PUB_LEN); o += EPHX_PUB_LEN;
            byte[] commit = Arrays.copyOfRange(sealed, o, o + COMMIT_LEN);   o += COMMIT_LEN;
            byte[] nonce  = Arrays.copyOfRange(sealed, o, o + NONCE_LEN);    o += NONCE_LEN;
            byte[] aeadCt = Arrays.copyOfRange(sealed, o, sealed.length);

            // ML-KEM-768 decapsulate (wrong private key -> implicit-rejection garbage ss, no exception).
            KeyGenerator dec = KeyGenerator.getInstance("ML-KEM", "BC");
            dec.init(new KEMExtractSpec(me.mlkemPriv(), ctM, "Secret"));
            byte[] ssM = ((SecretKeyWithEncapsulation) dec.generateKey()).getEncoded();

            // X25519 ECDH against the embedded ephemeral public key.
            PublicKey ephX = KeyFactory.getInstance("X25519", "BC")
                    .generatePublic(new X509EncodedKeySpec(ephPub));
            byte[] ssX = ecdh(me.x25519Priv(), ephX);

            byte[] K = combine(ssM, ssX, ctM, ephPub);

            byte[] expect = MessageDigest.getInstance("SHA-256").digest(concat("commit".getBytes(UTF8), K));
            if (!MessageDigest.isEqual(commit, expect)) return null;   // not for me (or tampered)

            Cipher c = Cipher.getInstance("ChaCha20-Poly1305", "BC");
            c.init(Cipher.DECRYPT_MODE, new SecretKeySpec(K, "ChaCha20"), new IvParameterSpec(nonce));
            c.updateAAD(commit);
            return c.doFinal(aeadCt);
        } catch (Exception e) {
            return null;
        }
    }

    // ============================================================= crypto primitives (verbatim from C3)

    static byte[] ecdh(PrivateKey p, PublicKey pub) throws Exception {
        KeyAgreement ka = KeyAgreement.getInstance("X25519", "BC");
        ka.init(p); ka.doPhase(pub, true); return ka.generateSecret();
    }

    static byte[] combine(byte[] ssM, byte[] ssX, byte[] ctM, byte[] ephPub) throws Exception {
        MessageDigest d = MessageDigest.getInstance("SHA3-256", "BC");
        d.update("polleneus-xwing-v0".getBytes(UTF8));
        d.update(ssM); d.update(ssX); d.update(ctM); d.update(ephPub);
        return d.digest();
    }

    static byte[] concat(byte[] a, byte[] b) {
        byte[] r = Arrays.copyOf(a, a.length + b.length);
        System.arraycopy(b, 0, r, a.length, b.length);
        return r;
    }

    // (H3) The deterministic-RNG helper that derived the world-known fixed recipient keypair has been removed
    // along with RECIPIENT_SEED / fixedRecipientIdentity(); production keys come only from a real CSPRNG.

    private Crypto() {}
}
