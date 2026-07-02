package com.polleneus.client.mesh.store;

import android.content.Context;
import android.content.pm.PackageManager;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyInfo;
import android.security.keystore.KeyProperties;
import android.security.keystore.StrongBoxUnavailableException;
import android.util.Log;

import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.GCMParameterSpec;

/**
 * H4: hardware-backed at-rest wrapping of the spike's key files (identity.dat / contacts.dat) with
 * ONE non-exportable AES-256-GCM key in AndroidKeyStore — StrongBox where the device has it
 * (measured: S21U Knox Vault backs the standard API; Tab A9+ is TEE-only), TEE otherwise.
 *
 * HONEST ATTACKER-MODEL BOUNDARY (do not overclaim — grounded in Research Stop #6, source-cited):
 *   - WIN: a seized powered-OFF / before-first-unlock device, or a pure off-device flash image
 *     (chip-off): files are ciphertext under BOTH file-based-encryption (LSKF-bound) AND a
 *     device-bound Keystore KEK whose material never leaves the SE/TEE — unattackable offline.
 *     Keystore wrapping adds DEVICE-binding + a filesystem-independent deletion point on top of the
 *     credential-bound FBE that app-internal storage already has; it does NOT raise credential-
 *     guessing cost.
 *   - NOT A WIN: a booted (after-first-unlock) device with the app's UID compromised (or root) can
 *     USE the key through Keystore exactly like we do — hardware backing prevents EXTRACTION of key
 *     material, not USE (no user-auth gate: the mesh must seal/relay/decrypt locked+screen-off in a
 *     pocket, so a wipe-on-lock / auth-required key is impossible here — by design).
 *   - EXTRACTION resistance is implementation- and PATCH-dependent, not absolute: Samsung TEE
 *     keyblob extractions (CVE-2021-25444 / -25490, S8..S21 class, patched 2021) broke the
 *     "can't extract" contract in the field. StrongBox/Knox Vault (isolated processor) is the
 *     mitigation class, not a guarantee.
 *
 * Threading: Keystore is thread-safe; ops are ms-scale (see the keystore probe results in
 * spike/keystoretest/results/ for the measured per-device medians) and happen only at load/save/panic
 * — fine on the calling thread for the spike.
 */
public final class Vault {
    static final String TAG = "MESH";
    static final String ALIAS = "polleneus-vault-v1";
    static final String STORE = "AndroidKeyStore";

    private final Context ctx;
    private boolean strongBox;      // whether the CURRENT key is StrongBox-backed (from KeyInfo)
    private SecretKey key;

    public Vault(Context ctx) { this.ctx = ctx; }

    /** Wrap plaintext for at-rest storage. aadName (the file's role, e.g. "identity.dat") is bound as
     *  GCM AAD so an envelope cannot be swapped between files. */
    public byte[] wrap(byte[] plain, String aadName) throws Exception {
        SecretKey k = ensureKey();
        Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
        c.init(Cipher.ENCRYPT_MODE, k);
        c.updateAAD(aadName.getBytes("UTF-8"));
        byte[] ct = c.doFinal(plain);
        return VaultFormat.pack(strongBox ? VaultFormat.FLAG_STRONGBOX : 0, c.getIV(), ct);
    }

    /** Unwrap an envelope. Throws on tamper/wrong-key/wrong-file (GCM auth failure). */
    public byte[] unwrap(byte[] envelope, String aadName) throws Exception {
        VaultFormat.Parsed p = VaultFormat.parse(envelope);
        SecretKey k = ensureKey();
        Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
        c.init(Cipher.DECRYPT_MODE, k, new GCMParameterSpec(128, p.iv));
        c.updateAAD(aadName.getBytes("UTF-8"));
        return c.doFinal(p.ct);
    }

    /** PANIC: delete the wrapping key (deleteEntry). This REVOKES the OS-side software copy of the key
     *  behind a device-bound KEK — every wrapped file becomes unreadable BY THIS RUNNING SYSTEM (deleteEntry
     *  is a fast Keystore op — per-device latency in the probe results), and there is no in-app copy of the
     *  wrap key to recover. HONEST LIMIT (RS#6, load-bearing): this is NOT a GUARANTEED flash-level crypto-erase — the
     *  public API cannot request KeyMint ROLLBACK_RESISTANCE, so the spec attaches no required destructive
     *  effect to deleting an untagged key, and a stale keyblob copy can survive on FTL flash. An adversary
     *  who imaged the flash BEFORE the panic AND later obtains code execution on the SAME intact device
     *  could in principle replay the blob and revive the key; a pure off-device flash image cannot (the blob
     *  is ciphertext under the in-SE/TEE KEK). Whether a given vendor actually erases the blob-wrapping
     *  material on delete is UNKNOWN without a rooted restore-after-delete test (M-FS3, unrunnable on the
     *  stock lab devices — documented residual). The file overwrite-then-delete in panicWipe() is the belt to
     *  this suspenders. A fresh key is minted lazily on the next wrap. */
    public synchronized void eraseKey() {   // synchronized: publishes key=null under the same monitor as ensureKey (H4-LC3)
        try {
            KeyStore ks = KeyStore.getInstance(STORE);
            ks.load(null);
            ks.deleteEntry(ALIAS);
            key = null;
            Log.w(TAG, "VAULT wrap-key deleted (OS-side revoke; was " + levelName()
                    + "). NOT a guaranteed flash-erase — see Vault.eraseKey doc.");
        } catch (Exception e) {
            Log.e(TAG, "VAULT erase failed: " + e);
        }
    }

    public String levelName() { return strongBox ? "STRONGBOX" : "TEE"; }

    private synchronized SecretKey ensureKey() throws Exception {
        if (key != null) return key;
        KeyStore ks = KeyStore.getInstance(STORE);
        ks.load(null);
        if (ks.containsAlias(ALIAS)) {
            key = (SecretKey) ks.getKey(ALIAS, null);
            strongBox = readBackStrongBox(key);
            return key;
        }
        boolean wantSb = ctx.getPackageManager().hasSystemFeature(PackageManager.FEATURE_STRONGBOX_KEYSTORE);
        if (wantSb) {
            try {
                key = genKey(true);
            } catch (Exception e) {
                // H4-LC2: some OEMs throw a generic ProviderException/KeyStoreException (not
                // StrongBoxUnavailableException) on StrongBox keygen. ANY StrongBox failure -> TEE fallback,
                // so a StrongBox hiccup can never leave us unable to persist a wrap key.
                Log.w(TAG, "VAULT StrongBox keygen failed (" + e.getClass().getSimpleName()
                        + ") -> TEE fallback");
                key = genKey(false);
            }
        } else {
            key = genKey(false);
        }
        strongBox = readBackStrongBox(key);
        Log.i(TAG, "VAULT key created backend=" + levelName());
        return key;
    }

    private SecretKey genKey(boolean sb) throws Exception {
        KeyGenParameterSpec.Builder b = new KeyGenParameterSpec.Builder(ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256);
        // Deliberately NO setUserAuthenticationRequired / setUnlockedDeviceRequired: the mesh seals,
        // relays, and decrypts while the phone is locked in a pocket. Trade-off documented above.
        if (sb) b.setIsStrongBoxBacked(true);
        KeyGenerator kg = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, STORE);
        kg.init(b.build());
        return kg.generateKey();
    }

    /** Ground truth from KeyInfo (never trust our own request flags). */
    private boolean readBackStrongBox(SecretKey k) {
        try {
            SecretKeyFactory f = SecretKeyFactory.getInstance(k.getAlgorithm(), STORE);
            KeyInfo info = (KeyInfo) f.getKeySpec(k, KeyInfo.class);
            if (android.os.Build.VERSION.SDK_INT >= 31) {
                return info.getSecurityLevel() == KeyProperties.SECURITY_LEVEL_STRONGBOX;
            }
            return false;   // pre-31 can't distinguish StrongBox from TEE via KeyInfo; log-only anyway
        } catch (Exception e) {
            return false;
        }
    }
}
