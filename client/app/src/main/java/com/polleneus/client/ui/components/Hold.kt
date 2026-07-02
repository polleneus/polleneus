package com.polleneus.client.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.BasicText
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.polleneus.client.ui.theme.MartianMono
import com.polleneus.client.ui.theme.Pn

/**
 * Destructive = hold (design system §4/§7): nothing destructive happens on a tap, anywhere.
 * The track fills linearly over 2s; releasing early drains it back at 2x. Completion = commit.
 */
@Composable
fun HoldToConfirm(
    text: String,
    sub: String,
    modifier: Modifier = Modifier,
    onComplete: () -> Unit,
) {
    var pressing by remember { mutableStateOf(false) }
    var progress by remember { mutableFloatStateOf(0f) }
    var fired by remember { mutableStateOf(false) }
    val complete by rememberUpdatedState(onComplete)

    LaunchedEffect(pressing) {
        var last = withFrameNanos { it }
        while (true) {
            if (pressing) {
                if (progress >= 1f) break
            } else {
                if (progress <= 0f) break
            }
            val now = withFrameNanos { it }
            val dt = (now - last) / 1_000_000_000f
            last = now
            progress = if (pressing) {
                (progress + dt / 2f).coerceAtMost(1f)      // fill: 2000ms linear
            } else {
                (progress - dt).coerceAtLeast(0f)          // drain-back: 2x speed
            }
            if (progress >= 1f && pressing && !fired) {
                fired = true
                complete()
            }
        }
    }

    Column(
        modifier
            .fillMaxWidth()
            .border(1.dp, Pn.Danger.copy(alpha = 0.6f))
            .hatched(Pn.DangerDim)
            .pointerInput(Unit) {
                detectTapGestures(onPress = {
                    if (!fired) {
                        pressing = true
                        tryAwaitRelease()
                        pressing = false
                    }
                })
            }
            .padding(horizontal = 16.dp, vertical = 18.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        BasicText(
            text.uppercase(),
            style = TextStyle(
                fontFamily = MartianMono, fontSize = 12.sp, fontWeight = FontWeight.W700,
                letterSpacing = 0.15.em, color = Pn.DangerText,
            ),
        )
        Spacer(Modifier.height(6.dp))
        BasicText(
            sub.uppercase(),
            style = TextStyle(
                fontFamily = MartianMono, fontSize = 8.sp, letterSpacing = 0.12.em,
                color = Pn.InkFaint,
            ),
        )
        Spacer(Modifier.height(12.dp))
        Box(Modifier.fillMaxWidth().height(3.dp).background(Pn.Danger.copy(alpha = 0.2f))) {
            Box(Modifier.fillMaxWidth(progress).height(3.dp).background(Pn.Danger))
        }
    }
}
