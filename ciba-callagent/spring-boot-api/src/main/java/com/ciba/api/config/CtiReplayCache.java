package com.ciba.api.config;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Replay-attack prevention for CIBA tokens.
 *
 * CIBA tokens contain a `cti` (CIBA Token Identifier) claim — a unique,
 * opaque identifier assigned by the IdP per authentication request.
 * The spec REQUIRES resource servers to track used cti values and reject
 * any token that reuses a cti (indicating a replay attack).
 *
 * This implementation uses Caffeine with a 24-hour TTL for used cti values.
 * In production, use Redis with a TTL matching token expiry.
 */
@Component
public class CtiReplayCache {

    // Map: cti value → first-seen timestamp
    private final Cache<String, Long> usedCtis;

    public CtiReplayCache() {
        this.usedCtis = Caffeine.newBuilder()
                .expireAfterWrite(Duration.ofHours(24))
                .maximumSize(100_000)
                .build();
    }

    /**
     * Returns true if this cti has NOT been seen before (token is fresh).
     * Returns false if this cti was already used (possible replay attack).
     */
    public boolean checkAndMark(String cti) {
        if (cti == null || cti.isBlank()) {
            // CIBA tokens MUST have a cti — missing cti means invalid
            return false;
        }
        return usedCtis.asMap().putIfAbsent(cti, System.currentTimeMillis()) == null;
    }

    /**
     * Number of stored cti entries (for monitoring).
     */
    public long size() {
        return usedCtis.estimatedSize();
    }

    /**
     * Clear all entries (useful for tests).
     */
    public void clear() {
        usedCtis.invalidateAll();
    }
}
