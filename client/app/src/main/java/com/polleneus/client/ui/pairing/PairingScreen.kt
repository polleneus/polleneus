package com.polleneus.client.ui.pairing

import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
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
import com.polleneus.client.mesh.PairingEvent
import com.polleneus.client.ui.components.BackChevron
import com.polleneus.client.ui.components.BtnKind
import com.polleneus.client.ui.components.Faceplate
import com.polleneus.client.ui.components.KeyCode
import com.polleneus.client.ui.components.PnButton
import com.polleneus.client.ui.components.Radar
import com.polleneus.client.ui.components.StateRing
import com.polleneus.client.ui.components.TFoot
import com.polleneus.client.ui.components.TLabel
import com.polleneus.client.ui.theme.MartianMono
import com.polleneus.client.ui.theme.Pn

/**
 * The security boundary rendered as a ceremony (design brief §5, design system §5).
 * Deliberate choices carried from the mockups: no countdown timer anywhere (time pressure
 * causes rushed compares), equal-size match/mismatch, the confirm button carries its own
 * friction line.
 *
 * Consent semantics: pairing mode broadcasts ONLY while this screen is open — leaving the
 * screen turns it off (DisposableEffect below). Inbound requests while off never surface.
 */
private sealed interface Stage {
    data object Searching : Stage
    data class Found(val peerId: String, val keyChunk: String) : Stage
    data class Sas(val code: String, val peerKey: String) : Stage
    data class Done(val contact: Contact) : Stage
    data object Rejected : Stage
}

@Composable
fun PairingScreen(controller: MeshController, onClose: () -> Unit) {
    var stage by remember { mutableStateOf<Stage>(Stage.Searching) }
    var lastPeerKey by remember { mutableStateOf("") }

    LaunchedEffect(controller) {
        controller.setPairingMode(true)
        controller.pairing.collect { e ->
            stage = when (e) {
                is PairingEvent.PeerFound -> { lastPeerKey = e.keyChunk; Stage.Found(e.peerId, e.keyChunk) }
                is PairingEvent.SasReady -> Stage.Sas(e.code, lastPeerKey)
                is PairingEvent.Verified -> Stage.Done(e.contact)
                is PairingEvent.Rejected -> Stage.Rejected
                is PairingEvent.Failed -> Stage.Rejected
            }
        }
    }
    DisposableEffect(controller) {
        onDispose { controller.setPairingMode(false) }
    }

    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp).verticalScroll(rememberScrollState())) {
        Row(
            Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            BackChevron(onClick = onClose)
            Spacer(Modifier.width(12.dp))
            BasicText(
                when (stage) {
                    is Stage.Sas -> "CONFIRM CODES"
                    is Stage.Done -> "VERIFIED"
                    is Stage.Rejected -> "NOT VERIFIED"
                    else -> "PAIRING"
                },
                style = TextStyle(
                    fontFamily = MartianMono, fontSize = 13.sp, fontWeight = FontWeight.W700,
                    letterSpacing = 0.14.em, color = Pn.Ink,
                ),
            )
        }

        when (val s = stage) {
            is Stage.Searching -> SearchFound(found = null, onBegin = {})
            is Stage.Found -> SearchFound(found = s, onBegin = { controller.beginExchange(s.peerId) })
            is Stage.Sas -> SasCompare(
                code = s.code, peerKey = s.peerKey,
                onMatch = { controller.confirmSasMatch() },
                onMismatch = { controller.rejectSasMismatch() },
            )
            is Stage.Done -> VerifiedResult(
                contact = s.contact,
                onDone = { alias ->
                    if (alias.isNotBlank()) controller.setAlias(s.contact.id, alias.trim())
                    onClose()
                },
            )
            is Stage.Rejected -> RejectedResult(
                onDone = onClose,
                onRetry = {
                    controller.setPairingMode(false)
                    controller.setPairingMode(true)
                    stage = Stage.Searching
                },
            )
        }
    }
}

/* ---------------- act 1: broadcasting + peer found ---------------- */

@Composable
private fun SearchFound(found: Stage.Found?, onBegin: () -> Unit) {
    Faceplate {
        Column(Modifier.padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(width = 30.dp, height = 16.dp).border(1.dp, Pn.Data)) {
                    Box(
                        Modifier.align(Alignment.CenterEnd).padding(2.dp)
                            .size(width = 12.dp, height = 10.dp).background(Pn.Data),
                    )
                }
                Spacer(Modifier.width(10.dp))
                TLabel("Pairing mode — on", color = Pn.Data)
            }
            Spacer(Modifier.height(9.dp))
            TFoot("broadcasting only while this screen is open · requests while off are auto-rejected")
        }
    }

    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
        Radar(
            nodes = if (found != null) 1 else 0,
            sweeping = true,
            modifier = Modifier.padding(top = 26.dp, bottom = 20.dp).size(170.dp),
        )
        TLabel(
            if (found != null) "One device in pairing range" else "Listening for a nearby device…",
            live = found != null,
        )
    }

    Spacer(Modifier.height(18.dp))

    if (found != null) {
        Faceplate {
            Column(Modifier.padding(14.dp)) {
                TLabel("Device found")
                Spacer(Modifier.height(6.dp))
                KeyCode(found.keyChunk, color = Pn.Ink)
                Spacer(Modifier.height(9.dp))
                TFoot("stand within a few meters — pairing is a two-person, in-person act")
            }
        }
        Spacer(Modifier.height(14.dp))
        PnButton("Begin key exchange", BtnKind.PRIMARY, Modifier.fillMaxWidth(), onClick = onBegin)
    }

    Spacer(Modifier.height(26.dp))
    TFoot(
        "next: both screens show a code — you'll compare them out loud",
        Modifier.fillMaxWidth().padding(bottom = 14.dp),
    )
}

/* ---------------- act 2: the SAS compare ---------------- */

@Composable
private fun SasCompare(code: String, peerKey: String, onMatch: () -> Unit, onMismatch: () -> Unit) {
    BasicText(
        "Both screens now show a code. Read it aloud to each other. " +
            "Confirm only if both codes are exactly the same.",
        Modifier.padding(top = 4.dp, bottom = 14.dp),
        style = TextStyle(fontSize = 13.5.sp, lineHeight = 21.sp, color = Pn.InkDim),
    )

    Faceplate {
        Column(
            Modifier.fillMaxWidth().padding(top = 16.dp, bottom = 22.dp, start = 14.dp, end = 14.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            TLabel("This code · $peerKey sees the same one")
            Row(Modifier.padding(top = 22.dp, bottom = 16.dp), horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                code.split(" ").forEach { group ->
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        BasicText(
                            group,
                            softWrap = false,
                            style = TextStyle(
                                fontFamily = MartianMono, fontSize = 34.sp, fontWeight = FontWeight.W300,
                                letterSpacing = 0.06.em, color = Pn.Ink,
                            ),
                        )
                        Spacer(Modifier.height(9.dp))
                        Box(Modifier.width(64.dp).height(2.dp).background(Pn.Data))
                    }
                }
            }
            TFoot("same code on both screens = no one is standing in the middle")
        }
    }

    Spacer(Modifier.height(22.dp))
    // equal-size match/mismatch is a design-system rule — IntrinsicSize keeps heights identical
    Row(
        Modifier.fillMaxWidth().height(IntrinsicSize.Min),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        PnButton(
            "✕ Doesn't match", BtnKind.OUTLINE_DANGER,
            Modifier.weight(1f).fillMaxHeight(),
            sub = "stop — someone may be interfering", onClick = onMismatch,
        )
        PnButton(
            "✓ It matches", BtnKind.PRIMARY,
            Modifier.weight(1f).fillMaxHeight(),
            sub = "only after reading it aloud", onClick = onMatch,
        )
    }

    Spacer(Modifier.height(20.dp))
    TFoot(
        "no time limit — this check is the whole protection. take your time.",
        Modifier.fillMaxWidth().padding(bottom = 14.dp),
    )
}

/* ---------------- act 3a: verified + local naming ---------------- */

@Composable
private fun VerifiedResult(contact: Contact, onDone: (String) -> Unit) {
    var alias by remember { mutableStateOf("") }

    Faceplate {
        Column(
            Modifier.fillMaxWidth().padding(vertical = 30.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            StateRing(Pn.Data, cross = false)
            Spacer(Modifier.height(20.dp))
            BasicText(
                "VERIFIED — BY YOU",
                style = TextStyle(
                    fontFamily = MartianMono, fontSize = 21.sp, fontWeight = FontWeight.W700,
                    letterSpacing = 0.03.em, color = Pn.Data,
                ),
            )
            Spacer(Modifier.height(10.dp))
            TFoot("${contact.keyChunk} · ${if (contact.pq) "post-quantum exchange" else "classical exchange"}", color = Pn.InkFaint)
        }
        com.polleneus.client.ui.components.HDivider()
        Column(Modifier.padding(14.dp)) {
            TLabel("What \"verified\" means")
            Spacer(Modifier.height(6.dp))
            BasicText(
                "You compared the codes in person. The app can't do that check for you — this mark means you did it.",
                style = TextStyle(fontSize = 13.sp, lineHeight = 21.sp, color = Pn.InkDim),
            )
        }
        com.polleneus.client.ui.components.HDivider()
        Column(Modifier.padding(14.dp)) {
            TLabel("Name them on this phone")
            Spacer(Modifier.height(8.dp))
            BasicTextField(
                value = alias,
                onValueChange = { alias = it },
                singleLine = true,
                textStyle = TextStyle(
                    fontFamily = MartianMono, fontSize = 13.sp, letterSpacing = 0.05.em, color = Pn.Ink,
                ),
                cursorBrush = SolidColor(Pn.Data),
                modifier = Modifier.fillMaxWidth().background(Pn.Panel2)
                    .border(1.dp, Pn.Line).padding(12.dp),
            )
            Spacer(Modifier.height(9.dp))
            TFoot("only you see this name — it never travels with a message")
        }
    }

    Spacer(Modifier.height(16.dp))
    PnButton(
        "Done — sending unlocked", BtnKind.PRIMARY, Modifier.fillMaxWidth(),
        onClick = { onDone(alias) },
    )
    Spacer(Modifier.height(14.dp))
}

/* ---------------- act 3b: codes didn't match ---------------- */

@Composable
private fun RejectedResult(onDone: () -> Unit, onRetry: () -> Unit) {
    Faceplate {
        Column(
            Modifier.fillMaxWidth().padding(vertical = 30.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            StateRing(Pn.DangerText, cross = true)
            Spacer(Modifier.height(20.dp))
            BasicText(
                "CODES DIDN'T MATCH",
                style = TextStyle(
                    fontFamily = MartianMono, fontSize = 20.sp, fontWeight = FontWeight.W700,
                    letterSpacing = 0.03.em, color = Pn.DangerText,
                ),
            )
            Spacer(Modifier.height(10.dp))
            TFoot("the keys were thrown away · nothing was saved", color = Pn.InkFaint)
        }
        com.polleneus.client.ui.components.HDivider()
        Column(Modifier.padding(14.dp)) {
            TLabel("What this can mean")
            Spacer(Modifier.height(6.dp))
            BasicText(
                "Sometimes it's a radio glitch. But it is also exactly what an interception looks like — someone standing between your two phones.",
                style = TextStyle(fontSize = 13.sp, lineHeight = 21.sp, color = Pn.InkDim),
            )
        }
        com.polleneus.client.ui.components.HDivider()
        Column(Modifier.padding(14.dp)) {
            TLabel("What to do")
            Spacer(Modifier.height(6.dp))
            BasicText(
                "Move somewhere else and try again. If it fails twice, take it seriously — talk in person, not over the mesh.",
                style = TextStyle(fontSize = 13.sp, lineHeight = 21.sp, color = Pn.InkDim),
            )
        }
    }

    Spacer(Modifier.height(16.dp))
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        PnButton("Done", BtnKind.PLAIN, Modifier.weight(1f), onClick = onDone)
        PnButton("Try again", BtnKind.OUTLINE_DATA, Modifier.weight(1f), onClick = onRetry)
    }
    Spacer(Modifier.height(14.dp))
}
