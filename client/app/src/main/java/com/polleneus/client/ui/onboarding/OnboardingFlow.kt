package com.polleneus.client.ui.onboarding

import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.polleneus.client.mesh.MeshController
import com.polleneus.client.system.Battery
import com.polleneus.client.ui.components.BtnKind
import com.polleneus.client.ui.components.Faceplate
import com.polleneus.client.ui.components.HDivider
import com.polleneus.client.ui.components.PnButton
import com.polleneus.client.ui.components.Radar
import com.polleneus.client.ui.components.TFoot
import com.polleneus.client.ui.components.TLabel
import com.polleneus.client.ui.theme.Archivo
import com.polleneus.client.ui.theme.MartianMono
import com.polleneus.client.ui.theme.Pn

/**
 * First run — the flow that carries the ethical weight (design brief §6.1, design system §5).
 * Three steps: identity (no account) → the honest deal (§3 must-disclose; the gate is
 * deliberately unskippable, kickoff Q3 approved as designed) → battery + notification reframe.
 *
 * Step 3 also asks for the runtime permissions the mesh needs to exist at all (notifications
 * on 13+, BLE on 12+) — asking before explaining would waste the one moment Android gives us.
 */
@Composable
fun OnboardingFlow(controller: MeshController, onDone: () -> Unit) {
    var step by remember { mutableIntStateOf(0) }
    Column(
        Modifier.fillMaxSize().padding(horizontal = 16.dp),
    ) {
        StepHeader(step)
        when (step) {
            0 -> StepIdentity(controller, onNext = { step = 1 })
            1 -> StepHonestDeal(onNext = { step = 2 })
            2 -> StepBattery(onDone = onDone)
        }
    }
}

@Composable
private fun StepHeader(step: Int) {
    Row(
        Modifier.fillMaxWidth().padding(top = 14.dp, bottom = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        TLabel("First run", color = Pn.InkGhost)
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            repeat(3) { i ->
                Box(
                    Modifier.size(width = 14.dp, height = 3.dp)
                        .background(if (i == step) Pn.Accent else Pn.LineStrong),
                )
            }
        }
    }
}

@Composable
private fun ObHeading(text: String) {
    BasicText(
        text.uppercase(),
        Modifier.padding(top = 14.dp, bottom = 10.dp),
        style = TextStyle(
            fontFamily = MartianMono, fontSize = 21.sp, fontWeight = FontWeight.W700,
            letterSpacing = 0.02.em, color = Pn.Ink, lineHeight = 28.sp,
        ),
    )
}

@Composable
private fun ObBody(text: String, modifier: Modifier = Modifier) {
    BasicText(
        text,
        modifier,
        style = TextStyle(
            fontFamily = Archivo, fontSize = 14.sp, color = Pn.InkDim, lineHeight = 22.sp,
        ),
    )
}

/* ============ step 1 — identity, no account ============ */

@Composable
private fun StepIdentity(controller: MeshController, onNext: () -> Unit) {
    val key by controller.deviceKey.collectAsState()
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        ObHeading("This phone just\nmade its own key")
        Faceplate {
            Column(
                Modifier.fillMaxWidth().padding(vertical = 26.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Radar(nodes = 0, sweeping = true, modifier = Modifier.size(120.dp))
                Spacer(Modifier.height(20.dp))
                TLabel("Your device key")
                Spacer(Modifier.height(10.dp))
                BasicText(
                    if (key.isEmpty()) "· · · ·" else key,
                    style = TextStyle(
                        fontFamily = MartianMono, fontSize = 19.sp, letterSpacing = 0.14.em,
                        color = Pn.Ink,
                    ),
                )
            }
            HDivider()
            Column(Modifier.padding(14.dp)) {
                ObBody(
                    "No account. No phone number. No signup, no servers. The key never " +
                        "leaves this phone — when you want to reach someone, you'll meet " +
                        "them once, in person, and compare a short code.",
                )
            }
        }
        Spacer(Modifier.weight(1f))
        PnButton("Continue", BtnKind.PRIMARY, Modifier.fillMaxWidth(), onClick = onNext)
        Spacer(Modifier.height(26.dp))
    }
}

/* ============ step 2 — the honest deal (unskippable gate, Q3) ============ */

@Composable
private fun StepHonestDeal(onNext: () -> Unit) {
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        ObHeading("The honest deal")
        NorthStar()
        Spacer(Modifier.height(12.dp))
        Faceplate {
            DealRow(true, "Sealed — content",
                "Only the person a message is sealed for can read it. Carriers can't.")
            HDivider()
            DealRow(true, "Sealed — who it's for",
                "Every phone nearby gets a copy, so having one proves nothing about you.")
            HDivider()
            DealRow(false, "Visible — that you run it",
                "Radio can be seen. A capable observer can tell this phone is on the mesh. " +
                    "There is no invisible mode.")
            HDivider()
            DealRow(false, "Visible — patterns over time",
                "Someone watched and sending often can eventually be identified. " +
                    "One message blends in; a habit doesn't.")
            HDivider()
            DealRow(false, "Deleting is local",
                "Wiping removes your copy. Copies other phones carry fade on their own timers.")
        }
        TFoot(
            "if you are personally hunted by a well-equipped adversary, " +
                "this tool is not enough on its own",
            Modifier.padding(top = 10.dp, start = 2.dp),
            color = Pn.InkFaint,
        )
        Spacer(Modifier.weight(1f))
        Spacer(Modifier.height(14.dp))
        // The gate: one required tap, once, with the limits above the fold. No skip exists.
        PnButton("I understand the limits", BtnKind.PRIMARY, Modifier.fillMaxWidth(), onClick = onNext)
        Spacer(Modifier.height(26.dp))
    }
}

@Composable
fun NorthStar(modifier: Modifier = Modifier) {
    Box(modifier.fillMaxWidth().background(Pn.Panel).padding(14.dp)) {
        BasicText(
            buildString {
                append("What you say, and who you say it to, are hidden. ")
                append("That you're part of the network is not.")
            },
            style = TextStyle(
                fontFamily = Archivo, fontSize = 13.5.sp, color = Pn.Ink, lineHeight = 21.sp,
            ),
        )
    }
}

@Composable
fun DealRow(sealed: Boolean, title: String, body: String) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp)) {
        DealMark(sealed)
        Spacer(Modifier.width(12.dp))
        Column {
            BasicText(
                title.uppercase(),
                style = TextStyle(
                    fontFamily = MartianMono, fontSize = 9.5.sp, fontWeight = FontWeight.W500,
                    letterSpacing = 0.1.em, color = Pn.Ink,
                ),
            )
            Spacer(Modifier.height(4.dp))
            BasicText(
                body,
                style = TextStyle(
                    fontFamily = Archivo, fontSize = 12.5.sp, color = Pn.InkDim, lineHeight = 19.sp,
                ),
            )
        }
    }
}

/** Teal check = sealed/protected; orange alert = visible/limit. The triad law, in a glyph. */
@Composable
private fun DealMark(sealed: Boolean) {
    androidx.compose.foundation.Canvas(Modifier.padding(top = 1.dp).size(16.dp)) {
        val s = size.minDimension
        val w = Stroke(1.8f * density)
        if (sealed) {
            val p = Path().apply {
                moveTo(s * 0.19f, s * 0.53f)
                lineTo(s * 0.41f, s * 0.75f)
                lineTo(s * 0.81f, s * 0.31f)
            }
            drawPath(p, Pn.Data, style = w)
        } else {
            drawCircle(Pn.Accent, radius = s * 0.375f, center = Offset(s / 2, s / 2), style = w)
            drawLine(Pn.Accent, Offset(s / 2, s * 0.31f), Offset(s / 2, s * 0.54f), w.width)
            drawCircle(Pn.Accent, radius = s * 0.033f, center = Offset(s / 2, s * 0.7f))
        }
    }
}

/* ============ step 3 — battery + the permanent notification ============ */

private fun runtimePerms(): Array<String> {
    val perms = mutableListOf<String>()
    if (Build.VERSION.SDK_INT >= 33) perms += android.Manifest.permission.POST_NOTIFICATIONS
    if (Build.VERSION.SDK_INT >= 31) {
        perms += android.Manifest.permission.BLUETOOTH_SCAN
        perms += android.Manifest.permission.BLUETOOTH_ADVERTISE
        perms += android.Manifest.permission.BLUETOOTH_CONNECT
    } else {
        perms += android.Manifest.permission.ACCESS_FINE_LOCATION
    }
    return perms.toTypedArray()
}

private fun allPermsGranted(ctx: android.content.Context): Boolean = runtimePerms().all {
    ctx.checkSelfPermission(it) == android.content.pm.PackageManager.PERMISSION_GRANTED
}

@Composable
private fun StepBattery(onDone: () -> Unit) {
    val ctx = LocalContext.current
    var batteryGranted by remember { mutableStateOf(Battery.unrestricted(ctx)) }
    var permsAsked by remember { mutableStateOf(false) }
    var doneAfterPerms by remember { mutableStateOf(false) }

    // returning from the system dialog / settings: re-read the real grant state
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val obs = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) batteryGranted = Battery.unrestricted(ctx)
        }
        lifecycleOwner.lifecycle.addObserver(obs)
        onDispose { lifecycleOwner.lifecycle.removeObserver(obs) }
    }

    val permLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions(),
    ) {
        if (doneAfterPerms) onDone()
        else if (!batteryGranted) Battery.requestGrant(ctx)
    }

    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())) {
        ObHeading("Let it work\nin your pocket")
        ObBody(
            "The mesh does its real work while the screen is off — carrying messages for " +
                "you and for people nearby. Android puts apps to sleep to save battery, " +
                "and a sleeping phone drops out of the mesh.",
            Modifier.padding(bottom = 8.dp),
        )
        Faceplate {
            Column(Modifier.padding(14.dp)) {
                TLabel("One Android setting")
                Spacer(Modifier.height(6.dp))
                ObBody(
                    "Allow unrestricted battery so the mesh keeps running. It's built to " +
                        "sip — it wakes briefly, listens, and sleeps again.",
                )
            }
            HDivider()
            Column(Modifier.padding(14.dp)) {
                TLabel("You'll always see one quiet notification")
                Spacer(Modifier.height(6.dp))
                ObBody(
                    "That's Android's rule for apps that work in the background — we make " +
                        "it useful: mesh status at a glance, panic within reach.",
                )
            }
        }
        Spacer(Modifier.weight(1f))
        Spacer(Modifier.height(14.dp))
        if (batteryGranted) {
            PnButton(
                "Continue", BtnKind.PRIMARY, Modifier.fillMaxWidth(),
                sub = "battery access granted — the mesh can work pocketed",
                onClick = {
                    // the permission moment still applies even when battery came pre-granted
                    if (allPermsGranted(ctx)) {
                        onDone()
                    } else {
                        doneAfterPerms = true
                        permLauncher.launch(runtimePerms())
                    }
                },
            )
        } else {
            PnButton(
                "Open battery settings", BtnKind.PRIMARY, Modifier.fillMaxWidth(),
                onClick = {
                    if (!permsAsked) {
                        permsAsked = true
                        permLauncher.launch(runtimePerms())   // battery dialog follows the result
                    } else {
                        Battery.requestGrant(ctx)
                    }
                },
            )
            Spacer(Modifier.height(10.dp))
            PnButton(
                "Not now", BtnKind.PLAIN, Modifier.fillMaxWidth(),
                sub = "the mesh will pause when the screen sleeps",
                onClick = onDone,
            )
        }
        Spacer(Modifier.height(26.dp))
    }
}
