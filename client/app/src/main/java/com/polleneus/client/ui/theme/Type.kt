@file:OptIn(androidx.compose.ui.text.ExperimentalTextApi::class)

package com.polleneus.client.ui.theme

import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import com.polleneus.client.R

/**
 * Variable TTFs bundled from google/fonts (OFL): res/font/martian_mono.ttf, res/font/archivo.ttf.
 * Weights are instantiated via font-variation settings (API 26+, our minSdk floor).
 */
private fun vfont(res: Int, weight: FontWeight) = Font(
    resId = res,
    weight = weight,
    variationSettings = FontVariation.Settings(FontVariation.weight(weight.weight)),
)

val MartianMono = FontFamily(
    vfont(R.font.martian_mono, FontWeight.W300),
    vfont(R.font.martian_mono, FontWeight.W400),
    vfont(R.font.martian_mono, FontWeight.W500),
    vfont(R.font.martian_mono, FontWeight.W700),
)

val Archivo = FontFamily(
    vfont(R.font.archivo, FontWeight.W400),
    vfont(R.font.archivo, FontWeight.W500),
    vfont(R.font.archivo, FontWeight.W600),
    vfont(R.font.archivo, FontWeight.W700),
)
