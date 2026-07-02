package com.polleneus.client.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.polleneus.client.mesh.LocalEvent
import com.polleneus.client.mesh.MeshController
import com.polleneus.client.mesh.MeshState
import androidx.compose.ui.geometry.Offset
import com.polleneus.client.ui.components.BigNum
import com.polleneus.client.ui.components.Faceplate
import com.polleneus.client.ui.components.HDivider
import com.polleneus.client.ui.components.HoldToConfirm
import com.polleneus.client.ui.components.KeyCode
import com.polleneus.client.ui.components.Radar
import com.polleneus.client.ui.components.StatusWord
import com.polleneus.client.ui.components.TFoot
import com.polleneus.client.ui.components.TLabel
import com.polleneus.client.ui.components.blinkAlpha
import com.polleneus.client.ui.theme.Archivo
import com.polleneus.client.ui.theme.MartianMono
import com.polleneus.client.ui.theme.Pn
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

@Composable
fun HomeScreen(
    controller: MeshController,
    onOpenSettings: () -> Unit = {},
    onPanic: () -> Unit = {},
) {
    val state by controller.meshState.collectAsState()
    val nearby by controller.nearbyDevices.collectAsState()
    val carrying by controller.carryingCount.collectAsState()
    val key by controller.deviceKey.collectAsState()

    val log = remember { mutableStateListOf<LocalEvent>() }
    LaunchedEffect(controller) {
        controller.activity.collect { e ->
            log.add(0, e)
            while (log.size > 3) log.removeAt(log.size - 1)
        }
    }

    val paused = state == MeshState.PAUSED

    Column(
        Modifier.fillMaxSize().padding(horizontal = 16.dp).verticalScroll(rememberScrollState()),
    ) {
        // ---- app row ----
        Row(
            Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            BasicText(
                "POLLENEUS",
                style = TextStyle(
                    fontFamily = MartianMono, fontSize = 13.sp, fontWeight = FontWeight.W500,
                    letterSpacing = 0.14.em, color = Pn.Ink,
                ),
            )
            Spacer(Modifier.width(5.dp))
            Box(Modifier.size(width = 8.dp, height = 13.dp).alpha(blinkAlpha()).background(Pn.Accent))
            Spacer(Modifier.weight(1f))
            SettingsGlyph(
                Modifier
                    .clickable(role = Role.Button, onClick = onOpenSettings)
                    .semantics { contentDescription = "Settings" }
                    .padding(4.dp),
            )
        }

        // ---- faceplate ----
        Faceplate(borderColor = if (paused) Pn.AccentDim else Pn.Line) {
            // mesh tile
            Box(Modifier.fillMaxWidth().height(150.dp)) {
                Column(Modifier.fillMaxSize().padding(start = 14.dp, top = 14.dp, bottom = 12.dp)) {
                    TLabel(
                        if (paused) "Mesh · Paused" else "Mesh · Relay",
                        live = true,
                        color = if (paused) Pn.Accent else Pn.InkFaint,
                    )
                    Spacer(Modifier.weight(1f))
                    StatusWord(
                        when (state) {
                            MeshState.RELAYING -> "Relaying"
                            MeshState.LISTENING -> "Listening"
                            MeshState.PAUSED -> "Paused"
                        },
                        color = if (paused) Pn.Accent else Pn.Ink,
                    )
                    Spacer(Modifier.height(8.dp))
                    TFoot(
                        when (state) {
                            MeshState.RELAYING -> "store·carry·forward / no servers"
                            MeshState.LISTENING -> "no servers to reach — only other phones"
                            MeshState.PAUSED -> "not carrying · not receiving · not relaying"
                        },
                        color = Pn.InkFaint,
                    )
                }
                Radar(
                    nodes = if (paused) 0 else nearby,
                    sweeping = !paused,
                    modifier = Modifier.align(Alignment.TopEnd).padding(top = 12.dp, end = 14.dp).size(112.dp),
                )
            }
            HDivider()

            // nearby / carrying
            Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min)) {
                Box(Modifier.weight(1f).padding(14.dp)) {
                    Column {
                        TLabel("Nearby")
                        Spacer(Modifier.height(10.dp))
                        BigNum(
                            value = if (paused) "—" else nearby.toString(),
                            unit = if (paused) "" else "devices",
                            caption = when {
                                paused -> "not looking while paused"
                                nearby == 0 -> "the mesh starts with two"
                                else -> "varies as phones move"
                            },
                            valueColor = if (paused) Pn.InkGhost else Pn.Ink,
                        )
                    }
                }
                Box(Modifier.width(1.dp).fillMaxHeight().background(Pn.Line))
                Box(Modifier.weight(1f).padding(14.dp)) {
                    Column {
                        TLabel("Carrying")
                        Spacer(Modifier.height(10.dp))
                        BigNum(
                            value = carrying.toString(),
                            unit = "sealed",
                            caption = when {
                                paused -> "held — not forwarded while paused"
                                carrying == 0 -> "you'll carry for others as they appear"
                                else -> "unreadable by this phone"
                            },
                        )
                    }
                }
            }
            HDivider()

            // device key
            Column(Modifier.fillMaxWidth().padding(14.dp)) {
                TLabel("Device key · no account")
                Spacer(Modifier.height(8.dp))
                KeyCode(if (key.isEmpty()) "— nothing stored —" else key,
                    color = if (key.isEmpty()) Pn.InkGhost else Pn.InkDim)
            }

            // X5 — the honest context tile (review-05): alone and paused are states the
            // instrument explains, never error-styles. Both read REAL device signals.
            if (paused) {
                HDivider()
                PausedMeansTile(carrying)
            } else if (nearby == 0) {
                HDivider()
                AloneTile()
            }
        }

        Spacer(Modifier.height(12.dp))

        // ---- pause / resume strip ----
        Row(
            Modifier.fillMaxWidth()
                .border(1.dp, if (paused) Pn.Accent.copy(alpha = 0.45f) else Pn.Line)
                .clickable(role = Role.Switch) { if (paused) controller.resume() else controller.pause() }
                .semantics { stateDescription = if (paused) "Mesh paused" else "Mesh active" }
                .padding(horizontal = 14.dp, vertical = 11.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // toggle glyph
            Box(
                Modifier.size(width = 30.dp, height = 16.dp)
                    .border(1.dp, if (paused) Pn.InkGhost else Pn.Data),
            ) {
                Box(
                    Modifier.align(if (paused) Alignment.CenterStart else Alignment.CenterEnd)
                        .padding(2.dp).size(width = 12.dp, height = 10.dp)
                        .background(if (paused) Pn.InkGhost else Pn.Data),
                )
            }
            Spacer(Modifier.width(10.dp))
            BasicText(
                (if (paused) "Mesh paused — tap to resume" else "Mesh active — tap to pause").uppercase(),
                style = TextStyle(
                    fontFamily = MartianMono, fontSize = 9.5.sp, letterSpacing = 0.14.em,
                    color = if (paused) Pn.Accent else Pn.InkFaint,
                ),
            )
        }

        Spacer(Modifier.height(12.dp))

        // ---- local activity ----
        Faceplate {
            Column(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 11.dp)) {
                TLabel("Local activity")
                Spacer(Modifier.height(8.dp))
                if (log.isEmpty()) {
                    TFoot("nothing yet — events appear as the mesh works")
                } else {
                    log.forEach { e -> LogLine(e) }
                }
            }
        }

        Spacer(Modifier.weight(1f))
        Spacer(Modifier.height(16.dp))

        // ---- panic strip: STEP 1 of the two-step ceremony (a completed 2s hold opens the
        // confirm screen; a tap does nothing — design system §4/§5) ----
        HoldToConfirm(
            text = "▲ Panic wipe — hold 2s",
            sub = "local erase only · other phones keep what they carry",
            onComplete = onPanic,
        )
        Spacer(Modifier.height(8.dp))
    }
}

/** Zero-nearby is the app working, not failing (design system §5 / review-05 frame 1). */
@Composable
private fun AloneTile() {
    Column(Modifier.fillMaxWidth().padding(14.dp)) {
        TLabel("Nothing nearby right now")
        Spacer(Modifier.height(6.dp))
        BasicText(
            buildAnnotatedString {
                append(
                    "That's normal. Leave it running — it listens from your pocket and " +
                        "joins in the moment another phone appears. ",
                )
                withStyle(SpanStyle(color = Pn.Ink, fontWeight = FontWeight.W600)) {
                    append("To send your first message, pair with someone in person.")
                }
            },
            style = TextStyle(
                fontFamily = Archivo, fontSize = 13.sp, lineHeight = 21.sp, color = Pn.InkDim,
            ),
        )
    }
}

/**
 * Paused names its social cost and reads two REAL device signals: the battery level the
 * pause is presumably saving, and whether bluetooth is even on (the mesh can't resume
 * without it). No stealth claim anywhere — pausing stops the app's radio work; it does
 * not make the phone unobservable (Q6 wording rule).
 */
@Composable
private fun PausedMeansTile(carrying: Int) {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val battery = remember {
        (ctx.getSystemService(android.content.Context.BATTERY_SERVICE) as android.os.BatteryManager)
            .getIntProperty(android.os.BatteryManager.BATTERY_PROPERTY_CAPACITY)
    }
    val btOn = remember {
        (ctx.getSystemService(android.content.Context.BLUETOOTH_SERVICE) as android.bluetooth.BluetoothManager)
            .adapter?.isEnabled == true
    }
    Column(Modifier.fillMaxWidth().padding(14.dp)) {
        TLabel("What paused means")
        Spacer(Modifier.height(6.dp))
        BasicText(
            buildAnnotatedString {
                append("Messages for you can't arrive")
                if (carrying > 0) {
                    append(", and the $carrying you're holding ${if (carrying == 1) "waits" else "wait"}")
                }
                append(". People counting on this phone as a relay lose it. ")
                withStyle(SpanStyle(color = Pn.Ink, fontWeight = FontWeight.W600)) {
                    append("Good for saving battery — $battery% left.")
                }
            },
            style = TextStyle(
                fontFamily = Archivo, fontSize = 13.sp, lineHeight = 21.sp, color = Pn.InkDim,
            ),
        )
        if (!btOn) {
            Spacer(Modifier.height(8.dp))
            TFoot("bluetooth is off — the mesh has no radio until it's back on", color = Pn.Accent)
        }
    }
}

@Composable
private fun SettingsGlyph(modifier: Modifier = Modifier) {
    androidx.compose.foundation.Canvas(modifier.size(18.dp)) {
        val s = size.minDimension
        val w = s * 0.075f
        // instrument sliders: three rails, three offset knobs
        listOf(0.25f, 0.5f, 0.75f).forEachIndexed { i, y ->
            drawLine(Pn.InkFaint, Offset(s * 0.08f, s * y), Offset(s * 0.92f, s * y), w)
            val x = listOf(0.32f, 0.68f, 0.45f)[i]
            drawCircle(Pn.InkDim, radius = s * 0.1f, center = Offset(s * x, s * y))
        }
    }
}

@Composable
private fun LogLine(e: LocalEvent) {
    val fmt = remember { DateTimeFormatter.ofPattern("HH:mm").withZone(ZoneId.systemDefault()) }
    val text = when (e) {
        is LocalEvent.Relayed -> "relayed ${e.count} sealed message${plural(e.count)} onward"
        is LocalEvent.PickedUp -> "picked up ${e.count} sealed message${plural(e.count)} nearby"
        is LocalEvent.Faded -> "${e.count} message${plural(e.count)} faded (lifetime over)"
    }
    Row(Modifier.padding(vertical = 3.dp)) {
        BasicText(
            fmt.format(e.at),
            style = TextStyle(
                fontFamily = MartianMono, fontSize = 8.5.sp, letterSpacing = 0.08.em, color = Pn.InkDim,
            ),
        )
        Spacer(Modifier.width(12.dp))
        TFoot(text, color = Pn.InkFaint)
    }
}

private fun plural(n: Int) = if (n == 1) "" else "s"

private fun fmtInstant(fmt: DateTimeFormatter, at: Instant): String = fmt.format(at)
