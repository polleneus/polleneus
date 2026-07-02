package com.polleneus.client.ui.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import com.polleneus.client.Prefs
import com.polleneus.client.mesh.MeshController
import com.polleneus.client.service.MeshService
import com.polleneus.client.system.Battery
import com.polleneus.client.ui.components.BackChevron
import com.polleneus.client.ui.components.Chevron
import com.polleneus.client.ui.components.Faceplate
import com.polleneus.client.ui.components.HDivider
import com.polleneus.client.ui.components.TFoot
import com.polleneus.client.ui.components.TLabel
import com.polleneus.client.ui.messages.TTL_CHOICES
import com.polleneus.client.ui.theme.MartianMono
import com.polleneus.client.ui.theme.Pn

/**
 * Short by design (design system §5). The absences are decisions, not omissions: no themes,
 * no chat wallpapers, no backup/export (would contradict local-only deletion), no
 * "invisible mode" (would be a lie). Every row changes something real about safety or battery.
 */
@Composable
fun SettingsScreen(
    controller: MeshController,
    onBack: () -> Unit,
    onOpenHonesty: () -> Unit,
    onStartOver: () -> Unit,
) {
    val ctx = LocalContext.current
    val key by controller.deviceKey.collectAsState()

    var batteryGranted by remember { mutableStateOf(Battery.unrestricted(ctx)) }
    var discreet by remember { mutableStateOf(Prefs.discreet(ctx)) }
    var ttlIndex by remember { mutableIntStateOf(Prefs.defaultTtlIndex(ctx)) }

    // coming back from system settings: re-read the real grant state
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val obs = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) batteryGranted = Battery.unrestricted(ctx)
        }
        lifecycleOwner.lifecycle.addObserver(obs)
        onDispose { lifecycleOwner.lifecycle.removeObserver(obs) }
    }

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
                "SETTINGS",
                style = TextStyle(
                    fontFamily = MartianMono, fontSize = 13.sp, fontWeight = FontWeight.W700,
                    letterSpacing = 0.14.em, color = Pn.Ink,
                ),
            )
        }

        TLabel("Mesh", Modifier.padding(start = 2.dp, bottom = 8.dp))
        Faceplate {
            SettingRow(
                name = "Battery access",
                sub = if (batteryGranted) "unrestricted — the mesh can work pocketed"
                else "restricted — android may drop this phone out of the mesh",
                onClick = if (batteryGranted) null else ({ Battery.requestGrant(ctx) }),
            ) {
                if (batteryGranted) SettingValue("✓ granted", Pn.Data)
                else SettingValue("tap to allow", Pn.Accent)
            }
        }

        TLabel("Lock screen", Modifier.padding(top = 14.dp, start = 2.dp, bottom = 8.dp))
        Faceplate {
            SettingRow(
                name = "Discreet notification",
                sub = "locked phone shows only \"active\" — no counts, no message hints",
                onClick = {
                    discreet = !discreet
                    Prefs.setDiscreet(ctx, discreet)
                    MeshService.refresh(ctx)
                },
            ) {
                InstrumentSwitch(on = discreet)
            }
        }

        TLabel("Messages", Modifier.padding(top = 14.dp, start = 2.dp, bottom = 8.dp))
        Faceplate {
            SettingRow(
                name = "Default lifetime",
                sub = "senders can change it per message",
                onClick = {
                    ttlIndex = (ttlIndex + 1) % TTL_CHOICES.size
                    Prefs.setDefaultTtlIndex(ctx, ttlIndex)
                },
            ) {
                SettingValue(TTL_CHOICES[ttlIndex].label, Pn.InkDim)
                Spacer(Modifier.width(8.dp))
                Chevron()
            }
        }

        TLabel("Honesty", Modifier.padding(top = 14.dp, start = 2.dp, bottom = 8.dp))
        Faceplate {
            SettingRow(
                name = "What this protects",
                sub = "and what it doesn't — read it again any time",
                onClick = onOpenHonesty,
            ) {
                Chevron()
            }
        }

        TLabel("Identity", Modifier.padding(top = 14.dp, start = 2.dp, bottom = 8.dp))
        Faceplate {
            SettingRow(
                name = "Device key",
                sub = "never leaves this phone",
                onClick = null,
            ) {
                SettingValue(if (key.isEmpty()) "—" else key, Pn.InkDim)
            }
            HDivider()
            SettingRow(
                name = "Start over",
                sub = "erase everything — opens the panic ceremony",
                nameColor = Pn.DangerText,
                onClick = onStartOver,
            ) {
                Chevron()
            }
        }

        Spacer(Modifier.weight(1f))
        Spacer(Modifier.height(16.dp))
        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
            TFoot("v0.1 · no servers — nothing here phones home")
        }
        Spacer(Modifier.height(14.dp))
    }
}

@Composable
private fun SettingRow(
    name: String,
    sub: String,
    nameColor: Color = Pn.Ink,
    onClick: (() -> Unit)?,
    trailing: @Composable () -> Unit,
) {
    Row(
        Modifier.fillMaxWidth()
            .let { if (onClick != null) it.clickable(onClick = onClick) else it }
            .padding(14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            BasicText(
                name.uppercase(),
                style = TextStyle(
                    fontFamily = MartianMono, fontSize = 10.5.sp, fontWeight = FontWeight.W500,
                    letterSpacing = 0.1.em, color = nameColor,
                ),
            )
            Spacer(Modifier.height(4.dp))
            TFoot(sub)
        }
        Spacer(Modifier.width(12.dp))
        trailing()
    }
}

@Composable
private fun SettingValue(text: String, color: Color) {
    BasicText(
        text.uppercase(),
        style = TextStyle(
            fontFamily = MartianMono, fontSize = 9.sp, letterSpacing = 0.1.em, color = color,
        ),
    )
}

/** The faceplate toggle: bordered track, square knob. Teal = on (healthy), ghost = off. */
@Composable
fun InstrumentSwitch(on: Boolean) {
    Box(
        Modifier.size(width = 30.dp, height = 16.dp)
            .border(1.dp, if (on) Pn.Data else Pn.InkGhost),
    ) {
        Box(
            Modifier.align(if (on) Alignment.CenterEnd else Alignment.CenterStart)
                .padding(2.dp).size(width = 12.dp, height = 10.dp)
                .background(if (on) Pn.Data else Pn.InkGhost),
        )
    }
}
