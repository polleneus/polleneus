package com.polleneus.client.ui.messages

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.polleneus.client.mesh.Contact
import com.polleneus.client.mesh.MeshController
import com.polleneus.client.mesh.ReleaseResult
import com.polleneus.client.mesh.TrustState
import com.polleneus.client.ui.components.BackChevron
import com.polleneus.client.ui.components.BadgeKind
import com.polleneus.client.ui.components.BtnKind
import com.polleneus.client.ui.components.Faceplate
import com.polleneus.client.ui.components.HDivider
import com.polleneus.client.ui.components.PnButton
import com.polleneus.client.ui.components.Radar
import com.polleneus.client.ui.components.TFoot
import com.polleneus.client.ui.components.TLabel
import com.polleneus.client.ui.components.TrustBadge
import com.polleneus.client.ui.theme.Archivo
import com.polleneus.client.ui.theme.MartianMono
import com.polleneus.client.ui.theme.Pn
import java.time.Duration

private data class TtlChoice(val label: String, val duration: Duration)

private val TTL_CHOICES = listOf(
    TtlChoice("1h", Duration.ofHours(1)),
    TtlChoice("12h", Duration.ofHours(12)),
    TtlChoice("2 days", Duration.ofDays(2)),
    TtlChoice("7 days", Duration.ofDays(7)),
)

@Composable
fun ComposeScreen(controller: MeshController, onClose: () -> Unit) {
    val contacts by controller.contacts.collectAsState()
    val maxBytes by controller.maxPlaintextBytes.collectAsState()
    val verified = contacts.filter { it.state == TrustState.VERIFIED }

    var recipient by remember(verified) { mutableStateOf(verified.firstOrNull()) }
    var body by remember { mutableStateOf("") }
    var ttlIndex by remember { mutableStateOf(2) }
    var released by remember { mutableStateOf<ReleaseResult.Released?>(null) }
    var refusal by remember { mutableStateOf<String?>(null) }

    released?.let { r ->
        ReleasedScreen(recipient, TTL_CHOICES[ttlIndex].label, onDone = onClose)
        return
    }

    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp).verticalScroll(rememberScrollState())) {
        Row(
            Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            BackChevron(onClick = onClose)
            Spacer(Modifier.width(12.dp))
            BasicText(
                "NEW MESSAGE",
                style = TextStyle(
                    fontFamily = MartianMono, fontSize = 13.sp, fontWeight = FontWeight.W700,
                    letterSpacing = 0.14.em, color = Pn.Ink,
                ),
            )
        }

        Faceplate {
            // ---- recipient (fail-closed: only verified contacts selectable) ----
            Column(Modifier.padding(14.dp)) {
                TLabel("To")
                Spacer(Modifier.height(8.dp))
                if (verified.isEmpty()) {
                    BasicText(
                        "No verified contacts yet.",
                        style = TextStyle(fontFamily = MartianMono, fontSize = 12.sp, color = Pn.InkFaint),
                    )
                } else {
                    verified.forEach { c ->
                        RecipientChip(c, selected = c.id == recipient?.id, onClick = { recipient = c })
                    }
                }
                Spacer(Modifier.height(9.dp))
                TFoot("only contacts you verified in person can be chosen")
            }
            HDivider()
            // ---- body ----
            Column(Modifier.padding(14.dp)) {
                TLabel("Message")
                Spacer(Modifier.height(8.dp))
                Box(
                    Modifier.fillMaxWidth().heightIn(min = 120.dp)
                        .background(Pn.Panel2).border(1.dp, Pn.Line).padding(12.dp),
                ) {
                    if (body.isEmpty()) {
                        BasicText(
                            "Write your message…",
                            style = TextStyle(fontFamily = Archivo, fontSize = 14.5.sp, color = Pn.InkGhost),
                        )
                    }
                    BasicTextField(
                        value = body,
                        onValueChange = { body = it; refusal = null },
                        textStyle = TextStyle(fontFamily = Archivo, fontSize = 14.5.sp, lineHeight = 22.sp, color = Pn.Ink),
                        cursorBrush = SolidColor(Pn.Data),
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
                Spacer(Modifier.height(8.dp))
                val bytes = body.toByteArray().size
                TFoot("$bytes / $maxBytes bytes", Modifier.fillMaxWidth(),
                    color = if (bytes > maxBytes) Pn.Accent else Pn.InkGhost)
            }
            HDivider()
            // ---- lifetime ----
            Column(Modifier.padding(14.dp)) {
                TLabel("Lifetime — how long it exists, anywhere")
                Spacer(Modifier.height(10.dp))
                Row(Modifier.fillMaxWidth()) {
                    TTL_CHOICES.forEachIndexed { i, choice ->
                        Box(
                            Modifier.weight(1f)
                                .border(1.dp, if (i == ttlIndex) Pn.Data.copy(alpha = 0.55f) else Pn.Line)
                                .background(if (i == ttlIndex) Pn.DataDim else androidx.compose.ui.graphics.Color.Transparent)
                                .clickable { ttlIndex = i }
                                .padding(vertical = 9.dp),
                            contentAlignment = Alignment.Center,
                        ) {
                            BasicText(
                                choice.label.uppercase(),
                                style = TextStyle(
                                    fontFamily = MartianMono, fontSize = 9.5.sp, letterSpacing = 0.1.em,
                                    color = if (i == ttlIndex) Pn.Data else Pn.InkFaint,
                                ),
                            )
                        }
                    }
                }
                Spacer(Modifier.height(9.dp))
                TFoot("after this it fades on every phone it reached — yours and theirs")
            }
        }

        refusal?.let {
            Spacer(Modifier.height(12.dp))
            Box(Modifier.fillMaxWidth().border(1.dp, Pn.Accent.copy(alpha = 0.4f)).background(Pn.AccentDim).padding(12.dp)) {
                BasicText(
                    it,
                    style = TextStyle(fontFamily = MartianMono, fontSize = 10.sp, letterSpacing = 0.05.em, color = Pn.Accent),
                )
            }
        }

        Spacer(Modifier.height(16.dp))
        val canSend = recipient != null && body.isNotBlank() && body.toByteArray().size <= maxBytes
        if (canSend) {
            PnButton(
                "Seal & release to mesh", BtnKind.PRIMARY, Modifier.fillMaxWidth(),
                sub = "no delivery promise — it spreads phone to phone",
                onClick = {
                    val r = controller.send(recipient!!.id, body, TTL_CHOICES[ttlIndex].duration)
                    when (r) {
                        is ReleaseResult.Released -> released = r
                        is ReleaseResult.Refused -> refusal = r.reason
                    }
                },
            )
        } else {
            // fail-closed rendering: disabled + the reason inline
            Column(
                Modifier.fillMaxWidth()
                    .border(1.dp, Pn.Line)
                    .background(hatch())
                    .padding(14.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                BasicText(
                    "SEAL & RELEASE",
                    style = TextStyle(
                        fontFamily = MartianMono, fontSize = 10.5.sp, fontWeight = FontWeight.W700,
                        letterSpacing = 0.14.em, color = Pn.InkGhost,
                    ),
                )
                Spacer(Modifier.height(5.dp))
                TFoot(
                    when {
                        recipient == null -> "verify a contact in person first — pairing"
                        body.isBlank() -> "write a message"
                        else -> "message is larger than the mesh can carry"
                    },
                    color = Pn.InkFaint,
                )
            }
        }
        Spacer(Modifier.height(14.dp))
    }
}

@Composable
private fun RecipientChip(c: Contact, selected: Boolean, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth()
            .border(1.dp, if (selected) Pn.Data.copy(alpha = 0.55f) else Pn.Line)
            .background(if (selected) Pn.DataDim else androidx.compose.ui.graphics.Color.Transparent)
            .clickable(onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        BasicText(
            (c.alias ?: c.keyChunk).uppercase(),
            style = TextStyle(
                fontFamily = MartianMono, fontSize = 12.sp, fontWeight = FontWeight.W500,
                letterSpacing = 0.08.em, color = Pn.Ink,
            ),
        )
        Spacer(Modifier.weight(1f))
        TrustBadge(BadgeKind.VERIFIED)
        if (c.pq) { Spacer(Modifier.width(6.dp)); TrustBadge(BadgeKind.PQ) }
    }
    Spacer(Modifier.height(6.dp))
}

private fun hatch() = androidx.compose.ui.graphics.Brush.linearGradient(
    0f to androidx.compose.ui.graphics.Color.Transparent,
    0.5f to Pn.Panel,
    1f to androidx.compose.ui.graphics.Color.Transparent,
)

/* ---------------- released state ---------------- */

@Composable
private fun ReleasedScreen(recipient: Contact?, ttlLabel: String, onDone: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp).verticalScroll(rememberScrollState())) {
        Row(Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 12.dp)) {
            BasicText(
                "RELEASED",
                style = TextStyle(
                    fontFamily = MartianMono, fontSize = 13.sp, fontWeight = FontWeight.W700,
                    letterSpacing = 0.14.em, color = Pn.Ink,
                ),
            )
        }
        Faceplate {
            Column(
                Modifier.fillMaxWidth().padding(vertical = 30.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Radar(nodes = 0, sweeping = true, modifier = Modifier.height(130.dp).fillMaxWidth())
                Spacer(Modifier.height(20.dp))
                BasicText(
                    "RELEASED TO MESH",
                    style = TextStyle(
                        fontFamily = MartianMono, fontSize = 21.sp, fontWeight = FontWeight.W700,
                        letterSpacing = 0.03.em, color = Pn.Data,
                    ),
                )
                Spacer(Modifier.height(10.dp))
                TFoot("sealed for ${(recipient?.alias ?: recipient?.keyChunk ?: "your contact")} · fades in $ttlLabel", color = Pn.InkFaint)
            }
            HDivider()
            Column(Modifier.padding(14.dp)) {
                TLabel("What happens now")
                Spacer(Modifier.height(6.dp))
                BasicText(
                    "It spreads phone to phone toward your contact. You won't be told when — or if — it arrives. Nobody is. That's the design, not a failure.",
                    style = TextStyle(fontFamily = Archivo, fontSize = 13.sp, lineHeight = 21.sp, color = Pn.InkDim),
                )
            }
        }
        Spacer(Modifier.height(16.dp))
        PnButton("Done", BtnKind.OUTLINE_DATA, Modifier.fillMaxWidth(), onClick = onDone)
        Spacer(Modifier.height(14.dp))
    }
}
