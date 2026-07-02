package com.polleneus.client.ui.messages

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.text.BasicText
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.polleneus.client.ui.theme.MartianMono
import com.polleneus.client.ui.theme.Pn
import java.time.Duration
import java.time.Instant

/** "fades in 2d 3h" / "fades in 40 min" — compact, lowercase, honest about ephemerality. */
fun fadeLabel(now: Instant, fadesAt: Instant): String {
    val d = Duration.between(now, fadesAt)
    if (d.isNegative || d.isZero) return "faded"
    val days = d.toDays()
    val hours = d.toHours() % 24
    val mins = d.toMinutes() % 60
    return when {
        days > 0 -> "fades in ${days}d ${hours}h"
        hours > 0 -> "fades in ${hours}h ${mins}m"
        else -> "fades in $mins min"
    }
}

/** Fraction of lifetime remaining, for the burn-down bar. */
fun fadeFraction(receivedAt: Instant, fadesAt: Instant, now: Instant): Float {
    val total = Duration.between(receivedAt, fadesAt).toMillis().coerceAtLeast(1)
    val left = Duration.between(now, fadesAt).toMillis().coerceIn(0, total)
    return left.toFloat() / total.toFloat()
}

@Composable
fun TtlBar(fraction: Float, label: String, urgent: Boolean, modifier: Modifier = Modifier) {
    val color = if (urgent) Pn.Accent else Pn.InkFaint
    Row(modifier, verticalAlignment = Alignment.CenterVertically) {
        Box(
            Modifier.width(34.dp).height(4.dp).border(1.dp, Pn.LineStrong).padding(1.dp),
        ) {
            Box(Modifier.fillMaxWidth(fraction.coerceIn(0f, 1f)).height(2.dp).background(color))
        }
        Spacer(Modifier.width(8.dp))
        BasicText(
            label.uppercase(),
            style = TextStyle(
                fontFamily = MartianMono, fontSize = 8.5.sp, letterSpacing = 0.1.em, color = color,
            ),
        )
    }
}

