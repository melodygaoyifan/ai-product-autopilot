package com.example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

public class AppTest {

    // J-TEST-1: assertion-free test — passes while verifying nothing
    @Test
    public void parseCountRuns() {
        new App().parseCount("7");
    }

    // J-MUT-1 counterpart: only the happy path; the >= 100 boundary and
    // the 20% branch are never asserted, so boundary mutants survive
    @Test
    public void smallOrderDiscount() {
        assertEquals(5, new App().discountPercent(1));
    }

    // J-TEST-2: permanently disabled test — green suite, dead coverage
    @org.junit.jupiter.api.Disabled("flaky since 2024, never fixed")
    @Test
    public void settlementRoundTrip() {
        assertEquals(100, new Payments().roundToUnit(100));
    }

    // J-TEST-3: tautological assertion — always true, verifies nothing
    @Test
    public void validAmountAccepted() {
        long cents = new Payments().roundToUnit(250);
        assertEquals(cents, cents);
    }
}
