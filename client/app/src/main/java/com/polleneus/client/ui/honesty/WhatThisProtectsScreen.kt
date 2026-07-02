package com.polleneus.client.ui.honesty

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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.polleneus.client.ui.components.BackChevron
import com.polleneus.client.ui.components.Faceplate
import com.polleneus.client.ui.components.HDivider
import com.polleneus.client.ui.components.TFoot
import com.polleneus.client.ui.components.TLabel
import com.polleneus.client.ui.onboarding.DealRow
import com.polleneus.client.ui.onboarding.NorthStar
import com.polleneus.client.ui.theme.MartianMono
import com.polleneus.client.ui.theme.Pn

/**
 * The canonical B3 wording (design system §5): 3 protected / 4 not-protected rows plus the
 * north star. This screen IS the honest-copy source of truth — onboarding and any future
 * store text must quote it, not paraphrase it. One tap from settings, never buried.
 */
@Composable
fun WhatThisProtectsScreen(onBack: () -> Unit) {
    Column(
        Modifier.fillMaxSize().padding(horizontal = 16.dp).verticalScroll(rememberScrollState()),
    ) {
        Row(
            Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            BackChevron(onClick = onBack)
            Spacer(Modifier.width(12.dp))
            BasicText(
                "WHAT THIS PROTECTS",
                style = TextStyle(
                    fontFamily = MartianMono, fontSize = 13.sp, fontWeight = FontWeight.W700,
                    letterSpacing = 0.14.em, color = Pn.Ink,
                ),
            )
        }

        NorthStar()

        TLabel("Protected", Modifier.padding(top = 14.dp, bottom = 8.dp, start = 2.dp), color = Pn.Data)
        Faceplate {
            DealRow(true, "What a message says",
                "Sealed end-to-end. Carriers, relays, and observers can't read it.")
            HDivider()
            DealRow(true, "Who a message is for",
                "Everyone nearby gets a copy — holding one proves nothing about you.")
            HDivider()
            DealRow(true, "Who a message is from — for others",
                "No sender name travels with it. Only a contact who verified you can prove it's you.")
        }

        TLabel(
            "Not protected — plan around these",
            Modifier.padding(top = 16.dp, bottom = 8.dp, start = 2.dp),
            color = Pn.Accent,
        )
        Faceplate {
            DealRow(false, "That this phone is on the mesh",
                "Radio is visible. Running the app is detectable. No setting changes this.")
            HDivider()
            DealRow(false, "A sending habit, over time",
                "A watched person who transmits often can eventually be identified. " +
                    "True for every mesh tool.")
            HDivider()
            DealRow(false, "Copies you didn't wipe",
                "Deletion is local. Other phones' copies fade only on their timers; " +
                    "screenshots never fade.")
            HDivider()
            DealRow(false, "Delivery",
                "Best-effort, phone to phone. It may be slow. It may never arrive. " +
                    "Nobody is told either way.")
        }

        Spacer(Modifier.weight(1f))
        Spacer(Modifier.height(16.dp))
        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
            TFoot("reachable any time: settings → what this protects")
        }
        Spacer(Modifier.height(14.dp))
    }
}
