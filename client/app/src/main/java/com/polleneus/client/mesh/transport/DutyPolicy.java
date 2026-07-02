package com.polleneus.client.mesh.transport;

/**
 * Pure decision logic for the scan duty cycler (Research Stop #5) — no Android imports so the
 * budget math is JVM-testable (spike/dutytest/DutySelfTest.java).
 *
 * Budget model (verified fact F4, research-stop-5 memo): the OS scan-start quota records a session
 * at scan STOP and refuses the next registration when the 5 most recent recorded sessions all began
 * within the last 30s — and the refusal is SILENT to the app. We track our completed-session stop
 * times and stay at <= maxCompleted (4) completed cycles per rolling window, approximating
 * "session started within the window" by "session stopped within the window", which is strictly
 * more conservative for sessions shorter than the window (all of ours: windows are 10s).
 */
final class DutyPolicy {
    private DutyPolicy() {}

    /** Continuous scanning whenever the user can see the screen or a pairing ceremony needs fresh tokens. */
    static boolean continuous(boolean pairMode, boolean screenOn) {
        return pairMode || screenOn;
    }

    /** Completed stop/start cycles whose STOP falls inside the rolling budget window. Zero entries = unused slots. */
    static int completedInWindow(long[] stopTimes, long now, long windowMs) {
        int n = 0;
        for (long t : stopTimes) {
            if (t > 0 && now - t < windowMs) n++;
        }
        return n;
    }

    /**
     * May we start a scan now? Normal duty operations keep one slot in reserve for self-heal
     * (allowed while completed < max-1); a self-heal start may consume the reserve (completed < max).
     */
    static boolean startAllowed(long[] stopTimes, long now, long windowMs, int maxCompleted, boolean selfHeal) {
        int completed = completedInWindow(stopTimes, now, windowMs);
        return completed < (selfHeal ? maxCompleted : maxCompleted - 1);
    }
}
