package com.ciba.client.service;

import com.ciba.client.config.CibaProperties;
import com.ciba.client.dto.CibaClientDtos.*;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.time.Instant;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Orchestrates the full CIBA flow:
 *   1. Initiate auth request (calls Keycloak)
 *   2. Store pending state
 *   3. Poll status (called by AI agent)
 *   4. Execute action (calls Resource Server with CIBA token)
 *
 * State is kept in-memory. Production: replace with Redis.
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class AgentOrchestrator {

    private final CibaClientService cibaClientService;
    private final CibaProperties cibaProps;
    private final RestTemplate resourceServerRestTemplate;

    // In-memory request store. Replace with Redis for production.
    private final Map<String, RequestState> requests = new ConcurrentHashMap<>();

    // ── Public API ───────────────────────────────────────────────────────

    /**
     * Initiate CIBA flow. Called by Hermes via POST /agent/request.
     */
    public AgentRequestResponse initiate(String userId, String action, Map<String, Object> params) {
        validateAction(action);

        String requestId = UUID.randomUUID().toString().substring(0, 8);
        String scope = actionToScope(action);
        String bindingMessage = actionToBindingMessage(action);

        log.info("[{}] CIBA initiate: userId={}, action={}, scope={}", requestId, userId, action, scope);

        CibaClientService.AuthReqResult authResult;
        try {
            authResult = cibaClientService.initiateAuthRequest(userId, bindingMessage, scope);
        } catch (CibaClientService.CibaException e) {
            throw new IllegalStateException("Keycloak CIBA initiation failed: " + e.getMessage(), e);
        }

        requests.put(requestId, new RequestState(
            requestId,
            authResult.authReqId(),
            userId,
            action,
            scope,
            bindingMessage,
            (params != null) ? params : Map.of(),
            Instant.now(),
            Instant.now().plusSeconds(authResult.expiresIn()),
            AuthState.PENDING,
            null, null, authResult.expiresIn()
        ));

        return AgentRequestResponse.builder()
            .requestId(requestId)
            .authReqId(authResult.authReqId())
            .bindingMessage(bindingMessage)
            .mode(cibaProps.getMode())
            .statusUrl("/agent/status/" + requestId)
            .expiresIn(authResult.expiresIn())
            .createdAt(Instant.now())
            .build();
    }

    /**
     * Check CIBA request status. Polls Keycloak if still PENDING.
     */
    public StatusResponse checkStatus(String requestId) {
        RequestState state = requests.get(requestId);
        if (state == null) {
            throw new IllegalArgumentException("Request not found: " + requestId);
        }

        if (state.getState() == AuthState.DENIED) {
            return buildStatus(state, null);
        }

        if (state.getState() == AuthState.APPROVED) {
            return buildStatus(state, state.getAccessToken());
        }

        // Poll Keycloak
        try {
            CibaClientService.CibaTokenResult token = cibaClientService.pollToken(state.getAuthReqId());
            state.setState(AuthState.APPROVED);
            state.setAccessToken(token.accessToken());
            state.setIdToken(token.idToken());
            state.setExpiresIn(token.expiresIn());
            log.info("[{}] CIBA approved: sub extraction pending from id_token", requestId);
            return buildStatus(state, token.accessToken());

        } catch (CibaClientService.AuthorizationPendingException e) {
            return buildStatus(state, null);

        } catch (CibaClientService.AccessDeniedException e) {
            state.setState(AuthState.DENIED);
            return buildStatus(state, null);

        } catch (CibaClientService.ExpiredTokenException e) {
            state.setState(AuthState.EXPIRED);
            return buildStatus(state, null);

        } catch (CibaClientService.CibaException e) {
            state.setState(AuthState.ERROR);
            return StatusResponse.builder()
                .requestId(requestId)
                .status("ERROR")
                .userId(state.getUserId())
                .error(e.getMessage())
                .build();
        }
    }

    /**
     * Execute the action. Calls the Resource Server with the CIBA token.
     */
    public ExecuteResponse execute(String requestId) {
        RequestState state = requests.get(requestId);
        if (state == null) {
            throw new IllegalArgumentException("Request not found: " + requestId);
        }

        if (state.getState() != AuthState.APPROVED) {
            return ExecuteResponse.builder()
                .success(false)
                .requestId(requestId)
                .userId(state.getUserId())
                .action(state.getAction())
                .error("Request not approved. Current status: " + state.getState().name())
                .build();
        }

        if (state.getAccessToken() == null) {
            return ExecuteResponse.builder()
                .success(false)
                .requestId(requestId)
                .userId(state.getUserId())
                .action(state.getAction())
                .error("No access token available")
                .build();
        }

        log.info("[{}] Executing action={} with CIBA token for user={}", requestId, state.getAction(), state.getUserId());

        // Call Resource Server with the CIBA access_token
        Object data = callResourceServer(state);

        state.setState(AuthState.COMPLETED);

        return ExecuteResponse.builder()
            .success(true)
            .requestId(requestId)
            .userId(state.getUserId())
            .action(state.getAction())
            .data(data)
            .executedAt(Instant.now())
            .build();
    }

    // ── Private helpers ──────────────────────────────────────────────────

    private StatusResponse buildStatus(RequestState s, String accessToken) {
        return StatusResponse.builder()
            .requestId(s.getRequestId())
            .status(s.getState().name())
            .userId(s.getUserId())
            .bindingMessage(s.getBindingMessage())
            .accessToken(accessToken)
            .expiresIn(s.getExpiresIn() != null ? s.getExpiresIn() : 0)
            .build();
    }

    private Object callResourceServer(RequestState state) {
        String endpoint = switch (state.getAction()) {
            case "calendar_list", "calendar_create", "calendar_update" -> "/api/calendar/events";
            case "email_list", "email_send", "email_modify" -> "/api/email/inbox";
            case "profile" -> "/api/user/profile";
            case "token_info" -> "/api/user/token-info";
            default -> null;
        };

        if (endpoint == null) {
            return Map.of("error", "Action not implemented: " + state.getAction());
        }

        try {
            // In production: use WebClient with the actual Resource Server URL
            // For now: return mock data demonstrating the pattern
            return Map.of(
                "userId", state.getUserId(),
                "action", state.getAction(),
                "scope", state.getScope(),
                "endpoint", endpoint,
                "_note", "In production, call Resource Server at http://ciba-resource-server:8080" + endpoint,
                "_accessTokenReceived", state.getAccessToken() != null,
                "events", List.of(
                    Map.of("id", "evt1", "summary", "Meeting with team", "start", "2026-08-02T10:00:00Z"),
                    Map.of("id", "evt2", "summary", "Sprint review", "start", "2026-08-03T15:00:00Z")
                )
            );
        } catch (Exception e) {
            log.error("[{}] Resource Server call failed: {}", state.getRequestId(), e.getMessage());
            return Map.of("error", "Resource Server unavailable: " + e.getMessage());
        }
    }

    private String actionToScope(String action) {
        return switch (action) {
            // Calendar
            case "calendar_list"    -> "openid profile email calendar.read";
            case "calendar_create"  -> "openid profile email calendar.write";
            case "calendar_update"  -> "openid profile email calendar.write";
            // Email
            case "email_list"       -> "openid profile email";
            case "email_send"       -> "openid profile email email.send";
            case "email_modify"     -> "openid profile email email.modify";
            // Profile
            case "profile"          -> "openid profile email";
            case "token_info"       -> "openid profile email";
            default                 -> "openid profile email";
        };
    }

    private String actionToBindingMessage(String action) {
        return switch (action) {
            case "calendar_list"   -> "Read your calendar";
            case "calendar_create" -> "Create a calendar event";
            case "calendar_update" -> "Update a calendar event";
            case "email_list"      -> "Read your emails";
            case "email_send"      -> "Send an email";
            case "email_modify"    -> "Modify your email";
            case "profile"         -> "Access your profile";
            case "token_info"      -> "View session information";
            default                -> "Authorize: " + action;
        };
    }

    private void validateAction(String action) {
        Set<String> valid = Set.of(
            "calendar_list", "calendar_create", "calendar_update",
            "email_list", "email_send", "email_modify",
            "profile", "token_info"
        );
        if (!valid.contains(action)) {
            throw new IllegalArgumentException(
                "Unknown action: " + action + ". Valid: " + valid);
        }
    }

    // ── Mutable State class (replaces record to allow field mutation) ───

    private static class RequestState {
        private String requestId;
        private String authReqId;
        private String userId;
        private String action;
        private String scope;
        private String bindingMessage;
        private Map<String, Object> params;
        private Instant createdAt;
        private Instant expiresAt;
        private AuthState state;
        private String accessToken;
        private String idToken;
        private Integer expiresIn;

        RequestState(String requestId, String authReqId, String userId, String action,
                      String scope, String bindingMessage, Map<String, Object> params,
                      Instant createdAt, Instant expiresAt, AuthState state,
                      String accessToken, String idToken, Integer expiresIn) {
            this.requestId = requestId;
            this.authReqId = authReqId;
            this.userId = userId;
            this.action = action;
            this.scope = scope;
            this.bindingMessage = bindingMessage;
            this.params = params;
            this.createdAt = createdAt;
            this.expiresAt = expiresAt;
            this.state = state;
            this.accessToken = accessToken;
            this.idToken = idToken;
            this.expiresIn = expiresIn;
        }

        // Getters
        String getRequestId() { return requestId; }
        String getAuthReqId() { return authReqId; }
        String getUserId() { return userId; }
        String getAction() { return action; }
        String getScope() { return scope; }
        String getBindingMessage() { return bindingMessage; }
        Map<String, Object> getParams() { return params; }
        Instant getCreatedAt() { return createdAt; }
        Instant getExpiresAt() { return expiresAt; }
        AuthState getState() { return state; }
        String getAccessToken() { return accessToken; }
        String getIdToken() { return idToken; }
        Integer getExpiresIn() { return expiresIn; }

        // Setters
        void setRequestId(String requestId) { this.requestId = requestId; }
        void setAuthReqId(String authReqId) { this.authReqId = authReqId; }
        void setUserId(String userId) { this.userId = userId; }
        void setAction(String action) { this.action = action; }
        void setScope(String scope) { this.scope = scope; }
        void setBindingMessage(String bindingMessage) { this.bindingMessage = bindingMessage; }
        void setParams(Map<String, Object> params) { this.params = params; }
        void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }
        void setExpiresAt(Instant expiresAt) { this.expiresAt = expiresAt; }
        void setState(AuthState state) { this.state = state; }
        void setAccessToken(String accessToken) { this.accessToken = accessToken; }
        void setIdToken(String idToken) { this.idToken = idToken; }
        void setExpiresIn(Integer expiresIn) { this.expiresIn = expiresIn; }
    }

    private enum AuthState {
        PENDING, APPROVED, DENIED, EXPIRED, COMPLETED, ERROR
    }
}
