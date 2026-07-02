package com.polleneus.client.ui.components

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import androidx.compose.foundation.text.BasicText
import com.polleneus.client.ui.theme.MartianMono
import com.polleneus.client.ui.theme.Pn

/* ============ the instrument text voice (design system §4/§6) ============ */

/** Uppercase mono label. `live` adds the blinking attention square. */
@Composable
fun TLabel(text: String, modifier: Modifier = Modifier, color: Color = Pn.InkFaint, live: Boolean = false) {
    Row(modifier, verticalAlignment = Alignment.CenterVertically) {
        if (live) {
            Box(Modifier.size(6.dp).alpha(blinkAlpha()).background(Pn.Accent))
            Spacer(Modifier.width(7.dp))
        }
        BasicText(
            text.uppercase(),
            style = TextStyle(
                fontFamily = MartianMono, fontSize = 9.sp, fontWeight = FontWeight.W500,
                letterSpacing = 0.16.em, color = color,
            ),
        )
    }
}

/** The honest micro-caption. A surfaced number without one is a review defect. */
@Composable
fun TFoot(text: String, modifier: Modifier = Modifier, color: Color = Pn.InkGhost) {
    BasicText(
        text.uppercase(),
        modifier,
        style = TextStyle(
            fontFamily = MartianMono, fontSize = 8.5.sp, letterSpacing = 0.1.em,
            color = color, lineHeight = 15.sp,
        ),
    )
}

@Composable
fun StatusWord(text: String, color: Color = Pn.Ink, size: Int = 23) {
    BasicText(
        text.uppercase(),
        style = TextStyle(
            fontFamily = MartianMono, fontSize = size.sp, fontWeight = FontWeight.W700,
            letterSpacing = 0.03.em, color = color,
        ),
    )
}

@Composable
fun BigNum(value: String, unit: String, caption: String, modifier: Modifier = Modifier, valueColor: Color = Pn.Ink) {
    Column(modifier) {
        Row(verticalAlignment = Alignment.Bottom) {
            BasicText(
                value,
                style = TextStyle(
                    fontFamily = MartianMono, fontSize = 30.sp, fontWeight = FontWeight.W300,
                    color = valueColor,
                ),
            )
            Spacer(Modifier.width(6.dp))
            BasicText(
                unit.uppercase(),
                Modifier.padding(bottom = 5.dp),
                style = TextStyle(
                    fontFamily = MartianMono, fontSize = 10.sp, letterSpacing = 0.1.em,
                    color = Pn.InkFaint,
                ),
            )
        }
        Spacer(Modifier.size(6.dp))
        TFoot(caption)
    }
}

@Composable
fun KeyCode(text: String, color: Color = Pn.InkDim) {
    BasicText(
        text,
        style = TextStyle(
            fontFamily = MartianMono, fontSize = 14.5.sp, letterSpacing = 0.1.em, color = color,
        ),
    )
}

/* ============ faceplate grid ============ */

@Composable
fun Faceplate(modifier: Modifier = Modifier, borderColor: Color = Pn.Line, content: @Composable ColumnScope.() -> Unit) {
    Column(modifier.fillMaxWidth().border(1.dp, borderColor), content = content)
}

@Composable
fun Tile(modifier: Modifier = Modifier, content: @Composable ColumnScope.() -> Unit) {
    Column(modifier.fillMaxWidth().padding(start = 14.dp, top = 14.dp, end = 14.dp, bottom = 12.dp), content = content)
}

@Composable
fun HDivider(color: Color = Pn.Line) {
    Box(Modifier.fillMaxWidth().height(1.dp).background(color))
}

/* ============ shared motion: the 1.4s steps(1) blink ============ */

@Composable
fun blinkAlpha(): Float {
    // reduced motion (§7): blinks go solid — the marker stays, the flicker goes
    if (LocalReducedMotion.current) return 1f
    val t = rememberInfiniteTransition(label = "blink")
    val phase by t.animateFloat(
        initialValue = 0f, targetValue = 1f,
        animationSpec = infiniteRepeatable(tween(1400, easing = LinearEasing)),
        label = "blinkPhase",
    )
    return if (phase < 0.5f) 1f else 0.25f
}

/* ============ caution hatching (panic strip) ============ */

fun Modifier.hatched(lineColor: Color): Modifier = drawBehind {
    val step = 20f * density / 2f
    var x = -size.height
    while (x < size.width) {
        drawLine(
            color = lineColor,
            start = Offset(x, size.height),
            end = Offset(x + size.height, 0f),
            strokeWidth = step / 2f,
        )
        x += step * 2f
    }
}
