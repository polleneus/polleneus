package com.polleneus.client.ui.panic

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.polleneus.client.mesh.MeshController
import com.polleneus.client.ui.components.BtnKind
import com.polleneus.client.ui.components.Faceplate
import com.polleneus.client.ui.components.HDivider
import com.polleneus.client.ui.components.HoldToConfirm
import com.polleneus.client.ui.components.PnButton
import com.polleneus.client.ui.components.TFoot
import com.polleneus.client.ui.components.TLabel
import com.polleneus.client.ui.theme.Archivo
import com.polleneus.client.ui.theme.MartianMono
import com.polleneus.client.ui.theme.Pn

/**
 * Step 2 of 2 of the panic ceremony (design system §5). Step 1 was a completed 2s hold on
 * the home strip / a notification action — an accidental pocket tap cannot get here, and
 * even here a tap does nothing: only a completed hold wipes.
 *
 * The will-erase vs cannot-do split is the honesty surface. The cannot-do copy carries the
 * M-FS3 verdict (kickoff Q8): keystore deletion is an OS-side revoke, not a proven flash
 * erase, so a well-equipped forensic lab may still recover traces from the storage chips.
 */
@Composable
fun PanicConfirmScreen(controller: MeshController, onCancel: () -> Unit, onWiped: () -> Unit) {
    Column(
        Modifier.fillMaxSize().padding(horizontal = 16.dp).verticalScroll(rememberScrollState()),
    ) {
        BasicText(
            "▲ PANIC WIPE",
            Modifier.fillMaxWidth().padding(top = 22.dp),
            style = TextStyle(
                fontFamily = MartianMono, fontSize = 23.sp, fontWeight = FontWeight.W700,
                letterSpacing = 0.06.em, color = Pn.DangerText,
                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
            ),
        )
        Spacer(Modifier.height(6.dp))
        Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
            TFoot("step 2 of 2 — nothing has been erased yet", color = Pn.InkFaint)
        }
        Spacer(Modifier.height(16.dp))

        Faceplate {
            Column(Modifier.padding(14.dp)) {
                TLabel("Will erase — now, from this phone", color = Pn.DangerText)
                Spacer(Modifier.height(8.dp))
                EraseLine("your key and identity")
                EraseLine("all contacts and verifications")
                EraseLine("all messages — yours and carried")
            }
            HDivider()
            Column(Modifier.padding(14.dp)) {
                TLabel("Cannot do — be honest with yourself")
                Spacer(Modifier.height(8.dp))
                TFoot(
                    "can't recall copies other phones already carry — those fade on their " +
                        "own timers · can't undo a forensic copy if this phone was already " +
                        "taken and imaged · can't promise a specialist lab recovers nothing " +
                        "from this phone's storage chips after the wipe",
                    color = Pn.InkFaint,
                )
            }
        }

        Spacer(Modifier.weight(1f))
        Spacer(Modifier.height(20.dp))
        HoldToConfirm(
            text = "Hold to wipe",
            sub = "keep pressing — 2 seconds",
            onComplete = {
                controller.panicWipe()
                onWiped()
            },
        )
        Spacer(Modifier.height(10.dp))
        PnButton("Cancel — nothing happens", BtnKind.PLAIN, Modifier.fillMaxWidth(), onClick = onCancel)
        Spacer(Modifier.height(26.dp))
    }
}

@Composable
private fun EraseLine(text: String) {
    BasicText(
        text.uppercase(),
        Modifier.padding(vertical = 4.dp),
        style = TextStyle(
            fontFamily = MartianMono, fontSize = 8.5.sp, letterSpacing = 0.08.em,
            color = Pn.InkDim,
        ),
    )
}

/**
 * After the wipe: honest-clean, factory-fresh, and nothing more. Anything beyond this look
 * (disguise modes, decoys) is a duress direction gated on security-track sign-off (Q4).
 */
@Composable
fun PostWipeScreen(onStartFresh: () -> Unit) {
    Column(
        Modifier.fillMaxSize().padding(horizontal = 16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Spacer(Modifier.weight(1f))
        CleanRing()
        Spacer(Modifier.height(24.dp))
        BasicText(
            "NOTHING STORED",
            style = TextStyle(
                fontFamily = MartianMono, fontSize = 21.sp, fontWeight = FontWeight.W700,
                letterSpacing = 0.03.em, color = Pn.InkDim,
            ),
        )
        Spacer(Modifier.height(16.dp))
        BasicText(
            "This app now looks and behaves like it was just installed. " +
                "No key, no contacts, no messages.",
            Modifier.padding(horizontal = 10.dp),
            style = TextStyle(
                fontFamily = Archivo, fontSize = 14.sp, color = Pn.InkDim, lineHeight = 22.sp,
                textAlign = androidx.compose.ui.text.style.TextAlign.Center,
            ),
        )
        Spacer(Modifier.height(14.dp))
        TFoot("copies other phones already carry will fade on their own timers")
        Spacer(Modifier.weight(1f))
        PnButton(
            "Start fresh — make a new key", BtnKind.OUTLINE_DATA, Modifier.fillMaxWidth(),
            onClick = onStartFresh,
        )
        Spacer(Modifier.height(26.dp))
    }
}

@Composable
private fun CleanRing() {
    androidx.compose.foundation.Canvas(Modifier.size(96.dp)) {
        val c = Offset(size.width / 2f, size.height / 2f)
        drawCircle(Pn.LineStrong, radius = size.minDimension / 2f - 1.dp.toPx(), center = c,
            style = Stroke(1.dp.toPx()))
        drawCircle(Pn.InkFaint, radius = size.minDimension * 0.16f, center = c,
            style = Stroke(1.6f * density))
    }
}
