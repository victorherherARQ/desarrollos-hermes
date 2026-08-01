package com.ciba.resource.controller;

import com.ciba.resource.config.CtiReplayCache;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.Map;

@RestController
@RequiredArgsConstructor
public class HealthController {

    private final CtiReplayCache ctiReplayCache;

    @GetMapping("/health")
    public ResponseEntity<?> health() {
        return ResponseEntity.ok(Map.of(
            "service", "ciba-resource-server",
            "status", "UP",
            "port", 8082,
            "ctiCacheSize", ctiReplayCache.size(),
            "timestamp", Instant.now()
        ));
    }

    @DeleteMapping("/admin/cti-cache")
    public ResponseEntity<?> clearCtiCache() {
        ctiReplayCache.clear();
        return ResponseEntity.ok(Map.of(
            "message", "CTI cache cleared",
            "timestamp", Instant.now()
        ));
    }
}
