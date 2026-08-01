package com.ciba.client.controller;

import com.ciba.client.service.CibaClientService;
import com.fasterxml.jackson.databind.JsonNode;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

/**
 * Receives ping callbacks from Keycloak when in ping mode.
 * Keycloak POSTs here when the user approves the CIBA request.
 */
@RestController
@RequestMapping("/ciba")
@RequiredArgsConstructor
@Slf4j
public class PingCallbackController {

    private final CibaClientService cibaClientService;

    @PostMapping("/ping-callback")
    public ResponseEntity<?> pingCallback(@RequestBody JsonNode payload) {
        log.info("Ping callback received from Keycloak: {}", payload);

        try {
            var result = cibaClientService.handlePingCallback(payload);
            return ResponseEntity.ok(Map.of(
                "status", "TOKEN_RECEIVED",
                "authReqId", result.authReqId(),
                "message", "Ping callback processed successfully"
            ));
        } catch (Exception e) {
            log.error("Ping callback failed", e);
            return ResponseEntity.internalServerError()
                .body(Map.of("error", e.getMessage()));
        }
    }
}
