package com.polleneus.client.system

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.PowerManager
import android.provider.Settings
import android.util.Log

/**
 * The battery-optimization grant (design brief §2 — a known adoption cliff; kickoff Q5).
 *
 * Deliberately OEM-generic: the standard exemption dialog first, the system exemption list
 * as fallback, app details as last resort. Q5's per-OEM answer is a DEVICE-TESTED table
 * recorded at X4 verification (lab fleet = Samsung One UI), not speculative deep links into
 * vendor settings that break across OEM versions.
 *
 * REQUEST_IGNORE_BATTERY_OPTIMIZATIONS is Play-restricted policy-wise; this project ships
 * nothing before the B1 audit and never through a store without a B3 copy review, so the
 * honest, direct grant path is the right call for lab builds.
 */
object Battery {
    private const val TAG = "PN-BATT"

    fun unrestricted(ctx: Context): Boolean {
        val pm = ctx.getSystemService(Context.POWER_SERVICE) as PowerManager
        return pm.isIgnoringBatteryOptimizations(ctx.packageName)
    }

    /** Opens the most direct grant surface this device supports. */
    fun requestGrant(ctx: Context) {
        val direct = Intent(
            Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
            Uri.parse("package:${ctx.packageName}"),
        )
        try {
            ctx.startActivity(direct)
            Log.i(TAG, "battery grant: direct exemption dialog")
            return
        } catch (_: ActivityNotFoundException) {
        } catch (_: SecurityException) {
        }
        try {
            ctx.startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
            Log.i(TAG, "battery grant: exemption list fallback")
            return
        } catch (_: ActivityNotFoundException) {
        }
        try {
            ctx.startActivity(
                Intent(
                    Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                    Uri.parse("package:${ctx.packageName}"),
                ),
            )
            Log.i(TAG, "battery grant: app details last resort")
        } catch (e: Exception) {
            Log.e(TAG, "battery grant: no settings surface reachable: $e")
        }
    }
}
