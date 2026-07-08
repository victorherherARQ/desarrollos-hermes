package com.poc.api.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * Endpoint público de health del Apigee-stub.
 * NO requiere token (configurado en {@link com.poc.api.config.SecurityConfig}).
 */
@RestController
public class HealthController {

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of(
                "status", "UP",
                "service", "apigee-stub"
        );
    }
}
