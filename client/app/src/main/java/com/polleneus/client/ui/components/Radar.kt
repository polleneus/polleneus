package com.polleneus.client.ui.components

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.StartOffset
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.drawscope.Stroke
import com.polleneus.client.ui.theme.Pn

/**
 * The liveness motif. Motion spec: telemetry loops are slow + linear (3.2s, three rings
 * staggered by 1/3 period); they prove the machine is alive, never demand attention.
 * `sweeping=false` renders the paused/static instrument (single ghost ring, no motion).
 */
@Composable
fun Radar(nodes: Int, sweeping: Boolean, modifier: Modifier = Modifier) {
    val rings = if (sweeping) {
        val t = rememberInfiniteTransition(label = "radar")
        listOf(0, 1066, 2133).map { offset ->
            val p by t.animateFloat(
                initialValue = 0f, targetValue = 1f,
                animationSpec = infiniteRepeatable(
                    tween(3200, easing = LinearEasing),
                    initialStartOffset = StartOffset(offset),
                ),
                label = "ring$offset",
            )
            p
        }
    } else emptyList()

    // deterministic node placement (mirrors the design mockups)
    val nodeSpots = listOf(
        Offset(0.64f, 0.30f), Offset(0.22f, 0.34f), Offset(0.60f, 0.70f),
        Offset(0.36f, 0.62f), Offset(0.72f, 0.52f),
    )

    Canvas(modifier) {
        val r = size.minDimension / 2f
        val c = Offset(size.width / 2f, size.height / 2f)

        if (sweeping) {
            rings.forEach { p ->
                val scale = 0.12f + p * 0.88f
                drawCircle(
                    color = Pn.Data.copy(alpha = 0.6f * (1f - p)),
                    radius = r * scale,
                    center = c,
                    style = Stroke(width = 1.dp.toPx()),
                )
            }
        } else {
            drawCircle(
                color = Pn.LineStrong,
                radius = r * 0.64f,
                center = c,
                style = Stroke(width = 1.dp.toPx()),
            )
        }

        // core = this device
        drawCircle(
            color = if (sweeping) Pn.Data else Pn.InkGhost,
            radius = 3.5f.dp.toPx(),
            center = c,
        )

        // nearby devices — radio facts, one dot each
        nodeSpots.take(nodes.coerceAtMost(nodeSpots.size)).forEach { spot ->
            drawCircle(
                color = Pn.Ink,
                radius = 2.5f.dp.toPx(),
                center = Offset(spot.x * size.width, spot.y * size.height),
            )
        }
    }
}

private val Float.dp get() = androidx.compose.ui.unit.Dp(this)
private val Int.dp get() = androidx.compose.ui.unit.Dp(this.toFloat())
