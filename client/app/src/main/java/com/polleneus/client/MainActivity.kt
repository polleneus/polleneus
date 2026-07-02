package com.polleneus.client

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.mutableIntStateOf
import com.polleneus.client.service.MeshService
import com.polleneus.client.system.Perms
import com.polleneus.client.ui.AppShell
import com.polleneus.client.ui.theme.PolleneusTheme

class MainActivity : ComponentActivity() {

    companion object {
        /** The notification's Panic action: opens the step-2 confirm; on its own it erases nothing. */
        const val ACTION_PANIC = "com.polleneus.client.action.PANIC"
    }

    private val panicSignal = mutableIntStateOf(0)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = application as PolleneusApp

        if (Prefs.onboarded(this)) {
            // X4: the controller is app-scoped (kickoff D2); the foreground service keeps
            // the mesh + notification alive past this activity.
            app.controller.start()
            if (Perms.ble(this)) MeshService.start(this)
        } else {
            // First run (or post-wipe): show the key in onboarding step 1, but the radio
            // waits behind the honest-deal gate.
            app.controller.ensureIdentity()
        }

        if (intent?.action == ACTION_PANIC) panicSignal.intValue++

        setContent {
            PolleneusTheme {
                AppShell(
                    controller = app.controller,
                    panicSignal = panicSignal.intValue,
                    ensureIdentity = { app.controller.ensureIdentity() },
                )
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        if (intent.action == ACTION_PANIC) panicSignal.intValue++
    }
}
