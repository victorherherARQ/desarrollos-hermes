package com.ciba.api.controller;

import com.ciba.api.config.CtiReplayCache;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * Health check and system status endpoint.
 */
@RestController
public class HealthController {

    private final CtiReplayCache ctiReplayCache;

    public HealthController(CtiReplayCache ctiReplayCache) {
        this.ctiReplayCache = ctiReplayCache;
    }

    @GetMapping("/health")
    public ResponseEntity<?> health() {
        return ResponseEntity.ok(Map.of(
                "status", "UP",
                "service", "ciba-callagent",
                "version", "1.0.0",
                "cti_cache_entries", ctiReplayCache.size()
        ));
    }

    @GetMapping("/api/health")
    public ResponseEntity<?> apiHealth() {
        return ResponseEntity.ok(Map.of(
                "status", "UP",
                "protected_api", true,
                "_note", "CIBA Resource Server is operational"
        ));
    }
}
