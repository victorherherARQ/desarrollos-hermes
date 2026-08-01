package com.ciba.resource.config;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.util.concurrent.ConcurrentHashMap;

/**
 * CTI = CIBA Token Identifier.
 * 
 * Every CIBA-issued access_token contains a unique "cti" claim.
 * This cache stores used CTI values. If a token with a previously-used CTI
 * is presented, it is a REPLAY ATTACK and must be rejected.
 * 
 * Key = cti claim value
 * Value = timestamp of first use
 */
@Component
@Slf4j
public class CtiReplayCache {

    private final Cache<String, Long> cache;

    public CtiReplayCache(
            @Value("${cti.cache.max-size:10000}") int maxSize,
            @Value("${cti.cache.expire-after-hours:24}") int expireHours) {
        this.cache = Caffeine.newBuilder()
            .maximumSize(maxSize)
            .expireAfterWrite(Duration.ofHours(expireHours))
            .removalListener((key, value, cause) ->
                log.debug("CTI evicted from cache: key={}, cause={}", key, cause))
            .build();
        log.info("CtiReplayCache initialized: maxSize={}, expireAfterWrite={}h", maxSize, expireHours);
    }

    /**
     * Check if this CTI has been used before. If NOT, mark it as used.
     * 
     * @return true = NEW token (allowed), false = REPLAY (blocked)
     */
    public synchronized boolean checkAndMark(String cti) {
        if (cti == null || cti.isBlank()) {
            log.warn("CTI validation called with null/blank value — rejecting");
            return false;
        }

        Long existing = cache.getIfPresent(cti);
        if (existing != null) {
            log.warn("CTI REPLAY ATTACK detected: cti={}, firstUsed={}", cti, existing);
            return false;
        }

        cache.put(cti, System.currentTimeMillis());
        log.debug("CTI recorded: cti={}", cti);
        return true;
    }

    /**
     * Check-only: is this CTI already in the cache?
     */
    public boolean isKnown(String cti) {
        return cti != null && cache.getIfPresent(cti) != null;
    }

    public int size() {
        return (int) cache.estimatedSize();
    }

    public void clear() {
        cache.invalidateAll();
        log.info("CTI cache cleared");
    }
}
