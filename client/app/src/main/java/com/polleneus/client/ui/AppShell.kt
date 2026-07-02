package com.polleneus.client.ui

import androidx.compose.foundation.Canvas
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
import com.polleneus.client.mesh.MeshController
import com.polleneus.client.ui.components.TFoot
import com.polleneus.client.ui.components.TLabel
import com.polleneus.client.ui.home.HomeScreen
import com.polleneus.client.ui.theme.MartianMono
import com.polleneus.client.ui.theme.Pn

enum class Tab(val label: String) { MESH("Mesh"), MESSAGES("Messages"), CONTACTS("Contacts") }

@Composable
fun AppShell(controller: MeshController) {
    var tab by remember { mutableStateOf(Tab.MESH) }

    Column(Modifier.fillMaxSize().statusBarsPadding().navigationBarsPadding()) {
        Box(Modifier.weight(1f)) {
            when (tab) {
                Tab.MESH -> HomeScreen(controller)
                Tab.MESSAGES -> ComingInMilestone("Messages", "the inbox lands in X3 — sealed, receipt-free")
                Tab.CONTACTS -> ComingInMilestone("Contacts", "pairing lands in X2 — made in person, not from a list")
            }
        }
        BottomNav(tab, onSelect = { tab = it })
    }
}

/** Honest scaffolding: names the milestone instead of pretending. Removed as X2/X3 land. */
@Composable
private fun ComingInMilestone(title: String, note: String) {
    Column(
        Modifier.fillMaxSize().padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        TLabel(title, color = Pn.InkDim)
        Spacer(Modifier.height(12.dp))
        TFoot(note, color = Pn.InkFaint)
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
