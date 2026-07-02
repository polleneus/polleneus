package com.polleneus.client.mesh.transport;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/**
 * The spike's DutySelfTest, ported as JUnit over the verbatim DutyPolicy port (V2).
 * The budget model is measured OS behavior (RS#5): the scan-start quota records sessions
 * at STOP and denies SILENTLY, so staying under it is the only safe play.
 */
public class DutyPolicyTest {

    private static final long W = 30_000;
    private static final int MAX = 4;

    @Test public void continuousWhenScreenOn() {
        assertTrue(DutyPolicy.continuous(false, true));
    }

    @Test public void continuousInPairModeEvenDark() {
        assertTrue(DutyPolicy.continuous(true, false));
    }

    @Test public void windowedWhenDarkAndNotPairing() {
        assertFalse(DutyPolicy.continuous(false, false));
    }

    @Test public void emptyRingCountsZero() {
        assertEquals(0, DutyPolicy.completedInWindow(new long[8], 1_000_000, W));
    }

    @Test public void countsOnlyInWindowBoundaryExclusive() {
        long now = 1_000_000;
        long[] ring = new long[8];
        ring[0] = now - 1_000; ring[1] = now - 10_000; ring[2] = now - 29_999;  // in-window
        ring[3] = now - 30_000; ring[4] = now - 60_000;                          // aged out (>= W)
        assertEquals(3, DutyPolicy.completedInWindow(ring, now, W));
    }

    @Test public void normalStartKeepsReserveSlot() {
        long now = 1_000_000;
        long[] three = { now - 1000, now - 2000, now - 3000, 0, 0, 0, 0, 0 };
        assertFalse(DutyPolicy.startAllowed(three, now, W, MAX, false));
        assertTrue(DutyPolicy.startAllowed(three, now, W, MAX, true));   // self-heal may spend it
    }

    @Test public void twoCompletedAllowsNormalStart() {
        long now = 1_000_000;
        long[] two = { now - 1000, now - 2000, 0, 0, 0, 0, 0, 0 };
        assertTrue(DutyPolicy.startAllowed(two, now, W, MAX, false));
    }

    @Test public void fourCompletedDeniesEvenSelfHeal() {
        long now = 1_000_000;
        long[] four = { now - 1000, now - 2000, now - 3000, now - 4000, 0, 0, 0, 0 };
        assertFalse(DutyPolicy.startAllowed(four, now, W, MAX, true));
    }

    @Test public void agedOutRingReopensBudget() {
        long now = 1_000_000;
        long[] aged = { now - 31_000, now - 32_000, now - 33_000, now - 34_000, 0, 0, 0, 0 };
        assertTrue(DutyPolicy.startAllowed(aged, now, W, MAX, false));
    }

    @Test public void wrappedRingOrderIrrelevant() {
        long now = 1_000_000;
        long[] wrapped = { now - 40_000, now - 1_000, now - 41_000, now - 2_000, now - 42_000, 0, 0, 0 };
        assertEquals(2, DutyPolicy.completedInWindow(wrapped, now, W));
    }
}
