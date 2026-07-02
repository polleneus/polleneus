package com.polleneus.client

import android.app.Application
import com.polleneus.client.mesh.RealMeshController
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

/**
 * X4: the controller moves to application scope (kickoff spec D2 — one app, in-process
 * foreground service). The activity renders it; MeshService keeps it alive and mirrors it
 * into the persistent notification. Neither owns it.
 */
class PolleneusApp : Application() {

    val appScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    val controller: RealMeshController by lazy { RealMeshController(this, appScope) }
}
