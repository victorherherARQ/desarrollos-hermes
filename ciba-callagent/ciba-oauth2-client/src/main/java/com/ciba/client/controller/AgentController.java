package com.ciba.client.controller;

import com.ciba.client.dto.CibaClientDtos.*;
import com.ciba.client.service.AgentOrchestrator;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.Map;

@RestController
@RequestMapping("/agent")
@RequiredArgsConstructor
@Slf4j
public class AgentController {

    private final AgentOrchestrator agentOrchestrator;

    /**
     * POST /agent/request
     * 
     * Called by the AI agent (Hermes) to request authorization to act on
     * behalf of a user. Spring Boot sends a CIBA request to Keycloak, returns
     * a requestId for tracking.
     *
     * The AI agent then polls /agent/status/{requestId} until the user approves
     * on their phone, then calls /agent/execute/{requestId} to get the data.
     */
    @PostMapping("/request")
    public ResponseEntity<?> request(@Valid @RequestBody AgentRequest req) {
        log.info("/agent/request: userId={}, action={}", req.getUserId(), req.getAction());

        try {
            var resp = agentOrchestrator.initiate(req.getUserId(), req.getAction(), req.getParams());
            return ResponseEntity.status(HttpStatus.ACCEPTED).body(resp);
        } catch (IllegalArgumentException e) {
            return ResponseEntity.badRequest()
                .body(new ErrorResponse("INVALID_REQUEST", e.getMessage(), Instant.now()));
        } catch (Exception e) {
            log.error("/agent/request failed", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new ErrorResponse("CIBA_INIT_FAILED", e.getMessage(), Instant.now()));
        }
    }

    /**
     * GET /agent/status/{requestId}
     * 
     * Poll CIBA request status. If approved, the response includes the access_token.
     * The AI agent should poll every 3 seconds until status != PENDING.
     */
    @GetMapping("/status/{requestId}")
    public ResponseEntity<?> status(@PathVariable String requestId) {
        try {
            var resp = agentOrchestrator.checkStatus(requestId);
            return ResponseEntity.ok(resp);
        } catch (IllegalArgumentException e) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("error", "NOT_FOUND", "detail", e.getMessage()));
        }
    }

    /**
     * POST /agent/execute/{requestId}
     * 
     * Execute the requested action with the CIBA token.
     * The token was obtained when the user approved the CIBA request.
     * This endpoint calls the Resource Server with the CIBA token and returns
     * the user's data.
     */
    @PostMapping("/execute/{requestId}")
    public ResponseEntity<?> execute(@PathVariable String requestId) {
        try {
            var resp = agentOrchestrator.execute(requestId);
            if (resp.isSuccess()) {
                return ResponseEntity.ok(resp);
            } else {
                return ResponseEntity.status(HttpStatus.UNPROCESSABLE_ENTITY).body(resp);
            }
        } catch (Exception e) {
            log.error("/agent/execute failed", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new ErrorResponse("EXECUTE_FAILED", e.getMessage(), Instant.now()));
        }
    }

    /**
     * GET /agent/health — health check for the AI agent
     */
    @GetMapping("/health")
    public ResponseEntity<?> health() {
        return ResponseEntity.ok(Map.of(
            "service", "ciba-oauth2-client",
            "status", "UP",
            "timestamp", Instant.now()
        ));
    }
}
