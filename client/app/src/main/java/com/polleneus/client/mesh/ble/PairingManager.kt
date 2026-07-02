package com.polleneus.client.mesh.ble

import android.annotation.SuppressLint
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattServer
import android.bluetooth.BluetoothGattServerCallback
import android.bluetooth.BluetoothGattService
import android.bluetooth.BluetoothManager
import android.bluetooth.BluetoothProfile
import android.bluetooth.le.AdvertiseCallback
import android.bluetooth.le.AdvertiseData
import android.bluetooth.le.AdvertiseSettings
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.os.Handler
import android.os.HandlerThread
import android.os.ParcelUuid
import android.util.Log
import com.polleneus.client.mesh.crypto.Crypto
import java.util.UUID

/**
 * The commit-before-reveal pairing ceremony over BLE GATT — the client build of the spike's
 * hardened protocol (spike/design-commit-before-reveal-pairing.md; Vaudenay CRYPTO'05 / ZRTP
 * RFC 6189 §4.2). All security decisions live in Crypto.java (ported verbatim, JVM-tested);
 * this class is transport + sequencing, and the SEQUENCE is the security-relevant part:
 *
 *   1. COMMIT  — both sides exchange SHA-256 commitments to their identity bundles
 *                BEFORE either bundle is revealed (kills adaptive SAS grinding).
 *   2. REVEAL  — bundles exchanged; each side verifies the peer's bundle against the
 *                commitment received in (1). Mismatch = abort, nothing persisted.
 *   3. CT      — responder ML-KEM-encapsulates to the initiator's (verified) key.
 *   4. KC      — both derive the PQ K_pair and exchange role-tagged key confirmations.
 *   5. SAS     — the 6-digit code over the two bundles is handed to the HUMANS; the app
 *                persists PENDING on kc-verify, and only the human match makes it sendable
 *                (that flip happens in the ContactStore, not here).
 *
 * Roles: both sides advertise PAIR_SVC with an 8-byte tiebreak token (contactId prefix);
 * the LOWER token becomes the initiator/central. Both phones compute the same answer.
 *
 * Wire framing per GATT op: [round:1][totalLen:4 BE][offset:4 BE][chunk<=180] — the spike's
 * proven chunk size. UUIDs are client-v1 (distinct from the spike's, so a stray spike node
 * in the lab can't interfere with a client ceremony).
 */
@SuppressLint("MissingPermission") // every entry point is permission-gated by the UI layer
class PairingManager(
    ctx: Context,
    private val identity: Crypto.Identity,
    myContactId: ByteArray,
    private val onEvent: (Event) -> Unit,
) {
    sealed interface Event {
        data class PeerFound(val peerToken: String) : Event
        /** All machine steps done on this side; hand the SAS to the human. */
        data class KcVerified(
            val idHex: String,
            val peerBundle: ByteArray,
            val kPair: ByteArray,
            val pq: Boolean,
            val sas: String,
        ) : Event
        /** security=true means a commitment/key-confirmation check failed (possible interception);
         *  security=false means a transport hiccup (glitch/timeout) — never cry "interception" for that. */
        data class Failed(val reason: String, val security: Boolean) : Event
    }

    companion object {
        private const val TAG = "PN-PAIR"
        val PAIR_SVC: UUID = UUID.fromString("0000b1b3-0000-1000-8000-00805f9b34fb")
        val SVC: UUID = UUID.fromString("0000b1c2-0000-1000-8000-00805f9b34fb")
        val CHR_PAIR: UUID = UUID.fromString("0000b1c4-0000-1000-8000-00805f9b34fb")

        private const val TOKEN_LEN = 8
        private const val HDR = 9              // [round:1][totalLen:4][offset:4]
        private const val CHUNK = 180          // spike-validated frame payload
        private const val MAX_MSG = 8 * 1024
        private const val CEREMONY_TIMEOUT_MS = 45_000L

        private const val R_COMMIT = 1
        private const val R_REVEAL = 2
        private const val R_CT = 3
        private const val R_KC = 4

        fun tokenHex(b: ByteArray): String = b.joinToString("") { "%02x".format(it) }
    }

    private val app = ctx.applicationContext
    private val btMgr = app.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
    private val adapter = btMgr.adapter

    private val thread = HandlerThread("pn-pairing").also { it.start() }
    private val handler = Handler(thread.looper)

    private val myToken = myContactId.copyOf(TOKEN_LEN)
    private val myBundle = Crypto.bundle(identity)

    private var advertising = false
    private var scanning = false
    private var gattServer: BluetoothGattServer? = null
    private var centralGatt: BluetoothGatt? = null
    private var active = false
    private var peerDevice: BluetoothDevice? = null
    private var peerToken: ByteArray? = null
    private var ceremonyRunning = false

    // ---------------- lifecycle ----------------

    fun start() {
        handler.post {
            if (active) return@post
            active = true
            startServer()
            startAdvertising()
            startScan()
            Log.i(TAG, "pairing mode ON token=${tokenHex(myToken)}")
        }
    }

    fun stop() {
        handler.post {
            active = false
            ceremonyRunning = false
            try { adapter.bluetoothLeScanner?.stopScan(scanCb) } catch (_: Exception) { }
            scanning = false
            try { adapter.bluetoothLeAdvertiser?.stopAdvertising(advCb) } catch (_: Exception) { }
            advertising = false
            try { centralGatt?.disconnect(); centralGatt?.close() } catch (_: Exception) { }
            centralGatt = null
            try { gattServer?.close() } catch (_: Exception) { }
            gattServer = null
            peerDevice = null
            peerToken = null
            serverState = null
            Log.i(TAG, "pairing mode OFF")
        }
    }

    /** The human tapped "Begin key exchange". Only the lower-token side actually drives. */
    fun beginExchange() {
        handler.post {
            val dev = peerDevice ?: return@post
            val pt = peerToken ?: return@post
            if (ceremonyRunning) return@post
            val iAmInitiator = Crypto.compareUnsigned(myToken, pt) <= 0
            if (!iAmInitiator) {
                Log.i(TAG, "responder role — waiting for the peer to connect")
                return@post // peripheral: the ceremony arrives via the GATT server
            }
            ceremonyRunning = true
            armTimeout()
            Log.i(TAG, "initiator role — connecting to ${dev.address}")
            centralGatt = dev.connectGatt(app, false, centralCb, BluetoothDevice.TRANSPORT_LE)
        }
    }

    private fun fail(reason: String) = abort(reason, security = false)
    private fun securityAbort(reason: String) = abort(reason, security = true)

    private fun abort(reason: String, security: Boolean) {
        Log.w(TAG, "ceremony ${if (security) "SECURITY-ABORT" else "FAILED"}: $reason")
        ceremonyRunning = false
        try { centralGatt?.disconnect(); centralGatt?.close() } catch (_: Exception) { }
        centralGatt = null
        serverState = null
        onEvent(Event.Failed(reason, security))
    }

    private fun armTimeout() {
        handler.postDelayed({
            if (ceremonyRunning) fail("timed out — move the phones closer and try again")
        }, CEREMONY_TIMEOUT_MS)
    }

    // ---------------- advertise + scan (both roles) ----------------

    private val advCb = object : AdvertiseCallback() {
        override fun onStartSuccess(s: AdvertiseSettings) { Log.i(TAG, "advertising OK") }
        override fun onStartFailure(e: Int) { Log.e(TAG, "advertise FAIL code=$e") }
    }

    private fun startAdvertising() {
        val adv = adapter.bluetoothLeAdvertiser ?: run { fail("BLE advertising unavailable"); return }
        val settings = AdvertiseSettings.Builder()
            .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
            .setConnectable(true)
            .build()
        val data = AdvertiseData.Builder()
            .addServiceUuid(ParcelUuid(PAIR_SVC))
            .addServiceData(ParcelUuid(PAIR_SVC), myToken)
            .setIncludeDeviceName(false)
            .build()
        adv.startAdvertising(settings, data, advCb)
        advertising = true
    }

    private val scanCb = object : ScanCallback() {
        override fun onScanResult(type: Int, r: ScanResult) {
            handler.post { onScan(r) }
        }
        override fun onScanFailed(e: Int) { Log.e(TAG, "scan FAIL code=$e") }
    }

    private fun startScan() {
        val scanner = adapter.bluetoothLeScanner ?: run { fail("BLE scanning unavailable"); return }
        val filter = ScanFilter.Builder().setServiceUuid(ParcelUuid(PAIR_SVC)).build()
        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY) // interactive, screen-on ceremony
            .build()
        scanner.startScan(listOf(filter), settings, scanCb)
        scanning = true
    }

    private fun onScan(r: ScanResult) {
        if (!active || peerDevice != null) return
        val sd = r.scanRecord?.getServiceData(ParcelUuid(PAIR_SVC)) ?: return
        if (sd.size < TOKEN_LEN) return
        val token = sd.copyOf(TOKEN_LEN)
        if (token.contentEquals(myToken)) return
        peerDevice = r.device
        peerToken = token
        Log.i(TAG, "peer found addr=${r.device.address} token=${tokenHex(token)} rssi=${r.rssi}")
        onEvent(Event.PeerFound(tokenHex(token)))
    }

    // ---------------- framing ----------------

    private fun frame(round: Int, msg: ByteArray, offset: Int): ByteArray {
        val n = minOf(CHUNK, msg.size - offset)
        val f = ByteArray(HDR + n)
        f[0] = round.toByte()
        var len = msg.size
        for (i in 4 downTo 1) { f[i] = (len and 0xff).toByte(); len = len ushr 8 }
        var off = offset
        for (i in 8 downTo 5) { f[i] = (off and 0xff).toByte(); off = off ushr 8 }
        System.arraycopy(msg, offset, f, HDR, n)
        return f
    }

    private class Reassembly {
        var round = 0
        var total = -1
        var buf = ByteArray(0)
        var got = 0
        fun accept(f: ByteArray): ByteArray? { // returns completed msg or null
            if (f.size < HDR) return null
            val r = f[0].toInt()
            var len = 0; for (i in 1..4) len = (len shl 8) or (f[i].toInt() and 0xff)
            var off = 0; for (i in 5..8) off = (off shl 8) or (f[i].toInt() and 0xff)
            if (len < 0 || len > MAX_MSG) return null
            if (r != round || total == -1) { round = r; total = len; buf = ByteArray(len); got = 0 }
            val n = f.size - HDR
            if (off + n > total) return null
            System.arraycopy(f, HDR, buf, off, n)
            got = off + n
            return if (got >= total) { val out = buf; total = -1; out } else null
        }
    }

    // ---------------- central / initiator ----------------

    private var cReasm = Reassembly()
    private var cStage = 0
    private var cOutMsg: ByteArray = ByteArray(0)
    private var cOutRound = 0
    private var cOutOff = 0
    private var peerCommit: ByteArray? = null
    private var peerBundle: ByteArray? = null
    private var kPairC: ByteArray? = null

    private val centralCb = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
            handler.post {
                if (newState == BluetoothProfile.STATE_CONNECTED) {
                    g.requestMtu(517)
                } else if (newState == BluetoothProfile.STATE_DISCONNECTED && ceremonyRunning) {
                    fail("connection lost")
                }
            }
        }
        override fun onMtuChanged(g: BluetoothGatt, mtu: Int, status: Int) {
            handler.post { g.discoverServices() }
        }
        override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
            handler.post {
                val chr = g.getService(SVC)?.getCharacteristic(CHR_PAIR)
                    ?: return@post fail("peer has no pairing service")
                // stage 0: send our COMMIT
                cReasm = Reassembly(); cStage = 0
                peerCommit = null; peerBundle = null; kPairC = null
                sendMsg(g, chr, R_COMMIT, Crypto.commit(myBundle))
            }
        }
        override fun onCharacteristicWrite(g: BluetoothGatt, chr: BluetoothGattCharacteristic, status: Int) {
            handler.post {
                if (status != BluetoothGatt.GATT_SUCCESS) return@post fail("write failed ($status)")
                if (cOutOff < cOutMsg.size) { writeNext(g, chr) } else { g.readCharacteristic(chr) }
            }
        }
        @Suppress("DEPRECATION")
        override fun onCharacteristicRead(g: BluetoothGatt, chr: BluetoothGattCharacteristic, status: Int) {
            handler.post {
                if (status != BluetoothGatt.GATT_SUCCESS) return@post fail("read failed ($status)")
                val msg = cReasm.accept(chr.value ?: ByteArray(0))
                if (msg == null) { g.readCharacteristic(chr); return@post }
                onCentralMsg(g, chr, msg)
            }
        }
    }

    @Suppress("DEPRECATION")
    private fun writeNext(g: BluetoothGatt, chr: BluetoothGattCharacteristic) {
        val f = frame(cOutRound, cOutMsg, cOutOff)
        cOutOff += f.size - HDR
        chr.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
        chr.value = f
        g.writeCharacteristic(chr)
    }

    private fun sendMsg(g: BluetoothGatt, chr: BluetoothGattCharacteristic, round: Int, msg: ByteArray) {
        cOutMsg = msg; cOutRound = round; cOutOff = 0
        writeNext(g, chr)
    }

    private fun onCentralMsg(g: BluetoothGatt, chr: BluetoothGattCharacteristic, msg: ByteArray) {
        when (cStage) {
            0 -> { // got peer COMMIT
                if (msg.size != Crypto.PAIR_COMMIT_LEN) return fail("bad commitment")
                peerCommit = msg
                cStage = 1
                sendMsg(g, chr, R_REVEAL, myBundle)
            }
            1 -> { // got peer REVEAL
                if (!Crypto.verifyCommit(msg, peerCommit)) {
                    return securityAbort("peer bundle does not match its commitment — possible interference")
                }
                peerBundle = msg
                cStage = 2
                g.readCharacteristic(chr) // pull the CT
            }
            2 -> { // got CT
                val pb = peerBundle ?: return fail("state error")
                val ss = try { Crypto.kemDecapsulate(identity, msg) } catch (e: Exception) {
                    return fail("decapsulation failed")
                }
                val peerX = Crypto.splitBundle(pb)[1]
                val k = try { Crypto.deriveKpairPq(identity, peerX, ss) } catch (e: Exception) {
                    return fail("key derivation failed: ${e.message}")
                }
                kPairC = k
                cStage = 3
                sendMsg(g, chr, R_KC, Crypto.kc(k, "I"))
            }
            3 -> { // got peer KC
                val k = kPairC ?: return fail("state error")
                val pb = peerBundle ?: return fail("state error")
                if (!Crypto.verifyKc(k, "R", msg)) return securityAbort("key confirmation failed — keys diverged")
                ceremonyRunning = false
                val sas = Crypto.sasOverBundles(myBundle, pb)
                Log.i(TAG, "ceremony complete (initiator) sas=$sas")
                onEvent(Event.KcVerified(ContactHex.of(pb), pb, k, pq = true, sas = sas))
                try { g.disconnect(); g.close() } catch (_: Exception) { }
                centralGatt = null
            }
        }
    }

    // ---------------- peripheral / responder ----------------

    private class ServerState {
        var deviceAddr: String? = null   // bind to one central; ignore ambient BLE noise
        val reasm = Reassembly()
        var stage = 0
        var outMsg: ByteArray = ByteArray(0)
        var outRound = 0
        var outOff = 0
        var peerCommit: ByteArray? = null
        var peerBundle: ByteArray? = null
        var kPair: ByteArray? = null
        var kcServed = false
    }

    private var serverState: ServerState? = null

    private fun startServer() {
        val server = btMgr.openGattServer(app, serverCb) ?: run { fail("GATT server unavailable"); return }
        val svc = BluetoothGattService(SVC, BluetoothGattService.SERVICE_TYPE_PRIMARY)
        svc.addCharacteristic(
            BluetoothGattCharacteristic(
                CHR_PAIR,
                BluetoothGattCharacteristic.PROPERTY_READ or BluetoothGattCharacteristic.PROPERTY_WRITE,
                BluetoothGattCharacteristic.PERMISSION_READ or BluetoothGattCharacteristic.PERMISSION_WRITE,
            ),
        )
        server.addService(svc)
        gattServer = server
    }

    private val serverCb = object : BluetoothGattServerCallback() {
        override fun onConnectionStateChange(d: BluetoothDevice, status: Int, newState: Int) {
            handler.post {
                if (newState == BluetoothProfile.STATE_CONNECTED) {
                    val cur = serverState
                    if (cur != null && cur.stage > 0) {
                        // a real ceremony is already underway with someone else — ignore ambient noise
                        Log.i(TAG, "ignoring extra central ${d.address} — ceremony busy")
                        return@post
                    }
                    // prepare, but do NOT arm the ceremony until a real COMMIT actually arrives.
                    // Ambient BLE centrals probe-connect constantly; they never send a valid COMMIT.
                    serverState = ServerState().also { it.deviceAddr = d.address }
                    Log.i(TAG, "central connected ${d.address} (awaiting commit)")
                } else if (newState == BluetoothProfile.STATE_DISCONNECTED) {
                    val s = serverState ?: return@post
                    if (s.deviceAddr != d.address) return@post
                    if (s.stage > 0 && !s.kcServed && ceremonyRunning) {
                        fail("the other phone disconnected before finishing")   // transport, not security
                    } else {
                        serverState = null   // pre-ceremony connection noise — silent, no UI event
                    }
                }
            }
        }

        override fun onCharacteristicWriteRequest(
            d: BluetoothDevice, reqId: Int, chr: BluetoothGattCharacteristic,
            prep: Boolean, respond: Boolean, offset: Int, value: ByteArray,
        ) {
            handler.post {
                if (respond) gattServer?.sendResponse(d, reqId, BluetoothGatt.GATT_SUCCESS, 0, null)
                val s = serverState ?: return@post
                if (s.deviceAddr != null && s.deviceAddr != d.address) return@post   // ignore other centrals
                val msg = s.reasm.accept(value) ?: return@post
                onServerMsg(s, msg)
            }
        }

        override fun onCharacteristicReadRequest(
            d: BluetoothDevice, reqId: Int, offset: Int, chr: BluetoothGattCharacteristic,
        ) {
            handler.post {
                val s = serverState
                if (s == null || s.outMsg.isEmpty() || (s.deviceAddr != null && s.deviceAddr != d.address)) {
                    gattServer?.sendResponse(d, reqId, BluetoothGatt.GATT_SUCCESS, 0, ByteArray(0))
                    return@post
                }
                val f = frame(s.outRound, s.outMsg, s.outOff)
                s.outOff += f.size - HDR
                gattServer?.sendResponse(d, reqId, BluetoothGatt.GATT_SUCCESS, 0, f)
                if (s.outOff >= s.outMsg.size) afterServed(s)
            }
        }
    }

    private fun serverQueue(s: ServerState, round: Int, msg: ByteArray) {
        s.outMsg = msg; s.outRound = round; s.outOff = 0
    }

    private fun onServerMsg(s: ServerState, msg: ByteArray) {
        when (s.stage) {
            0 -> { // first frame: is it a real COMMIT, or ambient garbage?
                if (msg.size != Crypto.PAIR_COMMIT_LEN) {
                    // not our protocol — a stray central. Reset silently; never alarm the human.
                    serverState = null
                    return
                }
                s.peerCommit = msg
                if (!ceremonyRunning) { ceremonyRunning = true; armTimeout() } // NOW a real ceremony begins
                s.stage = 1
                serverQueue(s, R_COMMIT, Crypto.commit(myBundle))
            }
            1 -> { // REVEAL arrived
                if (!Crypto.verifyCommit(msg, s.peerCommit)) {
                    return securityAbort("peer bundle does not match its commitment — possible interference")
                }
                s.peerBundle = msg
                s.stage = 2
                serverQueue(s, R_REVEAL, myBundle)
            }
            2 -> { // KC arrived (CT was served between REVEAL and this)
                val k = s.kPair ?: return fail("state error")
                if (!Crypto.verifyKc(k, "I", msg)) return securityAbort("key confirmation failed — keys diverged")
                s.stage = 3
                s.kcServed = false
                serverQueue(s, R_KC, Crypto.kc(k, "R"))
            }
        }
    }

    private fun afterServed(s: ServerState) {
        when (s.outRound) {
            R_REVEAL -> { // our bundle fully read -> encapsulate to the (verified) initiator key
                val pb = s.peerBundle ?: return
                val mlkemPub = Crypto.splitBundle(pb)[0]
                val enc = try { Crypto.kemEncapsulateTo(mlkemPub) } catch (e: Exception) {
                    return fail("encapsulation failed")
                }
                val peerX = Crypto.splitBundle(pb)[1]
                s.kPair = try { Crypto.deriveKpairPq(identity, peerX, enc.ss) } catch (e: Exception) {
                    return fail("key derivation failed: ${e.message}")
                }
                serverQueue(s, R_CT, enc.ct)
            }
            R_KC -> {
                if (s.kcServed) return
                s.kcServed = true
                ceremonyRunning = false
                val pb = s.peerBundle ?: return
                val k = s.kPair ?: return
                val sas = Crypto.sasOverBundles(myBundle, pb)
                Log.i(TAG, "ceremony complete (responder) sas=$sas")
                onEvent(Event.KcVerified(ContactHex.of(pb), pb, k, pq = true, sas = sas))
            }
        }
    }
}

/** Hex of the full contactId derived from a peer bundle. */
private object ContactHex {
    fun of(bundle: ByteArray): String =
        Crypto.contactIdFromBundle(bundle).joinToString("") { "%02x".format(it) }
}
