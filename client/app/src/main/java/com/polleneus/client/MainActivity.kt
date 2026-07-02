package com.polleneus.client

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.remember
import androidx.lifecycle.lifecycleScope
import com.polleneus.client.mesh.RealMeshController
import com.polleneus.client.ui.AppShell
import com.polleneus.client.ui.theme.PolleneusTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            PolleneusTheme {
                // X2b-2: the promised one-line change — the real controller replaces the mock.
                // Real identity, real trust store, real pairing; messaging still honestly X3.
                val controller = remember { RealMeshController(applicationContext, lifecycleScope).also { it.start() } }
                AppShell(controller)
            }
        }
    }
}
