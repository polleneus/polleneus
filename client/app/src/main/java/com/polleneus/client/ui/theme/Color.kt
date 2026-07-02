package com.polleneus.client.ui.theme

import androidx.compose.ui.graphics.Color

/**
 * Direction C "Field Instrument" — tokens v0.1, ported 1:1 from the design system (#51 §3).
 *
 * Semantic triad law (normative): [Accent] orange = needs-your-attention only;
 * [Data] teal = verified/healthy/live only; [Danger] red = destructive/reject ONLY.
 * Introducing a fourth semantic color requires amending the design-system spec.
 */
object Pn {
    val Bg = Color(0xFF0C0E10)
    val Panel = Color(0xFF121517)
    val Panel2 = Color(0xFF161B1D)
    val Line = Color(0xFF1F2426)
    val LineStrong = Color(0xFF2A3134)

    val Ink = Color(0xFFDCE3E3)
    val InkDim = Color(0xFF8FA0A2)
    val InkFaint = Color(0xFF5C696B)
    val InkGhost = Color(0xFF414D4F)

    val Accent = Color(0xFFFF7A3D)
    val Data = Color(0xFF7FB5B5)
    val Danger = Color(0xFFFF4D3D)
    val DangerText = Color(0xFFFF6B5A)

    val AccentDim = Color(0x24FF7A3D)   // .14 alpha
    val DataDim = Color(0x1F7FB5B5)     // .12 alpha
    val DangerDim = Color(0x1AFF4D3D)   // .10 alpha
}
