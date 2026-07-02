package com.polleneus.client.ui.theme

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier

/**
 * Dark-only by design: the app targets blackout/night field use; there is no light theme
 * (design system: "themes" is a deliberate settings absence).
 */
private val PnColorScheme = darkColorScheme(
    primary = Pn.Data,
    secondary = Pn.Accent,
    error = Pn.Danger,
    background = Pn.Bg,
    surface = Pn.Bg,
    onPrimary = Pn.Bg,
    onSecondary = Pn.Bg,
    onBackground = Pn.Ink,
    onSurface = Pn.Ink,
)

@Composable
fun PolleneusTheme(content: @Composable () -> Unit) {
    val reduced by com.polleneus.client.ui.components.rememberReducedMotion()
    MaterialTheme(colorScheme = PnColorScheme) {
        androidx.compose.runtime.CompositionLocalProvider(
            com.polleneus.client.ui.components.LocalReducedMotion provides reduced,
        ) {
            androidx.compose.foundation.layout.Box(
                Modifier.fillMaxSize().background(Pn.Bg)
            ) { content() }
        }
    }
}
