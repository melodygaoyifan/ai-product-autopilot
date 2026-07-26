package com.example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class PaymentsTest {

    // J-TEST-2: only the happy path is asserted, so the J-MUT-2 rejection
    // branch (cents <= 0 -> false) and the upper bound both survive
    @Test
    public void acceptsAPositiveAmount() {
        assertTrue(new Payments().validateAmount(500));
    }

    // Exercises roundToUnit but ignores no return — the assertion here is
    // real; J-MUT-3 survives because PRODUCTION callers ignore the value,
    // not because this test does (documented in the manifest note)
    @Test
    public void roundsDownToUnit() {
        assertEquals(500, new Payments().roundToUnit(567));
    }
}
