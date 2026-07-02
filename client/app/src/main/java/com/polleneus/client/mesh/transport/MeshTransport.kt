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
 * The BLE flooding/relay transport — the client build of the spike's M1 flooding node, now with
 * the spike's VALIDATED screen-off scan duty cycler ported in (V2 — pocket operation).
 *
 * Duty policy (Research Stop #5; every constraint here was MEASURED on the lab fleet):
 *   screen ON  → one continuous filtered LOW_LATENCY scan + a break-before-make preventive
 *                restart every 4 min (the Tab A9+/A16 silently downgrades any scan session at
 *                ~5.1 min — tighter than AOSP's 10-min default).
 *   screen OFF → 10s scan windows / 50–60s jittered gaps (windows never live long enough to be
 *                downgraded; a partial wakelock covers each window because postDelayed freezes
 *                when the CPU sleeps). Advertising + the GATT server are NEVER duty-cycled — the
 *                AOSP advertising path has no screen/Doze throttling, so a node in a gap stays
 *                discoverable and connectable by any peer currently in a window.
 *   budget     → the OS scan-start quota records sessions at STOP and denies SILENTLY; we cap
 *                ourselves at 4 completed stop/start cycles per rolling 30s, one slot reserved
 *                for self-heal (DutyPolicy — ported verbatim, JVM-tested).
 *   watchdog   → zero-result windows while a neighbour was RECENTLY seen mark the radio deaf
 *                (quota denial and the Samsung scan penalty both present as silence); after 4
 *                such windows the BLE stack objects soft-restart. A ~9-min inexact alarm
 *                (armed by MeshService) backstops a scheduler frozen in deep Doze.
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

        // ---- duty cycler (spike-validated values; see class doc + RS#5 memo) ----
        private const val DUTY_WINDOW_ON_MS = 10_000L
        private const val DUTY_WINDOW_OFF_MS = 50_000L
        private const val DUTY_WINDOW_JITTER_MS = 10_000
        private const val PREVENTIVE_RESTART_MS = 4 * 60_000L
        private const val SCAN_BUDGET_MAX = 4
        private const val SCAN_BUDGET_WINDOW_MS = 30_000L
        private const val SCREEN_DEBOUNCE_MS = 3_000L
        private const val DEAF_WINDOWS_RESTART = 4
        private const val DUTY_RETRY_MS = 5_000L
        private const val SOFT_RESTART_MS = 4_000L

        /**
         * V8: how long a scan sighting keeps a peer in the nearby count. Must exceed the dark
         * duty period (10s on + up to 60s gap), or the count would false-drop between windows;
         * ~2.5 periods matches the spike's deaf-watchdog recency gate. Departed peers (and
         * rotated MACs) age out on this clock — the count is an honest recent-radio fact, not
         * presence.
         */
        private const val SIGHTING_TTL_MS = 150_000L
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

    // ---- duty-cycler state (mesh-handler thread unless noted) ----
    @Volatile private var screenOn = true           // written by screenRx (main) + start() seed
    private var scanRunning = false
    private var scanSessionStart = 0L               // policy re-applies must not stretch a session
    private var dutyWindowOpen = false
    private val scanStops = LongArray(8)            // ring of completed-session stop times
    private var scanStopIdx = 0
    private var deafWindows = 0
    private val resultsThisWindow = java.util.concurrent.atomic.AtomicLong()
    @Volatile private var lastSchedulerRun = 0L     // dead-man input for the alarm backstop
    @Volatile private var windowLock: android.os.PowerManager.WakeLock? = null
    private val rnd = java.util.Random()

    // V8: addr -> last scan sighting; the published nearby count is entries younger than
    // SIGHTING_TTL_MS. Distinct from peersSeen (connect cooldown).
    private val sightings = ConcurrentHashMap<String, Long>()

    private val screenRx = object : android.content.BroadcastReceiver() {
        override fun onReceive(c: Context, i: android.content.Intent) {
            val on = android.content.Intent.ACTION_SCREEN_ON == i.action
            if (on == screenOn) return
            screenOn = on
            Log.i(TAG, "DUTY screen=${if (on) "on" else "off"}")
            handler.removeCallbacks(applyPolicy)
            handler.postDelayed(applyPolicy, SCREEN_DEBOUNCE_MS)   // coalesce pocket flicker
        }
    }

    fun start() = handler.post {
        if (running) return@post
        running = true
        screenOn = (app.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager).isInteractive
        try {
            app.registerReceiver(screenRx, android.content.IntentFilter().apply {
                addAction(android.content.Intent.ACTION_SCREEN_ON)
                addAction(android.content.Intent.ACTION_SCREEN_OFF)
            })
        } catch (e: Exception) { Log.w(TAG, "screen receiver: $e") }
        startServer(); startAdvertising()
        applyScanPolicy("start")
        handler.postDelayed(pruneTick, 20_000)
        Log.i(TAG, "mesh transport ON (screen=${if (screenOn) "on" else "off"})")
    }

    fun stop() = handler.post {
        running = false
        try { app.unregisterReceiver(screenRx) } catch (_: Exception) {}
        handler.removeCallbacks(applyPolicy)
        handler.removeCallbacks(windowTick)
        handler.removeCallbacks(preventiveRestart)
        handler.removeCallbacks(pruneTick)
        dutyStopScan("transport-stop")
        releaseWindowLock()
        dutyWindowOpen = false
        try { adapter.bluetoothLeAdvertiser?.stopAdvertising(advCb) } catch (_: Exception) {}
        try { centralGatt?.disconnect(); centralGatt?.close() } catch (_: Exception) {}
        centralGatt = null; flooding = false
        try { server?.close() } catch (_: Exception) {}
        server = null
        peersSeen.clear(); sightings.clear(); onPeers(0)
        Log.i(TAG, "mesh transport OFF")
    }

    /**
     * A locally-sealed blob was injected — clear the connect cooldown so known peers get
     * re-flooded promptly, and if we're in a dark gap, open a scan window NOW: sending is
     * exactly the moment the human wants the mesh to move.
     */
    fun kick() = handler.post {
        peersSeen.clear()
        if (running && !DutyPolicy.continuous(false, screenOn) && !dutyWindowOpen) openWindow("kick")
    }

    /**
     * MeshService's ~9-min inexact alarm lands here: if the window scheduler has been frozen
     * (deep Doze; timers stopped, wakelock possibly ignored) for >2 full periods, close any
     * stale window and re-apply the policy. Degrades gracefully to ~9-min windows under true
     * deep Doze — the node stays reachable meanwhile via continuous advertising + GATT server.
     */
    fun backstopKick() = handler.post {
        if (!running) return@post
        if (DutyPolicy.continuous(false, screenOn)) return@post
        val idle = android.os.SystemClock.elapsedRealtime() - lastSchedulerRun
        if (idle > 2 * (DUTY_WINDOW_ON_MS + DUTY_WINDOW_OFF_MS)) {
            Log.w(TAG, "DUTY backstop kick (scheduler idle ${idle}ms)")
            if (dutyWindowOpen && scanRunning) {
                dutyStopScan("backstop-stale-window idle=$idle")
                dutyWindowOpen = false
            }
            applyScanPolicy("backstop")
        }
    }

    // ---------------- advertise + scan ----------------

    private var advRetries = 0

    private val advCb = object : AdvertiseCallback() {
        override fun onStartSuccess(s: AdvertiseSettings) {
            Log.i(TAG, "adv OK")
            advRetries = 0
        }
        override fun onStartFailure(e: Int) {
            // Advertising is a HARD requirement: a node that can't advertise is invisible to
            // every peer, so the sender can never push to it (found on the Tab A9+ after the
            // pairing→mesh advertiser churn: code 4 INTERNAL_ERROR). Retry with backoff, then
            // fall back to a BLE soft-restart to clear a wedged advertiser registration.
            Log.e(TAG, "adv FAIL $e (retry ${advRetries + 1})")
            if (!running) return
            if (advRetries++ < 5) {
                handler.postDelayed({ if (running) startAdvertising() }, 1_500L * advRetries)
            } else {
                advRetries = 0
                Log.w(TAG, "adv: retries exhausted → soft-restart")
                bleSoftRestart()
            }
        }
    }

    private fun startAdvertising() {
        val adv = adapter?.bluetoothLeAdvertiser ?: return
        val settings = AdvertiseSettings.Builder()
            .setAdvertiseMode(AdvertiseSettings.ADVERTISE_MODE_LOW_LATENCY)
            .setConnectable(true).build()
        val data = AdvertiseData.Builder()
            .addServiceUuid(ParcelUuid(SVC)).setIncludeDeviceName(false).build()
        // Stop any prior registration first — a lingering advertiser is the usual cause of
        // INTERNAL_ERROR on Samsung after rapid start/stop cycles.
        try { adv.stopAdvertising(advCb) } catch (_: Exception) {}
        try {
            adv.startAdvertising(settings, data, advCb)
        } catch (e: Exception) {
            Log.e(TAG, "adv start threw: $e")
            if (running && advRetries++ < 5) handler.postDelayed({ if (running) startAdvertising() }, 1_500L * advRetries)
        }
    }

    private val scanCb = object : ScanCallback() {
        override fun onScanResult(type: Int, r: ScanResult) { handler.post { onScan(r) } }
        override fun onScanFailed(e: Int) {
            Log.e(TAG, "scan FAIL $e")
            handler.post { retryPolicy("scan-failed-$e") }
        }
    }

    // ---------------- the duty cycler (spike port; see class doc) ----------------

    private val applyPolicy = Runnable { applyScanPolicy("policy") }

    /** Recompute + apply the desired scan state. Idempotent; mesh thread only. */
    private fun applyScanPolicy(why: String) {
        lastSchedulerRun = android.os.SystemClock.elapsedRealtime()
        if (!running) return
        handler.removeCallbacks(windowTick)
        handler.removeCallbacks(preventiveRestart)
        if (DutyPolicy.continuous(false, screenOn)) {
            dutyWindowOpen = false
            deafWindows = 0        // stale dark-mode counts must not survive a healthy continuous period
            releaseWindowLock()
            if (!scanRunning) {
                dutyStartScan("continuous/$why")
            } else {
                // ADOPTING a running session: its age keeps counting toward the OS's silent
                // downgrade — a re-apply must not stretch the session past the cadence.
                val age = android.os.SystemClock.elapsedRealtime() - scanSessionStart
                if (age >= PREVENTIVE_RESTART_MS) {
                    dutyStopScan("preventive-overdue/$why")
                    dutyStartScan("preventive-overdue/$why")
                }
            }
            val age = if (scanRunning) android.os.SystemClock.elapsedRealtime() - scanSessionStart else 0
            handler.postDelayed(preventiveRestart, maxOf(1_000L, PREVENTIVE_RESTART_MS - age))
        } else {
            // Screen-off: open a window NOW — pocketing the phone is exactly when a fresh peer
            // may appear.
            openWindow(why)
        }
        prunePeers()
    }

    private fun openWindow(why: String) {
        if (!running) return
        dutyWindowOpen = true
        resultsThisWindow.set(0)
        acquireWindowLock()
        if (!scanRunning) dutyStartScan("window/$why")
        handler.removeCallbacks(windowTick)
        handler.postDelayed(windowTick, DUTY_WINDOW_ON_MS)
    }

    private val windowTick: Runnable = object : Runnable {
        override fun run() {
            if (!running) return
            lastSchedulerRun = android.os.SystemClock.elapsedRealtime()
            if (DutyPolicy.continuous(false, screenOn)) { applyScanPolicy("exit-windowed"); return }
            if (dutyWindowOpen) {
                // Close the window. DEAF-NODE WATCHDOG: the OS quota denial is SILENT and the
                // Samsung scan penalty also presents as a scan that delivers nothing — zero
                // results across several windows WHILE a neighbour was RECENTLY seen is our
                // only tell. Gate on recency: an empty room is not a deaf radio.
                dutyWindowOpen = false
                val got = resultsThisWindow.get()
                if (scanRunning) dutyStopScan("window-close got=$got")
                if (got == 0L && neighborsRecent()) {
                    deafWindows++
                    Log.w(TAG, "DUTY deaf window n=$deafWindows/$DEAF_WINDOWS_RESTART (0 results, recent neighbours known)")
                    if (deafWindows >= DEAF_WINDOWS_RESTART) {
                        deafWindows = 0
                        bleSoftRestart()
                        return
                    }
                } else if (got > 0) {
                    deafWindows = 0
                }
                releaseWindowLock()
                prunePeers()
                handler.postDelayed(this, DUTY_WINDOW_OFF_MS + rnd.nextInt(DUTY_WINDOW_JITTER_MS))
            } else {
                openWindow("gap-end")
            }
        }
    }

    /** Any peer actually SEEN within the recency window? (Deaf-watchdog input.) */
    private fun neighborsRecent(): Boolean {
        val now = android.os.SystemClock.elapsedRealtime()
        return sightings.values.any { now - it < SIGHTING_TTL_MS }
    }

    /** Screen-on continuous mode: break-before-make restart before the OS's silent downgrade. */
    private val preventiveRestart: Runnable = object : Runnable {
        override fun run() {
            if (!running) return
            lastSchedulerRun = android.os.SystemClock.elapsedRealtime()
            if (!DutyPolicy.continuous(false, screenOn)) return
            if (scanRunning) {
                dutyStopScan("preventive")
                dutyStartScan("preventive")
            }
            handler.postDelayed(this, PREVENTIVE_RESTART_MS)
        }
    }

    /**
     * Start the one filtered LL scan, gated on the stop/start budget (the OS records sessions
     * at STOP; denial is silent, so we never go near it). Every failure defers-and-retries —
     * a BT blip must not leave the node scan-deaf forever. A self-heal start may draw on the
     * reserved budget slot.
     */
    private fun dutyStartScan(why: String): Boolean {
        if (!running) return false
        val selfHeal = why.contains("self-heal")
        val scanner = adapter?.bluetoothLeScanner
            ?: run { Log.e(TAG, "DUTY no scanner (adapter off?)"); retryPolicy("no-scanner"); return false }
        val now = android.os.SystemClock.elapsedRealtime()
        if (!DutyPolicy.startAllowed(scanStops, now, SCAN_BUDGET_WINDOW_MS, SCAN_BUDGET_MAX, selfHeal)) {
            Log.w(TAG, "DUTY start DEFERRED (budget: ${DutyPolicy.completedInWindow(scanStops, now, SCAN_BUDGET_WINDOW_MS)} completed cycles in 30s) why=$why")
            retryPolicy("budget")
            return false
        }
        val filter = ScanFilter.Builder().setServiceUuid(ParcelUuid(SVC)).build()
        val settings = ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build()
        return try {
            scanner.startScan(listOf(filter), settings, scanCb)
            scanRunning = true
            scanSessionStart = now
            Log.i(TAG, "DUTY scan start ($why)")
            true
        } catch (e: Exception) {
            Log.e(TAG, "DUTY scan start failed ($why): $e")
            retryPolicy("start-threw")
            false
        }
    }

    private fun dutyStopScan(why: String) {
        val wasRunning = scanRunning
        try { adapter?.bluetoothLeScanner?.stopScan(scanCb) } catch (_: Exception) {}
        if (wasRunning) {
            scanRunning = false
            scanStops[scanStopIdx++ and 7] = android.os.SystemClock.elapsedRealtime()
            Log.i(TAG, "DUTY scan stop ($why)")
        }
    }

    /** Re-apply the policy after a delay (idempotent; coalesces repeated failures). */
    private fun retryPolicy(why: String) {
        handler.removeCallbacks(applyPolicy)
        handler.postDelayed(applyPolicy, DUTY_RETRY_MS)
    }

    /**
     * Deaf-radio self-heal: tear the BLE objects down and re-init after a cooldown. The
     * follow-up scan start is marked self-heal so it may spend the reserved budget slot.
     */
    private fun bleSoftRestart() {
        Log.w(TAG, "DUTY soft-restart (deaf radio suspected)")
        dutyStopScan("self-heal")
        releaseWindowLock()
        dutyWindowOpen = false
        try { adapter?.bluetoothLeAdvertiser?.stopAdvertising(advCb) } catch (_: Exception) {}
        try { centralGatt?.disconnect(); centralGatt?.close() } catch (_: Exception) {}
        centralGatt = null; flooding = false
        try { server?.close() } catch (_: Exception) {}
        server = null
        handler.postDelayed({
            if (!running) return@postDelayed
            startServer(); startAdvertising()
            if (DutyPolicy.continuous(false, screenOn)) dutyStartScan("continuous/self-heal")
            else openWindow("self-heal")
        }, SOFT_RESTART_MS)
    }

    // Wakelock: postDelayed runs on uptime, which FREEZES when the CPU deep-sleeps — the FGS
    // alone does not hold the CPU. Held ONLY during screen-off scan windows, timeout-capped so
    // a lost release can't pin the CPU.
    private fun acquireWindowLock() {
        try {
            if (windowLock == null) {
                val pm = app.getSystemService(Context.POWER_SERVICE) as android.os.PowerManager
                windowLock = pm.newWakeLock(
                    android.os.PowerManager.PARTIAL_WAKE_LOCK, "polleneus:scanwindow",
                ).apply { setReferenceCounted(false) }
            }
            windowLock?.acquire(DUTY_WINDOW_ON_MS + 5_000)
        } catch (e: Exception) { Log.w(TAG, "DUTY wakelock acquire: $e") }
    }

    private fun releaseWindowLock() {
        try { windowLock?.takeIf { it.isHeld }?.release() } catch (_: Exception) {}
    }

    /** V8: publish the decayed nearby count and drop aged sightings. */
    private fun prunePeers() {
        val now = android.os.SystemClock.elapsedRealtime()
        sightings.entries.removeIf { now - it.value >= SIGHTING_TTL_MS }
        onPeers(sightings.size)
    }

    /**
     * V8: with zero scan results nothing else prunes — a departed LAST peer would leave the
     * count stale on a visible screen. A light self-rescheduling tick covers that; it freezes
     * with the CPU in deep Doze, which is fine (no UI is watching a dark screen).
     */
    private val pruneTick: Runnable = object : Runnable {
        override fun run() {
            if (!running) return
            prunePeers()
            handler.postDelayed(this, 20_000)
        }
    }

    private fun onScan(r: ScanResult) {
        if (!running) return
        val addr = r.device.address
        val now = android.os.SystemClock.elapsedRealtime()
        resultsThisWindow.incrementAndGet()
        sightings[addr] = now
        prunePeers()
        if (flooding) return
        val last = peersSeen[addr] ?: 0
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
