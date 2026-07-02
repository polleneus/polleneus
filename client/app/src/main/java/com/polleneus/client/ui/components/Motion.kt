package com.polleneus.client.ui.components

import android.content.Context
import android.database.ContentObserver
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.State
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext

/**
 * Reduced motion (design system §7): when Android's "Remove animations" accessibility
 * setting is on (animator scale 0), telemetry loops go static and blinks go solid.
 * All information survives; only liveness theater goes.
 */
val LocalReducedMotion = compositionLocalOf { false }

@Composable
fun rememberReducedMotion(): State<Boolean> {
    val ctx = LocalContext.current
    val reduced = remember { mutableStateOf(isReduced(ctx)) }
    DisposableEffect(Unit) {
        val obs = object : ContentObserver(Handler(Looper.getMainLooper())) {
            override fun onChange(selfChange: Boolean) {
                reduced.value = isReduced(ctx)
            }
        }
        ctx.contentResolver.registerContentObserver(
            Settings.Global.getUriFor(Settings.Global.ANIMATOR_DURATION_SCALE), false, obs,
        )
        onDispose { ctx.contentResolver.unregisterContentObserver(obs) }
    }
    return reduced
}

private fun isReduced(ctx: Context): Boolean =
    Settings.Global.getFloat(
        ctx.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f,
    ) == 0f
