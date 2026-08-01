package com.ciba.resource;

import com.ciba.resource.config.CtiReplayCache;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class CibaResourceServerTests {

    private CtiReplayCache ctiReplayCache;

    @BeforeEach
    void setUp() {
        ctiReplayCache = new CtiReplayCache(1000, 24);
    }

    @Test
    @DisplayName("First use of CTI returns true (allowed), second use returns false (replay)")
    void ctiReplayCache_blocksReplay() {
        String cti = "cti-abc123";

        assertTrue(ctiReplayCache.checkAndMark(cti), "First use should be allowed");
        assertFalse(ctiReplayCache.checkAndMark(cti), "Second use should be blocked (replay)");
    }

    @Test
    @DisplayName("Null or blank CTI is rejected")
    void ctiReplayCache_rejectsNull() {
        assertFalse(ctiReplayCache.checkAndMark(null));
        assertFalse(ctiReplayCache.checkAndMark(""));
        assertFalse(ctiReplayCache.checkAndMark("   "));
    }

    @Test
    @DisplayName("Different CTIs are all allowed")
    void ctiReplayCache_allowsDifferentTokens() {
        assertTrue(ctiReplayCache.checkAndMark("cti-1"));
        assertTrue(ctiReplayCache.checkAndMark("cti-2"));
        assertTrue(ctiReplayCache.checkAndMark("cti-3"));
        assertEquals(3, ctiReplayCache.size());
    }

    @Test
    @DisplayName("Clear resets the cache")
    void ctiReplayCache_clearWorks() {
        ctiReplayCache.checkAndMark("cti-x");
        assertEquals(1, ctiReplayCache.size());

        ctiReplayCache.clear();
        assertEquals(0, ctiReplayCache.size());
        assertTrue(ctiReplayCache.checkAndMark("cti-x"), "After clear, same CTI is allowed again");
    }
}
