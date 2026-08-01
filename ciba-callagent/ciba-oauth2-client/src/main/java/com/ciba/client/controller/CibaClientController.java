package com.ciba.client.controller;

import com.ciba.client.dto.CibaClientDtos.*;
import com.ciba.client.service.CibaClientService;
import com.ciba.client.service.CibaClientService.*;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.util.Map;

@RestController
@RequestMapping
@RequiredArgsConstructor
@Slf4j
public class CibaClientController {

    private final CibaClientService cibaClientService;

    // ── CIBA direct endpoints ─────────────────────────────────────────────

    /** POST /ciba/auth-request — direct CIBA initiation (for testing) */
    @PostMapping("/ciba/auth-request")
    public ResponseEntity<AuthReqResult> cibaAuthRequest(
            @RequestParam String userId,
            @RequestParam(defaultValue = "Read your calendar") String bindingMessage,
            @RequestParam(defaultValue = "openid profile email calendar.read") String scope) {

        try {
            var result = cibaClientService.initiateAuthRequest(userId, bindingMessage, scope);
            return ResponseEntity.ok(result);
        } catch (CibaException e) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Keycloak error: " + e.getMessage());
        }
    }

    /** POST /ciba/poll/{authReqId} — direct CIBA polling (for testing) */
    @PostMapping("/ciba/poll/{authReqId}")
    public ResponseEntity<?> cibaPoll(@PathVariable String authReqId) {
        try {
            var result = cibaClientService.pollToken(authReqId);
            return ResponseEntity.ok(result);
        } catch (AuthorizationPendingException e) {
            return ResponseEntity.status(HttpStatus.ACCEPTED)
                .body(Map.of("status", "PENDING", "message", "Waiting for user approval"));
        } catch (AccessDeniedException e) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN)
                .body(Map.of("status", "DENIED", "message", "User denied the request"));
        } catch (ExpiredTokenException e) {
            return ResponseEntity.status(HttpStatus.GONE)
                .body(Map.of("status", "EXPIRED", "message", "CIBA request expired"));
        } catch (CibaException e) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, e.getMessage());
        }
    }

    /** GET /ciba/client-info — keycloak OIDC discovery */
    @GetMapping("/ciba/client-info")
    public ResponseEntity<?> clientInfo() {
        return ResponseEntity.ok(Map.of(
            "clientId", "ciba-agent",
            "cibaMode", "poll",
            "description", "CIBA OAuth2 Client — initiates auth requests to Keycloak on behalf of AI agents"
        ));
    }
}
