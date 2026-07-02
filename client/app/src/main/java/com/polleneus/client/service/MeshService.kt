package com.polleneus.client.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.drawable.Icon
import android.os.Build
import android.os.IBinder
import android.util.Log
import com.polleneus.client.MainActivity
import com.polleneus.client.PolleneusApp
import com.polleneus.client.Prefs
import com.polleneus.client.R
import com.polleneus.client.mesh.MeshState
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.launch

/**
 * The pocket surface (design brief §2: the permanent notification is a first-class UI, not
 * an afterthought). Wraps the app-scoped controller (kickoff D2) and mirrors its state into
 * the one notification Android requires anyway.
 *
 * Lock-screen behavior is the design system's §5 decision: DISCREET BY DEFAULT — a locked
 * phone shows only "polleneus · active" (an ordinary utility line; no counts, no message
 * hints, no panic action an adversary could see). Full-status-on-lock is a settings opt-in.
 *
 * Discreet is enforced by KEYGUARD STATE, not by VISIBILITY_PRIVATE alone: Android's
 * publicVersion redaction only applies on secure keyguards where the user also chose "hide
 * sensitive content" — measured on the lab S21U (One UI 5), the OS default
 * (lock_screen_allow_private_notifications=1) shows PRIVATE notifications in full. So while
 * the keyguard is locked and discreet is on, the posted notification itself carries nothing
 * but "active". publicVersion stays set as defense in depth.
 *
 * Honest limit (unchanged from X3b): this keeps the process and radio alive, but screen-off
 * discovery still needs the spike's duty cycler — pocket RELAY remains a deferred increment;
 * no copy anywhere claims it.
 */
class MeshService : Service() {

    companion object {
        private const val TAG = "PN-SVC"
        private const val CHANNEL = "mesh_status"
        private const val NOTIF_ID = 1

        const val ACTION_PAUSE = "com.polleneus.client.action.PAUSE"
        const val ACTION_RESUME = "com.polleneus.client.action.RESUME"
        private const val ACTION_REFRESH = "com.polleneus.client.action.REFRESH"

        @Volatile private var running = false

        fun start(ctx: Context) {
            ctx.startForegroundService(Intent(ctx, MeshService::class.java))
        }

        /** Re-post the notification (e.g. the discreet toggle flipped). No-op when stopped. */
        fun refresh(ctx: Context) {
            if (!running) return
            ctx.startService(Intent(ctx, MeshService::class.java).setAction(ACTION_REFRESH))
        }

        fun stop(ctx: Context) {
            ctx.stopService(Intent(ctx, MeshService::class.java))
        }
    }

    private var watch: Job? = null

    /** Keyguard transitions re-post the notification (discreet content swap). */
    private val lockWatcher = object : android.content.BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (running) {
                getSystemService(NotificationManager::class.java)
                    .notify(NOTIF_ID, buildNotification())
            }
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL, "Mesh status", NotificationManager.IMPORTANCE_LOW)
                .apply { setShowBadge(false) },
        )
        registerReceiver(
            lockWatcher,
            android.content.IntentFilter().apply {
                addAction(Intent.ACTION_SCREEN_OFF)
                addAction(Intent.ACTION_SCREEN_ON)
                addAction(Intent.ACTION_USER_PRESENT)
            },
        )
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val controller = (application as PolleneusApp).controller
        when (intent?.action) {
            ACTION_PAUSE -> controller.pause()
            ACTION_RESUME -> controller.resume()
        }

        try {
            val n = buildNotification()
            if (Build.VERSION.SDK_INT >= 29) {
                startForeground(NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE)
            } else {
                startForeground(NOTIF_ID, n)
            }
            running = true
        } catch (e: Exception) {
            // FGS-type prerequisites missing (e.g. BLE permission revoked mid-flight):
            // the mesh has no radio to run anyway — stop honestly rather than limp.
            Log.e(TAG, "startForeground refused: $e")
            stopSelf()
            return START_NOT_STICKY
        }

        if (watch == null) {
            watch = (application as PolleneusApp).appScope.launch {
                combine(
                    controller.meshState, controller.nearbyDevices,
                    controller.carryingCount, controller.inbox,
                ) { state, nearby, carrying, inbox ->
                    Snapshot(state, nearby, carrying, inbox.count { !it.openedLocally })
                }.distinctUntilChanged().collect {
                    if (running) {
                        getSystemService(NotificationManager::class.java)
                            .notify(NOTIF_ID, buildNotification(it))
                    }
                }
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        running = false
        watch?.cancel()
        watch = null
        runCatching { unregisterReceiver(lockWatcher) }
        super.onDestroy()
    }

    private data class Snapshot(
        val state: MeshState,
        val nearby: Int,
        val carrying: Int,
        val unread: Int,
    )

    private fun snapshotNow(): Snapshot {
        val c = (application as PolleneusApp).controller
        return Snapshot(
            c.meshState.value, c.nearbyDevices.value, c.carryingCount.value,
            c.inbox.value.count { !it.openedLocally },
        )
    }

    private fun buildNotification(s: Snapshot = snapshotNow()): Notification {
        val discreet = Prefs.discreet(this)
        val keyguard = getSystemService(android.app.KeyguardManager::class.java)

        // Discreet + locked: the posted notification itself is the ordinary utility line.
        // No counts (mesh-role evidence), no message hints, no panic action a stranger
        // could see on a seized phone. Everything returns at unlock (USER_PRESENT).
        if (discreet && keyguard.isKeyguardLocked) {
            return Notification.Builder(this, CHANNEL)
                .setSmallIcon(R.drawable.ic_stat_mesh)
                .setContentText("active")
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .setVisibility(Notification.VISIBILITY_PRIVATE)
                .build()
        }

        val paused = s.state == MeshState.PAUSED

        val title = when (s.state) {
            MeshState.RELAYING -> "Relaying — ${s.nearby} ${plural(s.nearby, "device")} nearby"
            MeshState.LISTENING -> "Listening — no devices nearby"
            MeshState.PAUSED -> "Paused — not relaying"
        }
        val text = if (paused) {
            "Held messages are not forwarded while paused."
        } else {
            buildString {
                append("Carrying ${s.carrying} sealed ${plural(s.carrying, "message")} for the mesh.")
                if (s.unread > 0) append(" ${s.unread} new ${plural(s.unread, "message")} for you.")
            }
        }

        val toggle = if (paused) {
            action("Resume mesh", ACTION_RESUME, 1)
        } else {
            action("Pause mesh", ACTION_PAUSE, 2)
        }
        // Panic opens the step-2 confirm screen (unlock required) — the two-step ceremony
        // survives the shortcut; the notification action alone never erases anything.
        val panic = Notification.Action.Builder(
            Icon.createWithResource(this, R.drawable.ic_stat_mesh),
            "Panic",
            PendingIntent.getActivity(
                this, 3,
                Intent(this, MainActivity::class.java)
                    .setAction(MainActivity.ACTION_PANIC)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            ),
        ).build()

        val b = Notification.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_stat_mesh)
            .setContentTitle(title)
            .setContentText(text)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(
                PendingIntent.getActivity(
                    this, 4, Intent(this, MainActivity::class.java),
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
                ),
            )
            .addAction(toggle)
            .addAction(panic)
            .setVisibility(
                if (discreet) Notification.VISIBILITY_PRIVATE else Notification.VISIBILITY_PUBLIC,
            )
        if (discreet) {
            b.setPublicVersion(
                Notification.Builder(this, CHANNEL)
                    .setSmallIcon(R.drawable.ic_stat_mesh)
                    .setContentText("active")
                    .setOngoing(true)
                    .build(),
            )
        }
        return b.build()
    }

    private fun action(title: String, intentAction: String, rc: Int): Notification.Action =
        Notification.Action.Builder(
            Icon.createWithResource(this, R.drawable.ic_stat_mesh),
            title,
            PendingIntent.getService(
                this, rc,
                Intent(this, MeshService::class.java).setAction(intentAction),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            ),
        ).build()

    private fun plural(n: Int, word: String) = if (n == 1) word else "${word}s"
}
