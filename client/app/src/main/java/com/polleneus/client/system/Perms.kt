package com.polleneus.client.system

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build

/** Single source of truth for the mesh's runtime-permission state. */
object Perms {

    fun blePerms(): Array<String> =
        if (Build.VERSION.SDK_INT >= 31) arrayOf(
            android.Manifest.permission.BLUETOOTH_SCAN,
            android.Manifest.permission.BLUETOOTH_ADVERTISE,
            android.Manifest.permission.BLUETOOTH_CONNECT,
        ) else arrayOf(android.Manifest.permission.ACCESS_FINE_LOCATION)

    fun ble(ctx: Context): Boolean = blePerms().all {
        ctx.checkSelfPermission(it) == PackageManager.PERMISSION_GRANTED
    }
}
