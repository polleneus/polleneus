package com.polleneus.client

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.remember
import androidx.lifecycle.lifecycleScope
import com.polleneus.client.mesh.MockMeshController
import com.polleneus.client.ui.AppShell
import com.polleneus.client.ui.theme.PolleneusTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            PolleneusTheme {
                // X1: the mock IS the mesh. The real MeshController port begins in X2;
                // this call site is the only line that changes.
                val controller = remember { MockMeshController(lifecycleScope).also { it.start() } }
                AppShell(controller)
            }
        }
    }
}
