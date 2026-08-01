package com.ciba.api.controller;

import com.ciba.api.service.CibaClientService;
import com.ciba.api.service.CibaClientService.*;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * CIBA Client Controller.
 *
 * Exposes the CIBA initiation and status endpoints.
 * This is the "client" side of the CIBA flow — it talks to Keycloak
 * on behalf of the AI agent.
 */
@RestController
@RequestMapping("/ciba")
@RequiredArgsConstructor
@Slf4j
public class CibaClientController {

    private final CibaClientService cibaClientService;

    // In-memory status (in production, use Redis)
    private final ConcurrentHashMap<String, AuthRequestStatus> requestStatuses = new ConcurrentHashMap<>();

    // ── POST /ciba/auth-request ────────────────────────────────────────────────
    // Initiates a CIBA authentication request.
    //
    // Request body:
    // {
    //   "login_hint": "user@example.com",
    //   "binding_message": "Access your calendar",
    //   "scope": "openid profile calendar.read email"
    // }
    //
    // Response (202 Accepted — poll for result):
    // {
    //   "auth_req_id": "AR-xxx",
    //   "mode": "poll",
    //   "interval_seconds": 5,
    //   "timeout_seconds": 300,
    //   "status_url": "/ciba/status/AR-xxx"
    // }

    @PostMapping("/auth-request")
    public ResponseEntity<?> initiateAuthRequest(@RequestBody AuthRequestDto dto) {
        if (dto.loginHint() == null || dto.loginHint().isBlank()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "login_hint is required"));
        }
        if (dto.scope() == null || dto.scope().isBlank()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "scope is required"));
        }

        String bindingMsg = dto.bindingMessage() != null
                ? dto.bindingMessage()
                : "Confirm access to your data";

        try {
            CibaAuthResponse authResp = cibaClientService.initiateAuthRequest(
                    dto.loginHint(), bindingMsg, dto.scope());

            // Store status
            requestStatuses.put(authResp.authReqId(), new AuthRequestStatus(
                    authResp.authReqId(), "pending", null, null, null));

            log.info("CIBA auth request created: {}", authResp.authReqId());

            return ResponseEntity.accepted().body(Map.of(
                    "auth_req_id", authResp.authReqId(),
                    "mode", authResp.mode(),
                    "interval_seconds", authResp.intervalSeconds(),
                    "timeout_seconds", authResp.timeoutSeconds(),
                    "status_url", authResp.statusUrl()
            ));
        } catch (CibaException e) {
            log.error("CIBA initiation failed: {}", e.getMessage());
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .body(Map.of("error", e.getMessage()));
        }
    }

    // ── GET /ciba/status/{authReqId} ──────────────────────────────────────────
    // Returns the current status of a CIBA auth request.

    @GetMapping("/status/{authReqId}")
    public ResponseEntity<?> getStatus(@PathVariable String authReqId) {
        AuthRequestStatus status = requestStatuses.get(authReqId);
        if (status == null) {
            return ResponseEntity.notFound().build();
        }
        return ResponseEntity.ok(Map.of(
                "auth_req_id", status.authReqId(),
                "status", status.status(),
                "access_token", status.accessToken() != null ? "[present]" : null,
                "id_token", status.idToken() != null ? "[present]" : null,
                "error", status.error() != null ? status.error() : null
        ));
    }

    // ── POST /ciba/poll/{authReqId} ─────────────────────────────────────────────
    // Manually triggers a poll for the given auth_req_id.
    // Useful for testing or non-async integration.

    @PostMapping("/poll/{authReqId}")
    public ResponseEntity<?> pollStatus(@PathVariable String authReqId) {
        try {
            CibaTokenResponse tokenResp = cibaClientService.pollForTokenSync(authReqId);
            if (tokenResp != null) {
                // Update status
                requestStatuses.put(authReqId, new AuthRequestStatus(
                        authReqId, "approved", tokenResp.accessToken(),
                        tokenResp.idToken(), null));
                return ResponseEntity.ok(Map.of(
                        "status", "approved",
                        "access_token", tokenResp.accessToken(),
                        "id_token", tokenResp.idToken(),
                        "expires_in", tokenResp.expiresIn(),
                        "scope", tokenResp.scope()
                ));
            } else {
                return ResponseEntity.ok(Map.of(
                        "status", "pending",
                        "auth_req_id", authReqId
                ));
            }
        } catch (CibaAuthPendingException e) {
            return ResponseEntity.ok(Map.of(
                    "status", "pending",
                    "auth_req_id", authReqId,
                    "error", "authorization_pending"
            ));
        } catch (CibaAccessDeniedException e) {
            requestStatuses.put(authReqId, new AuthRequestStatus(
                    authReqId, "denied", null, null, e.getMessage()));
            return ResponseEntity.ok(Map.of(
                    "status", "denied",
                    "error", e.getMessage()
            ));
        } catch (CibaException e) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(Map.of("error", e.getMessage()));
        }
    }

    // ── POST /ciba/ping-callback ───────────────────────────────────────────────
    // Called by Keycloak when in PING mode after user approves.
    // Keycloak POSTs to this endpoint with the token.

    @PostMapping("/ping-callback")
    public ResponseEntity<?> pingCallback(@RequestBody CibaTokenResponse tokenResp) {
        if (tokenResp == null || tokenResp.accessToken() == null) {
            return ResponseEntity.badRequest().body(Map.of("error", "Invalid callback"));
        }
        log.info("CIBA ping callback received: access_token present, expires_in={}",
                tokenResp.expiresIn());
        // In a real implementation, notify waiting clients via WebSocket/SSE
        return ResponseEntity.ok(Map.of("status", "received"));
    }

    // ── DTOs ────────────────────────────────────────────────────────────────────

    public record AuthRequestDto(
            String loginHint,
            String bindingMessage,
            String scope
    ) {}

    private record AuthRequestStatus(
            String authReqId,
            String status,       // pending | approved | denied | expired
            String accessToken,
            String idToken,
            String error
    ) {}
}
