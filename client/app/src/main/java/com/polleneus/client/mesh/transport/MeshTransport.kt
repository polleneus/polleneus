package com.polleneus.client.mesh.transport

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
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap

/**
 * The BLE flooding/relay transport — the client build of the spike's M1 flooding node, scoped to
 * SCREEN-ON interactive operation for the mission test. (The screen-off duty cycler that lets the
 * mesh run pocketed is validated in the spike and is a DEFERRED optimization — not needed to prove
 * send→flood→receive→open.)
 *
 * Reconciliation is the proven naive protocol over one GATT service:
 *   central: connect → OFFER (write my inventory ids) → REQUEST (read the ids the peer lacks)
 *            → DATA (write id‖len‖offset‖chunk for each wanted blob) → disconnect
 *   server:  on OFFER, compute wanted = offered ∉ store; on REQUEST, serve wanted; on DATA,
 *            reassemble per (peer,id) → validate content-address+TTL → store → trial-open.
 *
 * All crypto is the JVM-tested Crypto; this class is transport only.
 */
@SuppressLint("MissingPermission") // BLE perms are held by the foreground service that owns this
class MeshTransport(
    ctx: Context,
    private val store: MeshStore,
    private val onBlob: (id: String, wire: ByteArray) -> Boolean,  // returns true if fresh+stored
    private val onPeers: (Int) -> Unit,
) {
    companion object {
        private const val TAG = "PN-MESH"
        val SVC: UUID = UUID.fromString("0000b2b2-0000-1000-8000-00805f9b34fb")   // client mesh service
        val CHR_OFFER: UUID = UUID.fromString("0000b2c1-0000-1000-8000-00805f9b34fb")
        val CHR_REQUEST: UUID = UUID.fromString("0000b2c2-0000-1000-8000-00805f9b34fb")
        val CHR_DATA: UUID = UUID.fromString("0000b2c3-0000-1000-8000-00805f9b34fb")

        private const val ID_LEN = MeshStore.ID_LEN            // 32
        private const val DATA_HDR = ID_LEN + 4 + 4           // id ‖ totalLen ‖ offset
        private const val CHUNK = 180
        private const val MTU = 517
        private const val CONNECT_COOLDOWN_MS = 8_000L        // don't re-flood the same peer too fast
    }

    private val app = ctx.applicationContext
    private val btMgr = app.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager
    private val adapter = btMgr.adapter
    private val thread = HandlerThread("pn-mesh").also { it.start() }
    private val handler = Handler(thread.looper)

    private var running = false
    private var server: BluetoothGattServer? = null
    private val peersSeen = ConcurrentHashMap<String, Long>()   // addr -> last connect attempt
    private var flooding = false
    private var centralGatt: BluetoothGatt? = null

    fun start() = handler.post {
        if (running) return@post
        running = true
        startServer(); startAdvertising(); startScan()
        Log.i(TAG, "mesh transport ON")
    }

    fun stop() = handler.post {
        running = false
        try { adapter.bluetoothLeScanner?.stopScan(scanCb) } catch (_: Exception) {}
        try { adapter.bluetoothLeAdvertiser?.stopAdvertising(advCb) } catch (_: Exception) {}
        try { centralGatt?.disconnect(); centralGatt?.close() } catch (_: Exception) {}
        centralGatt = null; flooding = false
        try { server?.close() } catch (_: Exception) {}
        server = null
        peersSeen.clear(); onPeers(0)
        Log.i(TAG, "mesh transport OFF")
    }

    /** A locally-sealed blob was injected — kick a flood so nearby peers pull it promptly. */
    fun kick() = handler.post { peersSeen.clear() }   // allow immediate reconnect to known peers

    // ---------------- advertise + scan ----------------

    private val advCb = object : AdvertiseCallback() {
        override fun onStartSuccess(s: AdvertiseSettings) { Log.i(TAG, "adv OK") }
        override fun onStartFailure(e: Int) { Log.e(TAG, "adv FAIL $e") }
    }

    private fun startAdvertising() {
        val adv = adapter.bluetoothLeAdvertiser ?: return
        val settings = AdvertiseSettings.Builder()
            .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
            .setConnectable(true).build()
        val data = AdvertiseData.Builder()
            .addServiceUuid(ParcelUuid(SVC)).setIncludeDeviceName(false).build()
        adv.startAdvertising(settings, data, advCb)
    }

    private val scanCb = object : ScanCallback() {
        override fun onScanResult(type: Int, r: ScanResult) { handler.post { onScan(r) } }
        override fun onScanFailed(e: Int) { Log.e(TAG, "scan FAIL $e") }
    }

    private fun startScan() {
        val scanner = adapter.bluetoothLeScanner ?: return
        val filter = ScanFilter.Builder().setServiceUuid(ParcelUuid(SVC)).build()
        val settings = ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build()
        scanner.startScan(listOf(filter), settings, scanCb)
    }

    private fun onScan(r: ScanResult) {
        if (!running || flooding) return
        val addr = r.device.address
        val now = android.os.SystemClock.elapsedRealtime()
        val last = peersSeen[addr] ?: 0
        onPeers(peersSeen.size.coerceAtLeast(1))
        if (now - last < CONNECT_COOLDOWN_MS) return
        peersSeen[addr] = now
        // brief connect → reconcile → disconnect (the mandatory pattern from the transport findings)
        flooding = true
        Log.i(TAG, "flood → $addr")
        centralGatt = r.device.connectGatt(app, false, centralCb, BluetoothDevice.TRANSPORT_LE)
    }

    private fun endFlood(ok: Boolean) {
        try { centralGatt?.disconnect(); centralGatt?.close() } catch (_: Exception) {}
        centralGatt = null; flooding = false
    }

    // ---------------- central flood client ----------------

    private var cOffer: BluetoothGattCharacteristic? = null
    private var cRequest: BluetoothGattCharacteristic? = null
    private var cData: BluetoothGattCharacteristic? = null
    private var wanted: List<ByteArray> = emptyList()
    private var sendIndex = 0
    private var sendOffset = 0

    private val centralCb = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
            handler.post {
                if (newState == BluetoothProfile.STATE_CONNECTED) g.requestMtu(MTU)
                else if (newState == BluetoothProfile.STATE_DISCONNECTED) endFlood(false)
            }
        }
        override fun onMtuChanged(g: BluetoothGatt, mtu: Int, status: Int) { handler.post { g.discoverServices() } }
        override fun onServicesDiscovered(g: BluetoothGatt, status: Int) {
            handler.post {
                val svc = g.getService(SVC) ?: return@post endFlood(false)
                cOffer = svc.getCharacteristic(CHR_OFFER)
                cRequest = svc.getCharacteristic(CHR_REQUEST)
                cData = svc.getCharacteristic(CHR_DATA)
                if (cOffer == null || cRequest == null || cData == null) return@post endFlood(false)
                // Step 1: OFFER our inventory
                val inv = concatIds(store.inventory())
                cOffer!!.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
                @Suppress("DEPRECATION") run { cOffer!!.value = inv; g.writeCharacteristic(cOffer) }
            }
        }
        @Suppress("DEPRECATION")
        override fun onCharacteristicWrite(g: BluetoothGatt, chr: BluetoothGattCharacteristic, status: Int) {
            handler.post {
                if (status != BluetoothGatt.GATT_SUCCESS) return@post endFlood(false)
                when (chr.uuid) {
                    CHR_OFFER -> g.readCharacteristic(cRequest)     // Step 2: read REQUEST
                    CHR_DATA -> sendNextData(g)                     // Step 4: keep pushing
                }
            }
        }
        @Suppress("DEPRECATION")
        override fun onCharacteristicRead(g: BluetoothGatt, chr: BluetoothGattCharacteristic, status: Int) {
            handler.post {
                if (status != BluetoothGatt.GATT_SUCCESS || chr.uuid != CHR_REQUEST) return@post endFlood(false)
                wanted = parseIds(chr.value ?: ByteArray(0))
                sendIndex = 0; sendOffset = 0
                Log.i(TAG, "peer wants ${wanted.size} blobs")
                sendNextData(g)
            }
        }
    }

    @Suppress("DEPRECATION")
    private fun sendNextData(g: BluetoothGatt) {
        while (true) {
            if (sendIndex >= wanted.size) { Log.i(TAG, "push complete"); endFlood(true); return }
            val id = wanted[sendIndex]
            val blob = store.get(MeshStore.hex(id))
            if (blob == null || sendOffset >= blob.size) { sendIndex++; sendOffset = 0; continue }
            val chunkLen = minOf(CHUNK, blob.size - sendOffset)
            val frame = ByteArray(DATA_HDR + chunkLen)
            System.arraycopy(id, 0, frame, 0, ID_LEN)
            putInt(frame, ID_LEN, blob.size)
            putInt(frame, ID_LEN + 4, sendOffset)
            System.arraycopy(blob, sendOffset, frame, DATA_HDR, chunkLen)
            sendOffset += chunkLen
            cData!!.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
            cData!!.value = frame
            g.writeCharacteristic(cData)
            return
        }
    }

    // ---------------- GATT server (peripheral) ----------------

    private val wantedByPeer = ConcurrentHashMap<String, ByteArray>()
    private val reasm = ConcurrentHashMap<String, ReasmBuf>()

    private class ReasmBuf(val total: Int) { val buf = ByteArray(total); var got = 0 }

    private fun startServer() {
        val s = btMgr.openGattServer(app, serverCb) ?: return
        val svc = BluetoothGattService(SVC, BluetoothGattService.SERVICE_TYPE_PRIMARY)
        svc.addCharacteristic(BluetoothGattCharacteristic(CHR_OFFER,
            BluetoothGattCharacteristic.PROPERTY_WRITE, BluetoothGattCharacteristic.PERMISSION_WRITE))
        svc.addCharacteristic(BluetoothGattCharacteristic(CHR_REQUEST,
            BluetoothGattCharacteristic.PROPERTY_READ, BluetoothGattCharacteristic.PERMISSION_READ))
        svc.addCharacteristic(BluetoothGattCharacteristic(CHR_DATA,
            BluetoothGattCharacteristic.PROPERTY_WRITE, BluetoothGattCharacteristic.PERMISSION_WRITE))
        s.addService(svc)
        server = s
    }

    private val serverCb = object : BluetoothGattServerCallback() {
        override fun onCharacteristicWriteRequest(
            d: BluetoothDevice, reqId: Int, chr: BluetoothGattCharacteristic,
            prep: Boolean, respond: Boolean, offset: Int, value: ByteArray,
        ) {
            handler.post {
                when (chr.uuid) {
                    CHR_OFFER -> {
                        val offered = parseIds(value)
                        val want = offered.filter { !store.has(MeshStore.hex(it)) && !store.wasExpired(MeshStore.hex(it)) }
                        wantedByPeer[d.address] = concatIds(want)
                        Log.i(TAG, "OFFER from ${d.address} offered=${offered.size} want=${want.size}")
                        if (respond) server?.sendResponse(d, reqId, BluetoothGatt.GATT_SUCCESS, offset, null)
                    }
                    CHR_DATA -> {
                        handleDataChunk(d.address, value)
                        if (respond) server?.sendResponse(d, reqId, BluetoothGatt.GATT_SUCCESS, offset, null)
                    }
                    else -> if (respond) server?.sendResponse(d, reqId, BluetoothGatt.GATT_FAILURE, offset, null)
                }
            }
        }
        override fun onCharacteristicReadRequest(
            d: BluetoothDevice, reqId: Int, offset: Int, chr: BluetoothGattCharacteristic,
        ) {
            handler.post {
                if (chr.uuid == CHR_REQUEST) {
                    val want = wantedByPeer[d.address] ?: ByteArray(0)
                    val slice = if (offset >= want.size) ByteArray(0) else want.copyOfRange(offset, want.size)
                    server?.sendResponse(d, reqId, BluetoothGatt.GATT_SUCCESS, offset, slice)
                } else {
                    server?.sendResponse(d, reqId, BluetoothGatt.GATT_FAILURE, offset, null)
                }
            }
        }
    }

    private fun handleDataChunk(addr: String, frame: ByteArray) {
        if (frame.size < DATA_HDR) return
        val id = frame.copyOfRange(0, ID_LEN)
        val total = getInt(frame, ID_LEN)
        val off = getInt(frame, ID_LEN + 4)
        val chunk = frame.copyOfRange(DATA_HDR, frame.size)
        if (total < 0 || total > 8 * 1024 * 1024 || off < 0 || off + chunk.size > total) return
        val key = "$addr:${MeshStore.hex(id)}"
        val r = reasm.getOrPut(key) { ReasmBuf(total) }
        if (r.total != total) { reasm[key] = ReasmBuf(total) }
        val rb = reasm[key]!!
        System.arraycopy(chunk, 0, rb.buf, off, chunk.size)
        rb.got = maxOf(rb.got, off + chunk.size)
        if (rb.got >= rb.total) {
            reasm.remove(key)
            onBlob(MeshStore.hex(id), rb.buf)   // controller validates + stores + trial-opens
        }
    }

    // ---------------- id framing ----------------

    private fun parseIds(v: ByteArray): List<ByteArray> =
        (0 until v.size / ID_LEN).map { v.copyOfRange(it * ID_LEN, it * ID_LEN + ID_LEN) }

    private fun concatIds(ids: List<ByteArray>): ByteArray {
        // cap the inventory to what fits one ATT payload (MTU-3), oldest-safe: the spike truncates too
        val max = (MTU - 3) / ID_LEN
        val take = ids.take(max)
        val out = ByteArray(take.size * ID_LEN)
        take.forEachIndexed { i, id -> System.arraycopy(id, 0, out, i * ID_LEN, ID_LEN) }
        return out
    }

    private fun putInt(b: ByteArray, o: Int, v: Int) {
        b[o] = (v ushr 24).toByte(); b[o + 1] = (v ushr 16).toByte()
        b[o + 2] = (v ushr 8).toByte(); b[o + 3] = v.toByte()
    }

    private fun getInt(b: ByteArray, o: Int): Int =
        ((b[o].toInt() and 0xff) shl 24) or ((b[o + 1].toInt() and 0xff) shl 16) or
            ((b[o + 2].toInt() and 0xff) shl 8) or (b[o + 3].toInt() and 0xff)
}
