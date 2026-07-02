package com.polleneus.client.ui.contacts

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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.polleneus.client.mesh.Contact
import com.polleneus.client.mesh.MeshController
import com.polleneus.client.mesh.TrustState
import com.polleneus.client.ui.components.BadgeKind
import com.polleneus.client.ui.components.BtnKind
import com.polleneus.client.ui.components.Chevron
import com.polleneus.client.ui.components.Faceplate
import com.polleneus.client.ui.components.HDivider
import com.polleneus.client.ui.components.PnButton
import com.polleneus.client.ui.components.TFoot
import com.polleneus.client.ui.components.TLabel
import com.polleneus.client.ui.components.TrustBadge
import com.polleneus.client.ui.theme.MartianMono
import com.polleneus.client.ui.theme.Pn
import java.time.ZoneId
import java.time.format.DateTimeFormatter

@Composable
fun ContactsScreen(controller: MeshController, onOpenPairing: () -> Unit) {
    val contacts by controller.contacts.collectAsState()
    val verified = contacts.filter { it.state == TrustState.VERIFIED }
    val pending = contacts.filter { it.state == TrustState.PENDING }

    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp).verticalScroll(rememberScrollState())) {
        Row(
            Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            BasicText(
                "CONTACTS",
                style = TextStyle(
                    fontFamily = MartianMono, fontSize = 13.sp, fontWeight = FontWeight.W700,
                    letterSpacing = 0.14.em, color = Pn.Ink,
                ),
            )
            Spacer(Modifier.weight(1f))
            Box(
                Modifier.clickable(onClick = onOpenPairing)
                    .border(1.dp, Pn.Accent.copy(alpha = 0.45f))
                    .padding(horizontal = 9.dp, vertical = 5.dp),
            ) {
                BasicText(
                    "+ PAIR NEW",
                    style = TextStyle(
                        fontFamily = MartianMono, fontSize = 8.5.sp, fontWeight = FontWeight.W500,
                        letterSpacing = 0.14.em, color = Pn.Accent,
                    ),
                )
            }
        }

        if (contacts.isEmpty()) {
            EmptyContacts(onOpenPairing)
            return@Column
        }

        if (verified.isNotEmpty()) {
            TLabel("Verified — ${verified.size}", Modifier.padding(start = 2.dp, top = 4.dp, bottom = 8.dp))
            Faceplate {
                verified.forEachIndexed { i, c ->
                    if (i > 0) HDivider()
                    ContactRow(c)
                }
            }
        }

        if (pending.isNotEmpty()) {
            Spacer(Modifier.height(16.dp))
            TLabel(
                "Pending — ${pending.size} · cannot be sent to",
                Modifier.padding(start = 2.dp, bottom = 8.dp),
                color = Pn.Accent,
            )
            Faceplate(borderColor = Pn.Accent.copy(alpha = 0.25f)) {
                pending.forEachIndexed { i, c ->
                    if (i > 0) HDivider()
                    ContactRow(c)
                }
            }
        }

        Spacer(Modifier.weight(1f))
        TFoot(
            "no online/offline dots — presence doesn't exist here",
            Modifier.align(Alignment.CenterHorizontally).padding(vertical = 12.dp),
            color = Pn.InkGhost,
        )
    }
}

@Composable
private fun ContactRow(c: Contact) {
    val fmt = remember { DateTimeFormatter.ofPattern("MM-dd").withZone(ZoneId.systemDefault()) }
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 15.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            BasicText(
                (c.alias ?: c.keyChunk).uppercase(),
                style = TextStyle(
                    fontFamily = MartianMono, fontSize = 12.5.sp, fontWeight = FontWeight.W500,
                    letterSpacing = 0.08.em,
                    color = if (c.alias != null) Pn.Ink else Pn.InkFaint,
                ),
            )
            Spacer(Modifier.height(5.dp))
            if (c.state == TrustState.VERIFIED) {
                TFoot("${c.keyChunk} · verified ${c.verifiedAt?.let { fmt.format(it) } ?: "—"}")
            } else {
                TFoot("compare codes in person to finish", color = Pn.Accent)
            }
        }
        Spacer(Modifier.width(10.dp))
        when {
            c.state == TrustState.PENDING -> TrustBadge(BadgeKind.PENDING)
            c.pq -> TrustBadge(BadgeKind.PQ)
            else -> TrustBadge(BadgeKind.CLASSICAL)
        }
        Spacer(Modifier.width(12.dp))
        Chevron()
    }
}

@Composable
private fun EmptyContacts(onOpenPairing: () -> Unit) {
    Column(
        Modifier.fillMaxWidth().padding(top = 120.dp, start = 16.dp, end = 16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        BasicText(
            "NO CONTACTS YET",
            style = TextStyle(
                fontFamily = MartianMono, fontSize = 16.sp, fontWeight = FontWeight.W700,
                letterSpacing = 0.1.em, color = Pn.InkDim,
            ),
        )
        Spacer(Modifier.height(14.dp))
        BasicText(
            "Contacts aren't found in a list — they're made in person. " +
                "Meet, both turn on pairing, and compare a short code out loud.",
            style = TextStyle(fontSize = 13.5.sp, lineHeight = 21.sp, color = Pn.InkFaint),
        )
        Spacer(Modifier.height(10.dp))
        BasicText(
            "Nobody can add you remotely. While pairing is off, requests are rejected before you ever see them.",
            style = TextStyle(fontSize = 13.5.sp, lineHeight = 21.sp, color = Pn.InkFaint),
        )
        Spacer(Modifier.height(26.dp))
        PnButton("Open pairing", BtnKind.PRIMARY, onClick = onOpenPairing)
        Spacer(Modifier.height(30.dp))
        TFoot("sending stays locked until a contact is verified — by you")
    }
}
