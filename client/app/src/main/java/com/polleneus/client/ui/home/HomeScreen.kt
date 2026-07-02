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
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.polleneus.client.mesh.LocalEvent
import com.polleneus.client.mesh.MeshController
import com.polleneus.client.mesh.MeshState
import com.polleneus.client.ui.components.BigNum
import com.polleneus.client.ui.components.Faceplate
import com.polleneus.client.ui.components.HDivider
import com.polleneus.client.ui.components.KeyCode
import com.polleneus.client.ui.components.Radar
import com.polleneus.client.ui.components.StatusWord
import com.polleneus.client.ui.components.TFoot
import com.polleneus.client.ui.components.TLabel
import com.polleneus.client.ui.components.blinkAlpha
import com.polleneus.client.ui.components.hatched
import com.polleneus.client.ui.theme.MartianMono
import com.polleneus.client.ui.theme.Pn
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

@Composable
fun HomeScreen(controller: MeshController) {
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
        }

        Spacer(Modifier.height(12.dp))

        // ---- pause / resume strip ----
        Row(
            Modifier.fillMaxWidth()
                .border(1.dp, if (paused) Pn.Accent.copy(alpha = 0.45f) else Pn.Line)
                .clickable { if (paused) controller.resume() else controller.pause() }
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

        // ---- panic strip (visual in X1; the two-step ceremony arrives in X4) ----
        Column(
            Modifier.fillMaxWidth()
                .border(1.dp, Pn.Danger.copy(alpha = 0.5f))
                .hatched(Pn.DangerDim)
                .padding(13.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            BasicText(
                "▲ PANIC WIPE — HOLD 2S",
                style = TextStyle(
                    fontFamily = MartianMono, fontSize = 11.sp, fontWeight = FontWeight.W700,
                    letterSpacing = 0.15.em, color = Pn.DangerText,
                ),
            )
            Spacer(Modifier.height(5.dp))
            TFoot("local erase only · other phones keep what they carry", color = Pn.InkFaint)
        }
        Spacer(Modifier.height(8.dp))
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
