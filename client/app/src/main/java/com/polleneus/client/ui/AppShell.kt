package com.polleneus.client.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.text.BasicText
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.platform.LocalContext
import com.polleneus.client.Prefs
import com.polleneus.client.mesh.MeshController
import com.polleneus.client.service.MeshService
import com.polleneus.client.system.Perms
import com.polleneus.client.ui.components.TFoot
import com.polleneus.client.ui.components.TLabel
import com.polleneus.client.ui.contacts.ContactsScreen
import com.polleneus.client.ui.home.HomeScreen
import com.polleneus.client.ui.honesty.WhatThisProtectsScreen
import com.polleneus.client.ui.messages.ComposeScreen
import com.polleneus.client.ui.messages.MessagesScreen
import com.polleneus.client.ui.onboarding.OnboardingFlow
import com.polleneus.client.ui.pairing.PairingScreen
import com.polleneus.client.ui.panic.PanicConfirmScreen
import com.polleneus.client.ui.panic.PostWipeScreen
import com.polleneus.client.ui.settings.SettingsScreen
import com.polleneus.client.ui.theme.MartianMono
import com.polleneus.client.ui.theme.Pn

enum class Tab(val label: String) { MESH("Mesh"), MESSAGES("Messages"), CONTACTS("Contacts") }

private enum class Overlay { NONE, SETTINGS, HONESTY, PANIC }

/**
 * X4 root routing: onboarding gates the app (the honest deal comes before the mesh), panic
 * routes every entry point (home strip, settings "start over", notification action) through
 * the same step-2 confirm, and the post-wipe state is NOTHING STORED until the human opts
 * back in.
 *
 * @param panicSignal increments each time the notification's Panic action fires.
 * @param ensureIdentity mints the device key WITHOUT bringing the radio up — onboarding
 *   step 1 shows the key; the transport waits for the gate.
 */
@Composable
fun AppShell(
    controller: MeshController,
    panicSignal: Int = 0,
    // Default is deliberately a no-op: resume() would bring the radio up before the gate.
    // MainActivity wires the real identity-only mint; the mock's key is pre-seeded.
    ensureIdentity: () -> Unit = {},
) {
    val ctx = LocalContext.current
    var onboarded by remember { mutableStateOf(Prefs.onboarded(ctx)) }
    var wiped by remember { mutableStateOf(false) }
    var overlay by remember { mutableStateOf(Overlay.NONE) }

    LaunchedEffect(onboarded, wiped) {
        if (!onboarded && !wiped) ensureIdentity()
    }
    LaunchedEffect(panicSignal) {
        if (panicSignal > 0 && onboarded && !wiped) overlay = Overlay.PANIC
    }

    Box(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding()) {
        AppRoutes(
            controller, onboarded, wiped, overlay, ctx,
            setOnboarded = { onboarded = it },
            setWiped = { wiped = it },
            setOverlay = { overlay = it },
        )
    }
}

@Composable
private fun AppRoutes(
    controller: MeshController,
    onboarded: Boolean,
    wiped: Boolean,
    overlay: Overlay,
    ctx: android.content.Context,
    setOnboarded: (Boolean) -> Unit,
    setWiped: (Boolean) -> Unit,
    setOverlay: (Overlay) -> Unit,
) {
    when {
        wiped -> PostWipeScreen(onStartFresh = { setWiped(false) })

        !onboarded -> OnboardingFlow(controller, onDone = {
            Prefs.setOnboarded(ctx)
            setOnboarded(true)
            controller.resume()                     // the radio comes up only past the gate
            if (Perms.ble(ctx)) MeshService.start(ctx)
        })

        overlay == Overlay.PANIC -> PanicConfirmScreen(
            controller,
            onCancel = { setOverlay(Overlay.NONE) },
            onWiped = {
                Prefs.panicReset(ctx)               // factory-fresh: prefs are stored state too
                MeshService.stop(ctx)               // a lingering "active" line would be a lie
                setOverlay(Overlay.NONE)
                setOnboarded(false)
                setWiped(true)
            },
        )

        overlay == Overlay.SETTINGS -> SettingsScreen(
            controller,
            onBack = { setOverlay(Overlay.NONE) },
            onOpenHonesty = { setOverlay(Overlay.HONESTY) },
            onStartOver = { setOverlay(Overlay.PANIC) },
        )

        overlay == Overlay.HONESTY -> WhatThisProtectsScreen(onBack = { setOverlay(Overlay.SETTINGS) })

        else -> MainTabs(
            controller,
            onOpenSettings = { setOverlay(Overlay.SETTINGS) },
            onPanic = { setOverlay(Overlay.PANIC) },
        )
    }
}

@Composable
private fun MainTabs(controller: MeshController, onOpenSettings: () -> Unit, onPanic: () -> Unit) {
    var tab by remember { mutableStateOf(Tab.MESH) }

    var pairingOpen by remember { mutableStateOf(false) }
    var composeOpen by remember { mutableStateOf(false) }

    Column(Modifier.fillMaxSize()) {
        Box(Modifier.weight(1f)) {
            when (tab) {
                Tab.MESH -> HomeScreen(controller, onOpenSettings = onOpenSettings, onPanic = onPanic)
                Tab.MESSAGES ->
                    if (composeOpen) {
                        ComposeScreen(controller, onClose = { composeOpen = false })
                    } else {
                        MessagesScreen(controller)
                    }
                Tab.CONTACTS ->
                    if (pairingOpen) {
                        PairingScreen(controller, onClose = { pairingOpen = false })
                    } else {
                        ContactsScreen(controller, onOpenPairing = { pairingOpen = true })
                    }
            }
            // compose FAB — only on the (non-compose) Messages tab
            if (tab == Tab.MESSAGES && !composeOpen) {
                ComposeFab(
                    Modifier.align(Alignment.BottomEnd).padding(20.dp),
                    onClick = { composeOpen = true },
                )
            }
        }
        BottomNav(tab, onSelect = {
            tab = it
            if (it != Tab.CONTACTS) pairingOpen = false
            if (it != Tab.MESSAGES) composeOpen = false
        })
    }
}

@Composable
private fun ComposeFab(modifier: Modifier = Modifier, onClick: () -> Unit) {
    Box(
        modifier.size(52.dp).background(Pn.Data).clickable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        Canvas(Modifier.size(22.dp)) {
            val s = size.minDimension
            drawLine(Pn.Bg, Offset(s / 2, s * 0.2f), Offset(s / 2, s * 0.8f), s * 0.09f)
            drawLine(Pn.Bg, Offset(s * 0.2f, s / 2), Offset(s * 0.8f, s / 2), s * 0.09f)
        }
    }
}

@Composable
private fun BottomNav(current: Tab, onSelect: (Tab) -> Unit) {
    Column(Modifier.fillMaxWidth()) {
        Box(Modifier.fillMaxWidth().height(1.dp)) {
            Canvas(Modifier.fillMaxSize()) { drawRect(Pn.Line) }
        }
        Row(
            Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 10.dp),
            horizontalArrangement = Arrangement.SpaceEvenly,
        ) {
            Tab.entries.forEach { t ->
                val active = t == current
                Column(
                    Modifier.clickable { onSelect(t) }.padding(horizontal = 18.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                ) {
                    NavIcon(t, tint = if (active) Pn.Accent else Pn.InkGhost)
                    Spacer(Modifier.height(5.dp))
                    BasicText(
                        t.label.uppercase(),
                        style = TextStyle(
                            fontFamily = MartianMono, fontSize = 8.5.sp, letterSpacing = 0.12.em,
                            color = if (active) Pn.Ink else Pn.InkGhost,
                        ),
                    )
                }
            }
        }
    }
}

@Composable
private fun NavIcon(tab: Tab, tint: Color) {
    Canvas(Modifier.size(22.dp)) {
        when (tab) {
            Tab.MESH -> meshGlyph(tint)
            Tab.MESSAGES -> envelopeGlyph(tint)
            Tab.CONTACTS -> contactsGlyph(tint)
        }
    }
}

private fun DrawScope.meshGlyph(tint: Color) {
    val s = size.minDimension
    val stroke = Stroke(width = s * 0.068f)
    val top = Offset(s * 0.5f, s * 0.23f)
    val left = Offset(s * 0.23f, s * 0.73f)
    val right = Offset(s * 0.77f, s * 0.73f)
    drawLine(tint, top, left, stroke.width)
    drawLine(tint, top, right, stroke.width)
    drawLine(tint, left, right, stroke.width)
    listOf(top, left, right).forEach { drawCircle(tint, radius = s * 0.11f, center = it) }
}

private fun DrawScope.envelopeGlyph(tint: Color) {
    val s = size.minDimension
    val w = Stroke(width = s * 0.068f)
    drawRect(
        tint,
        topLeft = Offset(s * 0.14f, s * 0.23f),
        size = androidx.compose.ui.geometry.Size(s * 0.72f, s * 0.54f),
        style = w,
    )
    val p = Path().apply {
        moveTo(s * 0.14f, s * 0.32f)
        lineTo(s * 0.5f, s * 0.57f)
        lineTo(s * 0.86f, s * 0.32f)
    }
    drawPath(p, tint, style = w)
}

private fun DrawScope.contactsGlyph(tint: Color) {
    val s = size.minDimension
    val w = Stroke(width = s * 0.068f)
    drawCircle(tint, radius = s * 0.14f, center = Offset(s * 0.36f, s * 0.36f), style = w)
    val arc = Path().apply {
        moveTo(s * 0.11f, s * 0.82f)
        cubicTo(s * 0.16f, s * 0.6f, s * 0.56f, s * 0.6f, s * 0.61f, s * 0.82f)
    }
    drawPath(arc, tint, style = w)
    drawCircle(tint, radius = s * 0.11f, center = Offset(s * 0.7f, s * 0.41f), style = w)
    val arc2 = Path().apply {
        moveTo(s * 0.68f, s * 0.62f)
        cubicTo(s * 0.8f, s * 0.64f, s * 0.88f, s * 0.72f, s * 0.9f, s * 0.82f)
    }
    drawPath(arc2, tint, style = w)
}
