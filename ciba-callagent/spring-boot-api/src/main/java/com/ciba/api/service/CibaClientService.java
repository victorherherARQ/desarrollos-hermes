package com.ciba.api.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

import java.time.Duration;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.*;

/**
 * CIBA Client Service.
 *
 * Implements the CIBA Authentication Flow (OpenID Connect CIBA):
 * 1. POST /authreq  → initiate CIBA auth request, get auth_req_id
 * 2. Poll /token    → until user approves/denies or timeout
 *
 * Supports both poll mode and ping mode (via callback URL).
 *
 * Keycloak endpoint:
 *   POST {keycloak-url}/realms/{realm}/protocol/openid-connect/ext/ciba/auth/authreq
 *   POST {keycloak-url}/realms/{realm}/protocol/openid-connect/ext/ciba/auth/token
 */
@Service
@Slf4j
@RequiredArgsConstructor
public class CibaClientService {

    private final WebClient webClient = WebClient.builder().build();
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Value("${keycloak.base-url}")
    private String keycloakBaseUrl;

    @Value("${keycloak.realm}")
    private String realm;

    @Value("${keycloak.ciba-client.client-id}")
    private String clientId;

    @Value("${keycloak.ciba-client.client-secret}")
    private String clientSecret;

    @Value("${keycloak.ciba-client.mode}")
    private String cibaMode; // "poll" or "ping"

    @Value("${keycloak.ciba-client.backchannel-client-uri:}")
    private String backchannelClientUri;

    @Value("${keycloak.ciba-client.poll-interval-seconds}")
    private int pollIntervalSeconds;

    @Value("${keycloak.ciba-client.max-poll-attempts}")
    private int maxPollAttempts;

    // In-flight polling jobs keyed by auth_req_id
    private final ConcurrentHashMap<String, CompletableFuture<CibaTokenResponse>> pendingFutures = new ConcurrentHashMap<>();

    // ── Public API ───────────────────────────────────────────────────────────────

    /**
     * Initiates a CIBA authentication request.
     *
     * @param loginHint   User identifier (email, username, or sub claim)
     * @param bindingMsg  Message shown to user on their phone (max 200 chars)
     * @param scope       Space-separated list of OpenID scopes
     * @return            CibaAuthResponse with auth_req_id and instructions
     */
    public CibaAuthResponse initiateAuthRequest(String loginHint, String bindingMsg, String scope) {
        String nonce = UUID.randomUUID().toString();
        String authReqId = doAuthRequest(loginHint, bindingMsg, scope, nonce);
        log.info("CIBA auth request initiated: auth_req_id={}, loginHint={}, mode={}", authReqId, loginHint, cibaMode);

        return new CibaAuthResponse(
                authReqId,
                cibaMode,
                pollIntervalSeconds,
                maxPollAttempts * pollIntervalSeconds,
                buildStatusUrl(authReqId)
        );
    }

    /**
     * Async: initiate auth request and start polling in background.
     * Returns a CompletableFuture that completes when the user approves.
     */
    @Async
    public CompletableFuture<CibaTokenResponse> initiateAuthRequestAsync(String loginHint,
                                                                         String bindingMsg,
                                                                         String scope,
                                                                         String userRequestId) {
        String authReqId = doAuthRequest(loginHint, bindingMsg, scope, UUID.randomUUID().toString());
        log.info("Async CIBA flow started: auth_req_id={}", authReqId);

        CompletableFuture<CibaTokenResponse> future = new CompletableFuture<>();
        pendingFutures.put(authReqId, future);

        // Start polling in a virtual thread (or cached thread pool)
        CompletableFuture.runAsync(() -> pollForToken(authReqId, future));

        return future;
    }

    /**
     * Synchronous polling: poll until resolution or timeout.
     * Used when the caller wants to block.
     */
    public CibaTokenResponse pollForTokenSync(String authReqId) {
        return pollForToken(authReqId, new CompletableFuture<>());
    }

    // ── Internal ────────────────────────────────────────────────────────────────

    private String doAuthRequest(String loginHint, String bindingMsg, String scope, String nonce) {
        String authEndpoint = keycloakBaseUrl + "/realms/" + realm
                + "/protocol/openid-connect/ext/ciba/auth/authreq";

        ObjectNode body = objectMapper.createObjectNode();
        body.put("client_id", clientId);
        body.put("client_secret", clientSecret);
        body.put("login_hint", loginHint);
        body.put("binding_message", bindingMsg.length() > 200 ? bindingMsg.substring(0, 200) : bindingMsg);
        body.put("requested_expiry", 300); // 5 minutes to approve
        body.put("requested_scope", scope);

        if ("ping".equals(cibaMode) && backchannelClientUri != null) {
            body.put("backchannel_client_notification_endpoint", backchannelClientUri);
        }

        JsonNode response = webClient.post()
                .uri(authEndpoint)
                .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                .bodyValue(body)
                .retrieve()
                .bodyToMono(JsonNode.class)
                .retryWhen(Retry.backoff(3, Duration.ofSeconds(1))
                        .filter(ex -> ex.getMessage() != null && ex.getMessage().contains("5")))
                .timeout(Duration.ofSeconds(30))
                .onErrorResume(e -> Mono.error(
                        new CibaException("CIBA auth request failed: " + e.getMessage(), e)))
                .block();

        if (response == null || !response.has("auth_req_id")) {
            throw new CibaException("Invalid CIBA auth response: " + response);
        }
        return response.get("auth_req_id").asText();
    }

    private CibaTokenResponse pollForToken(String authReqId, CompletableFuture<CibaTokenResponse> future) {
        int attempts = 0;

        while (attempts < maxPollAttempts) {
            try {
                Thread.sleep(pollIntervalSeconds * 1000L);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                future.completeExceptionally(new CibaException("Polling interrupted"));
                pendingFutures.remove(authReqId);
                return null;
            }

            try {
                CibaTokenResponse tokenResponse = doTokenRequest(authReqId);
                if (tokenResponse != null) {
                    log.info("CIBA token received: sub={}, expires_in={}",
                            tokenResponse.sub(), tokenResponse.expiresIn());
                    future.complete(tokenResponse);
                    pendingFutures.remove(authReqId);
                    return tokenResponse;
                }
            } catch (CibaAuthPendingException e) {
                attempts++;
                log.debug("Poll attempt {} — authorization_pending", attempts);
            } catch (CibaException e) {
                log.warn("Poll error: {}", e.getMessage());
                attempts++;
            }
        }

        String msg = "CIBA polling timed out after " + maxPollAttempts + " attempts";
        log.warn(msg);
        future.completeExceptionally(new CibaException(msg));
        pendingFutures.remove(authReqId);
        return null;
    }

    private CibaTokenResponse doTokenRequest(String authReqId) {
        String tokenEndpoint = keycloakBaseUrl + "/realms/" + realm
                + "/protocol/openid-connect/ext/ciba/auth/token";

        ObjectNode body = objectMapper.createObjectNode();
        body.put("grant_type", "urn:openid:params:grant-type:ciba");
        body.put("auth_req_id", authReqId);
        body.put("client_id", clientId);

        try {
            JsonNode response = webClient.post()
                    .uri(tokenEndpoint)
                    .header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
                    .bodyValue(body)
                    .retrieve()
                    .bodyToMono(JsonNode.class)
                    .timeout(Duration.ofSeconds(30))
                    .block();

            if (response == null) {
                throw new CibaException("Empty token response");
            }

            // Check for CIBA-specific errors
            if (response.has("error")) {
                String error = response.get("error").asText();
                if ("authorization_pending".equals(error)) {
                    throw new CibaAuthPendingException();
                }
                if ("access_denied".equals(error)) {
                    throw new CibaAccessDeniedException(response.get("error_description").asText());
                }
                throw new CibaException("CIBA token error: " + error
                        + " — " + response.get("error_description").asText());
            }

            return parseTokenResponse(response);

        } catch (CibaAuthPendingException | CibaAccessDeniedException e) {
            throw e; // re-throw special exceptions
        } catch (Exception e) {
            if (e.getCause() instanceof java.time.Duration || e.getMessage() != null
                    && e.getMessage().contains("401")) {
                // Wrong client secret
                throw new CibaException("CIBA token request failed (401 — check client secret): "
                        + e.getMessage());
            }
            throw new CibaException("Token request failed: " + e.getMessage(), e);
        }
    }

    private CibaTokenResponse parseTokenResponse(JsonNode node) {
        return new CibaTokenResponse(
                node.has("access_token") ? node.get("access_token").asText() : null,
                node.has("id_token") ? node.get("id_token").asText() : null,
                node.has("refresh_token") ? node.get("refresh_token").asText() : null,
                node.has("token_type") ? node.get("token_type").asText() : "Bearer",
                node.has("expires_in") ? node.get("expires_in").asInt() : 300,
                node.has("scope") ? node.get("scope").asText() : ""
        );
    }

    private String buildStatusUrl(String authReqId) {
        return "/ciba/status/" + authReqId;
    }

    // ── DTOs ───────────────────────────────────────────────────────────────────

    public record CibaAuthResponse(
            String authReqId,
            String mode,           // "poll" or "ping"
            int intervalSeconds,
            int timeoutSeconds,
            String statusUrl
    ) {}

    public record CibaTokenResponse(
            String accessToken,
            String idToken,
            String refreshToken,
            String tokenType,
            int expiresIn,
            String scope
    ) {
        public String sub() {
            // Decode JWT to extract sub claim (without signature verification here)
            try {
                String[] parts = accessToken.split("\\.");
                if (parts.length == 3) {
                    String payload = new String(java.util.Base64.getUrlDecoder().decode(parts[1]));
                    JsonNode node = objectMapper.readTree(payload);
                    return node.has("sub") ? node.get("sub").asText() : null;
                }
            } catch (Exception e) {
                log.warn("Could not decode sub from token: {}", e.getMessage());
            }
            return null;
        }
    }

    // ── Exceptions ─────────────────────────────────────────────────────────────

    public static class CibaException extends RuntimeException {
        public CibaException(String msg) { super(msg); }
        public CibaException(String msg, Throwable t) { super(msg, t); }
    }

    public static class CibaAuthPendingException extends CibaException {
        public CibaAuthPendingException() { super("authorization_pending"); }
    }

    public static class CibaAccessDeniedException extends CibaException {
        public CibaAccessDeniedException(String msg) { super("access_denied: " + msg); }
    }
}
