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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.polleneus.client.mesh.Contact
import com.polleneus.client.mesh.MeshController
import com.polleneus.client.mesh.Message
import com.polleneus.client.mesh.Sender
import com.polleneus.client.ui.components.BadgeKind
import com.polleneus.client.ui.components.Faceplate
import com.polleneus.client.ui.components.HDivider
import com.polleneus.client.ui.components.TFoot
import com.polleneus.client.ui.components.TLabel
import com.polleneus.client.ui.components.TrustBadge
import com.polleneus.client.ui.theme.Archivo
import com.polleneus.client.ui.theme.MartianMono
import com.polleneus.client.ui.theme.Pn
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/** Resolve a sender to its display label THROUGH the trust store — never a wire-supplied name. */
private fun senderLabel(sender: Sender, contacts: List<Contact>): Pair<String, BadgeKind> = when (sender) {
    is Sender.VerifiedContact -> {
        val c = contacts.find { it.id == sender.contactId }
        (c?.alias ?: c?.keyChunk ?: "verified contact") to BadgeKind.VERIFIED
    }
    Sender.Unproven -> "sender unproven" to BadgeKind.UNVERIFIED
}

@Composable
fun MessagesScreen(controller: MeshController) {
    val inbox by controller.inbox.collectAsState()
    val contacts by controller.contacts.collectAsState()
    var open by remember { androidx.compose.runtime.mutableStateOf<Message?>(null) }

    val current = open
    if (current != null) {
        MessageDetail(current, contacts, onBack = { open = null }, onWipe = {
            controller.wipeMyCopy(current.id); open = null
        })
        return
    }

    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp)) {
        Row(
            Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            BasicText(
                "MESSAGES",
                style = TextStyle(
                    fontFamily = MartianMono, fontSize = 13.sp, fontWeight = FontWeight.W700,
                    letterSpacing = 0.14.em, color = Pn.Ink,
                ),
            )
            Spacer(Modifier.weight(1f))
            val unread = inbox.count { !it.openedLocally }
            if (unread > 0) TLabel("$unread new", color = Pn.Accent)
        }

        if (inbox.isEmpty()) {
            EmptyInbox()
            return@Column
        }

        TFoot(
            "sealed for you · no read receipts exist — senders never know",
            Modifier.padding(start = 2.dp, bottom = 10.dp),
        )
        Column(Modifier.verticalScroll(rememberScrollState())) {
            Faceplate {
                inbox.forEachIndexed { i, m ->
                    if (i > 0) HDivider()
                    MessageRow(m, contacts, onClick = { open = m })
                }
            }
            Spacer(Modifier.height(16.dp))
            TFoot("messages fade — nothing is archived here", Modifier.fillMaxWidth().padding(bottom = 12.dp))
        }
    }
}

@Composable
private fun MessageRow(m: Message, contacts: List<Contact>, onClick: () -> Unit) {
    val now = remember { Instant.now() }
    val (who, badge) = senderLabel(m.sender, contacts)
    val timeFmt = remember { DateTimeFormatter.ofPattern("HH:mm").withZone(ZoneId.systemDefault()) }
    val unread = !m.openedLocally
    val frac = fadeFraction(m.receivedAt, m.fadesAt, now)

    Row(
        Modifier.fillMaxWidth().clickable(onClick = onClick)
            .padding(start = if (unread) 13.dp else 16.dp, top = 14.dp, end = 14.dp, bottom = 12.dp),
    ) {
        if (unread) Box(Modifier.width(3.dp).height(52.dp).background(Pn.Accent).padding(end = 3.dp))
        Column(Modifier.padding(start = if (unread) 10.dp else 0.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                TrustBadge(badge)
                Spacer(Modifier.width(8.dp))
                BasicText(
                    who.uppercase(),
                    style = TextStyle(
                        fontFamily = MartianMono, fontSize = 10.5.sp, fontWeight = FontWeight.W500,
                        letterSpacing = 0.1.em,
                        color = if (badge == BadgeKind.UNVERIFIED) Pn.InkFaint else Pn.Ink,
                    ),
                )
                Spacer(Modifier.weight(1f))
                BasicText(
                    timeFmt.format(m.receivedAt),
                    style = TextStyle(
                        fontFamily = MartianMono, fontSize = 8.5.sp, letterSpacing = 0.08.em, color = Pn.InkGhost,
                    ),
                )
            }
            Spacer(Modifier.height(8.dp))
            BasicText(
                m.body,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
                style = TextStyle(
                    fontFamily = Archivo, fontSize = 13.5.sp, lineHeight = 20.sp,
                    color = if (unread) Pn.Ink else Pn.InkDim,
                ),
            )
            Spacer(Modifier.height(9.dp))
            TtlBar(frac, fadeLabel(now, m.fadesAt), urgent = frac < 0.05f)
        }
    }
}

@Composable
private fun EmptyInbox() {
    Column(
        Modifier.fillMaxWidth().padding(top = 120.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        BasicText(
            "NOTHING HERE",
            style = TextStyle(
                fontFamily = MartianMono, fontSize = 16.sp, fontWeight = FontWeight.W700,
                letterSpacing = 0.1.em, color = Pn.InkDim,
            ),
        )
        Spacer(Modifier.height(14.dp))
        BasicText(
            "Sealed messages for you arrive over the mesh and fade after their lifetime. " +
                "An empty inbox is normal — nothing is archived, nothing is missing.",
            style = TextStyle(fontSize = 13.5.sp, lineHeight = 21.sp, color = Pn.InkFaint),
        )
        Spacer(Modifier.height(10.dp))
        BasicText(
            "No refresh, no sync, no server to check. When something arrives, it's here.",
            style = TextStyle(fontSize = 13.5.sp, lineHeight = 21.sp, color = Pn.InkFaint),
        )
        Spacer(Modifier.height(24.dp))
        TFoot("senders are never told when you read — there are no read receipts")
    }
}

/* ---------------- message detail ---------------- */

@Composable
private fun MessageDetail(m: Message, contacts: List<Contact>, onBack: () -> Unit, onWipe: () -> Unit) {
    val now = remember { Instant.now() }
    val (who, badge) = senderLabel(m.sender, contacts)
    val contact = (m.sender as? Sender.VerifiedContact)?.let { s -> contacts.find { it.id == s.contactId } }
    val dateFmt = remember { DateTimeFormatter.ofPattern("MM-dd").withZone(ZoneId.systemDefault()) }
    val timeFmt = remember { DateTimeFormatter.ofPattern("HH:mm").withZone(ZoneId.systemDefault()) }

    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp).verticalScroll(rememberScrollState())) {
        Row(
            Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            com.polleneus.client.ui.components.BackChevron(onClick = onBack)
            Spacer(Modifier.width(12.dp))
            BasicText(
                "MESSAGE",
                style = TextStyle(
                    fontFamily = MartianMono, fontSize = 13.sp, fontWeight = FontWeight.W700,
                    letterSpacing = 0.14.em, color = Pn.Ink,
                ),
            )
            Spacer(Modifier.weight(1f))
            TrustBadge(badge)
        }

        Faceplate {
            Column(Modifier.padding(14.dp)) {
                TLabel(if (badge == BadgeKind.VERIFIED) "From · your contact" else "From · unproven sender")
                Spacer(Modifier.height(6.dp))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    BasicText(
                        who.uppercase(),
                        style = TextStyle(
                            fontFamily = MartianMono, fontSize = 13.sp, fontWeight = FontWeight.W500,
                            letterSpacing = 0.08.em,
                            color = if (badge == BadgeKind.UNVERIFIED) Pn.InkFaint else Pn.Ink,
                        ),
                    )
                    if (contact?.pq == true) { Spacer(Modifier.width(10.dp)); TrustBadge(BadgeKind.PQ) }
                }
                Spacer(Modifier.height(9.dp))
                TFoot(
                    if (badge == BadgeKind.VERIFIED)
                        "signature matched the key you verified in person${contact?.verifiedAt?.let { " on ${dateFmt.format(it)}" } ?: ""}"
                    else "no key you verified matches — treat with caution",
                )
            }
        }

        BasicText(
            m.body,
            Modifier.padding(vertical = 20.dp, horizontal = 4.dp),
            style = TextStyle(fontFamily = Archivo, fontSize = 15.5.sp, lineHeight = 25.sp, color = Pn.Ink),
        )

        Faceplate {
            Column(Modifier.padding(14.dp)) {
                MetaKv("Received", "${timeFmt.format(m.receivedAt)} · this device's clock")
                HDivider()
                Row(
                    Modifier.fillMaxWidth().padding(vertical = 9.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    TLabel("Fades")
                    Spacer(Modifier.weight(1f))
                    TtlBar(
                        fadeFraction(m.receivedAt, m.fadesAt, now),
                        fadeLabel(now, m.fadesAt).removePrefix("fades ").let { "in $it".replace("in in ", "in ") },
                        urgent = fadeFraction(m.receivedAt, m.fadesAt, now) < 0.05f,
                    )
                }
                HDivider()
                MetaKv("Route", "unknown — by design")
                Spacer(Modifier.height(8.dp))
                TFoot("when it fades, it fades on every phone it reached")
            }
        }

        Spacer(Modifier.height(16.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            com.polleneus.client.ui.components.PnButton(
                "Wipe my copy", com.polleneus.client.ui.components.BtnKind.OUTLINE_DANGER,
                Modifier.weight(1f), sub = "this phone only", onClick = onWipe,
            )
        }
        Spacer(Modifier.height(14.dp))
    }
}

@Composable
private fun MetaKv(k: String, v: String) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = 9.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        TLabel(k)
        Spacer(Modifier.weight(1f))
        BasicText(
            v.uppercase(),
            style = TextStyle(
                fontFamily = MartianMono, fontSize = 9.sp, letterSpacing = 0.08.em, color = Pn.InkDim,
            ),
        )
    }
}
