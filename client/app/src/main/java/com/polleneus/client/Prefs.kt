package com.polleneus.client

import android.content.Context

/**
 * Device-local UI preferences. Deliberately tiny (design system §5: settings are "short by
 * design" — every entry here changes something real about safety or battery).
 *
 * panicReset() returns this file to factory state: after a panic wipe the app must look and
 * behave like it was just installed — a surviving "onboarded" flag or lock-screen choice
 * would contradict NOTHING STORED.
 */
object Prefs {
    private const val FILE = "polleneus_prefs"
    private const val K_ONBOARDED = "onboarded"
    private const val K_DISCREET = "discreet_notification"
    private const val K_TTL_INDEX = "default_ttl_index"

    /** Index into the shared TTL table (1h / 12h / 2d / 7d). 2 days is the design default. */
    const val DEFAULT_TTL_INDEX = 2

    private fun sp(ctx: Context) = ctx.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    fun onboarded(ctx: Context): Boolean = sp(ctx).getBoolean(K_ONBOARDED, false)
    fun setOnboarded(ctx: Context) = sp(ctx).edit().putBoolean(K_ONBOARDED, true).apply()

    /** Discreet lock-screen notification. Default ON — the threat model's trade (§5/§6). */
    fun discreet(ctx: Context): Boolean = sp(ctx).getBoolean(K_DISCREET, true)
    fun setDiscreet(ctx: Context, on: Boolean) = sp(ctx).edit().putBoolean(K_DISCREET, on).apply()

    fun defaultTtlIndex(ctx: Context): Int = sp(ctx).getInt(K_TTL_INDEX, DEFAULT_TTL_INDEX)
    fun setDefaultTtlIndex(ctx: Context, i: Int) = sp(ctx).edit().putInt(K_TTL_INDEX, i).apply()

    fun panicReset(ctx: Context) = sp(ctx).edit().clear().commit()
}
