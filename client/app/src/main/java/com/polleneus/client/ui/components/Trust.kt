package com.polleneus.client.ui.components

import androidx.compose.foundation.border
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.text.BasicText
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.polleneus.client.ui.theme.MartianMono
import com.polleneus.client.ui.theme.Pn

/* ============ trust badges (design system §4) ============ */

enum class BadgeKind { VERIFIED, PENDING, UNVERIFIED, PQ, CLASSICAL }

@Composable
fun TrustBadge(kind: BadgeKind, modifier: Modifier = Modifier) {
    val (text, color) = when (kind) {
        BadgeKind.VERIFIED -> "Verified" to Pn.Data
        BadgeKind.PENDING -> "Pending" to Pn.Accent
        BadgeKind.UNVERIFIED -> "Unverified" to Pn.InkFaint
        BadgeKind.PQ -> "PQ" to Pn.Data
        BadgeKind.CLASSICAL -> "Classical" to Pn.InkFaint
    }
    val boxMod = when (kind) {
        BadgeKind.PQ -> modifier.background(Pn.DataDim)
        BadgeKind.CLASSICAL -> modifier.dashedBorder(Pn.LineStrong)
        BadgeKind.VERIFIED -> modifier.border(1.dp, Pn.Data.copy(alpha = 0.45f))
        BadgeKind.PENDING -> modifier.border(1.dp, Pn.Accent.copy(alpha = 0.45f))
        BadgeKind.UNVERIFIED -> modifier.border(1.dp, Pn.LineStrong)
    }
    Box(boxMod.padding(horizontal = 7.dp, vertical = 3.dp)) {
        BasicText(
            text.uppercase(),
            style = TextStyle(
                fontFamily = MartianMono, fontSize = 8.sp, fontWeight = FontWeight.W500,
                letterSpacing = 0.14.em, color = color,
            ),
        )
    }
}

private fun Modifier.dashedBorder(color: Color): Modifier = drawBehind {
    drawRect(
        color = color,
        style = Stroke(
            width = 1.dp.toPx(),
            pathEffect = PathEffect.dashPathEffect(floatArrayOf(6f, 4f)),
        ),
    )
}

/* ============ instrument buttons ============ */

enum class BtnKind { PRIMARY, OUTLINE_DATA, OUTLINE_DANGER, PLAIN }

@Composable
fun PnButton(
    text: String,
    kind: BtnKind,
    modifier: Modifier = Modifier,
    sub: String? = null,
    onClick: () -> Unit = {},
) {
    val (bg, border, fg) = when (kind) {
        BtnKind.PRIMARY -> Triple(Pn.Data, Pn.Data, Pn.Bg)
        BtnKind.OUTLINE_DATA -> Triple(Color.Transparent, Pn.Data.copy(alpha = 0.55f), Pn.Data)
        BtnKind.OUTLINE_DANGER -> Triple(Color.Transparent, Pn.Danger.copy(alpha = 0.5f), Pn.DangerText)
        BtnKind.PLAIN -> Triple(Color.Transparent, Pn.LineStrong, Pn.InkDim)
    }
    Column(
        modifier
            .background(bg)
            .border(1.dp, border)
            .clickable(role = Role.Button, onClick = onClick)
            .padding(horizontal = 16.dp, vertical = if (sub == null) 14.dp else 11.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = androidx.compose.foundation.layout.Arrangement.Center,
    ) {
        BasicText(
            text.uppercase(),
            style = TextStyle(
                fontFamily = MartianMono, fontSize = 10.5.sp, fontWeight = FontWeight.W700,
                letterSpacing = 0.14.em, color = fg,
            ),
        )
        if (sub != null) {
            BasicText(
                sub.uppercase(),
                Modifier.padding(top = 5.dp),
                style = TextStyle(
                    fontFamily = MartianMono, fontSize = 8.sp, letterSpacing = 0.12.em,
                    color = if (kind == BtnKind.PRIMARY) Pn.Bg.copy(alpha = 0.65f) else Pn.InkFaint,
                ),
            )
        }
    }
}

/* ============ ceremony state rings (verified check / reject cross) ============ */

@Composable
fun StateRing(color: Color, cross: Boolean, modifier: Modifier = Modifier) {
    androidx.compose.foundation.Canvas(modifier.size(86.dp)) {
        val c = Offset(size.width / 2f, size.height / 2f)
        val r = size.minDimension / 2f
        drawCircle(color.copy(alpha = 0.5f), radius = r - 1.dp.toPx(), center = c, style = Stroke(1.dp.toPx()))
        drawCircle(color.copy(alpha = 0.18f), radius = r + 8.dp.toPx(), center = c, style = Stroke(1.dp.toPx()))
        val s = r * 0.42f
        val w = Stroke(2.2f * density)
        if (cross) {
            drawLine(color, Offset(c.x - s, c.y - s), Offset(c.x + s, c.y + s), w.width)
            drawLine(color, Offset(c.x + s, c.y - s), Offset(c.x - s, c.y + s), w.width)
        } else {
            val p = androidx.compose.ui.graphics.Path().apply {
                moveTo(c.x - s, c.y + s * 0.1f)
                lineTo(c.x - s * 0.25f, c.y + s * 0.75f)
                lineTo(c.x + s, c.y - s * 0.6f)
            }
            drawPath(p, color, style = Stroke(w.width))
        }
    }
}

/* ============ small chevrons ============ */

@Composable
fun Chevron(modifier: Modifier = Modifier, color: Color = Pn.InkGhost) {
    androidx.compose.foundation.Canvas(modifier.size(12.dp)) {
        val p = androidx.compose.ui.graphics.Path().apply {
            moveTo(size.width * 0.33f, size.height * 0.17f)
            lineTo(size.width * 0.67f, size.height * 0.5f)
            lineTo(size.width * 0.33f, size.height * 0.83f)
        }
        drawPath(p, color, style = Stroke(1.8f * density))
    }
}

@Composable
fun BackChevron(onClick: () -> Unit, modifier: Modifier = Modifier) {
    androidx.compose.foundation.Canvas(
        modifier
            .size(16.dp)
            .clickable(role = Role.Button, onClick = onClick)
            .semantics { contentDescription = "Back" },
    ) {
        val p = androidx.compose.ui.graphics.Path().apply {
            moveTo(size.width * 0.62f, size.height * 0.19f)
            lineTo(size.width * 0.31f, size.height * 0.5f)
            lineTo(size.width * 0.62f, size.height * 0.81f)
        }
        drawPath(p, Pn.Ink, style = Stroke(1.8f * density))
    }
}
