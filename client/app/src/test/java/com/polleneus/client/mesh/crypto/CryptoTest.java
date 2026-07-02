package com.polleneus.client.mesh.crypto;

import static org.junit.Assert.assertArrayEquals;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import org.junit.BeforeClass;
import org.junit.Test;

import java.nio.charset.StandardCharsets;

/**
 * JVM verification of the ported crypto — the point of Crypto.java being pure Java (spike design).
 * These tests exercise the exact properties the pairing ceremony and sealed envelope depend on;
 * they run in CI on every push. The port is verbatim from the hardware-validated spike (package
 * rename only), so green here = the client carries the same primitives the mission test used.
 */
public class CryptoTest {

    static Crypto.Identity alice;
    static Crypto.Identity bob;

    @BeforeClass
    public static void keys() {
        alice = Crypto.randomIdentity();
        bob = Crypto.randomIdentity();
    }

    // ---- identity persistence ----

    @Test
    public void identityEncodeDecodeRoundTrip() throws Exception {
        byte[] enc = Crypto.encodeIdentity(alice);
        Crypto.Identity back = Crypto.decodeIdentity(enc);
        assertArrayEquals(Crypto.contactId(alice), Crypto.contactId(back));
        assertArrayEquals(alice.x25519PubEnc(), back.x25519PubEnc());
        assertArrayEquals(alice.mlkemPubEnc(), back.mlkemPubEnc());
    }

    @Test(expected = Exception.class)
    public void identityDecodeRejectsCorruption() throws Exception {
        byte[] enc = Crypto.encodeIdentity(alice);
        byte[] cut = java.util.Arrays.copyOf(enc, enc.length / 2);
        Crypto.decodeIdentity(cut);
    }

    // ---- contact id + bundle ----

    @Test
    public void contactIdIsStableAndBundleDerivedMatches() {
        byte[] direct = Crypto.contactId(alice);
        byte[] viaBundle = Crypto.contactIdFromBundle(Crypto.bundle(alice));
        assertArrayEquals(direct, viaBundle);
        assertEquals(32, direct.length);
    }

    @Test
    public void bundleSplitsIntoMlkemAndX25519() {
        byte[] bundle = Crypto.bundle(alice);
        byte[][] parts = Crypto.splitBundle(bundle);
        assertArrayEquals(alice.mlkemPubEnc(), parts[0]);
        assertArrayEquals(alice.x25519PubEnc(), parts[1]);
        assertEquals(Crypto.X25519_PUB_LEN, parts[1].length);
    }

    // ---- commit-before-reveal ----

    @Test
    public void commitVerifiesOwnBundleAndRejectsSubstitution() {
        byte[] bundleA = Crypto.bundle(alice);
        byte[] c = Crypto.commit(bundleA);
        assertTrue(Crypto.verifyCommit(bundleA, c));
        assertFalse("a substituted bundle must not match the commitment",
                Crypto.verifyCommit(Crypto.bundle(bob), c));
    }

    // ---- SAS ----

    @Test
    public void sasOverBundlesIsSymmetricAndSixDigits() {
        byte[] a = Crypto.bundle(alice);
        byte[] b = Crypto.bundle(bob);
        String s1 = Crypto.sasOverBundles(a, b);
        String s2 = Crypto.sasOverBundles(b, a);   // responder computes with args swapped
        assertEquals("both roles must display the identical SAS", s1, s2);
        assertTrue("SAS is exactly 6 decimal digits", s1.matches("\\d{6}"));
    }

    @Test
    public void sasChangesWhenABundleIsSubstituted() {
        String honest = Crypto.sasOverBundles(Crypto.bundle(alice), Crypto.bundle(bob));
        Crypto.Identity mitm = Crypto.randomIdentity();
        String attacked = Crypto.sasOverBundles(Crypto.bundle(alice), Crypto.bundle(mitm));
        assertFalse("substitution must (overwhelmingly) change the SAS", honest.equals(attacked));
    }

    // ---- PQ pairwise key: both roles derive the identical K_pair ----

    @Test
    public void deriveKpairPqIsRoleSymmetric() {
        // responder (bob) encapsulates to the initiator's (alice's) ML-KEM identity key
        Crypto.KemResult enc = Crypto.kemEncapsulateTo(alice.mlkemPubEnc());
        // initiator decapsulates the returned ct -> same ss
        byte[] ssAlice = Crypto.kemDecapsulate(alice, enc.ct);
        assertArrayEquals(enc.ss, ssAlice);

        byte[] kAlice = Crypto.deriveKpairPq(alice, bob.x25519PubEnc(), ssAlice);
        byte[] kBob = Crypto.deriveKpairPq(bob, alice.x25519PubEnc(), enc.ss);
        assertArrayEquals("initiator and responder must hold byte-identical K_pair", kAlice, kBob);
        assertEquals(32, kAlice.length);
    }

    @Test
    public void keyConfirmationVerifiesPerRoleAndRejectsWrongKey() {
        Crypto.KemResult enc = Crypto.kemEncapsulateTo(alice.mlkemPubEnc());
        byte[] k = Crypto.deriveKpairPq(alice, bob.x25519PubEnc(), Crypto.kemDecapsulate(alice, enc.ct));
        byte[] tagI = Crypto.kc(k, "I");
        assertTrue(Crypto.verifyKc(k, "I", tagI));
        assertFalse("role mixup must fail", Crypto.verifyKc(k, "R", tagI));
        byte[] wrong = Crypto.deriveKpair(alice, bob.x25519PubEnc()); // classical-only ≠ PQ K_pair
        assertFalse(Crypto.verifyKc(wrong, "I", tagI));
    }

    // ---- deniable sender auth ----

    @Test
    public void senderTagVerifiesAndRejectsTamper() {
        Crypto.KemResult enc = Crypto.kemEncapsulateTo(alice.mlkemPubEnc());
        byte[] kPair = Crypto.deriveKpairPq(alice, bob.x25519PubEnc(), Crypto.kemDecapsulate(alice, enc.ct));
        byte[] kAuth = Crypto.kAuth(kPair);

        byte[] blob = "sealed-bytes-stand-in".getBytes(StandardCharsets.UTF_8);
        byte[] tag = Crypto.senderTag(kAuth, blob);
        assertTrue(Crypto.verifySenderTag(kAuth, blob, tag));

        byte[] tampered = blob.clone();
        tampered[0] ^= 1;
        assertFalse(Crypto.verifySenderTag(kAuth, tampered, tag));
    }

    // ---- sealed envelope ----

    @Test
    public void sealOpenRoundTripAndWrongRecipientGetsNull() {
        byte[] msg = "Extra batteries and a radio at Mia's.".getBytes(StandardCharsets.UTF_8);
        byte[] sealed = Crypto.seal(bob.mlkemPubEnc(), bob.x25519PubEnc(), msg);

        assertTrue(sealed.length >= Crypto.HEADER_LEN + 16);
        assertArrayEquals(msg, Crypto.open(bob, sealed));
        assertNull("a non-recipient must get null, never an exception", Crypto.open(alice, sealed));

        byte[] flipped = sealed.clone();
        flipped[sealed.length - 1] ^= 1;   // corrupt the AEAD tag
        assertNull(Crypto.open(bob, flipped));
    }

    // ---- TTL header ----

    @Test
    public void ttlHeaderPacksAndReadsBack() {
        long creation = 1_751_450_000_000L;
        int ttl = 172_800_000; // 2 days — the design default
        byte[] wire = Crypto.withTtlHeader(creation, ttl, new byte[] {1, 2, 3});
        assertEquals(creation, Crypto.ttlCreationMs(wire));
        assertEquals(ttl, Crypto.ttlTtlMs(wire));
        assertEquals(Crypto.TTL_HDR_LEN + 3, wire.length);
    }

    @Test
    public void randomTagHasSenderTagLength() {
        assertEquals(Crypto.SENDER_TAG_LEN, Crypto.randomTag().length);
        assertNotNull(Crypto.randomTag());
    }
}
