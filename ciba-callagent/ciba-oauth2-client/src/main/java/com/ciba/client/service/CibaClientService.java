package com.ciba.client.service;

import com.ciba.client.config.CibaProperties;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import java.time.Duration;
import java.time.Instant;
import java.util.Map;

@Service
@RequiredArgsConstructor
@Slf4j
public class CibaClientService {

    private final WebClient webClient;
    private final CibaProperties cibaProps;
    private final ObjectMapper objectMapper = new ObjectMapper();

    private static final String CIBA_AUTH_REQ_PATH = "/protocol/openid-connect/ext/ciba/auth/authreq";
    private static final String CIBA_TOKEN_PATH = "/protocol/openid-connect/ext/ciba/auth/token";

    // ── Step 1: POST /authreq ───────────────────────────────────────────────

    public record AuthReqResult(String authReqId, int expiresIn, int interval) {}

    public AuthReqResult initiateAuthRequest(String userId, String bindingMessage, String scope) {
        String url = keycloakUrl(CIBA_AUTH_REQ_PATH);
        log.info("Initiating CIBA authreq: userId={}, bindingMessage={}", userId, bindingMessage);

        JsonNode response = webClient.post()
            .uri(url)
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .bodyValue(buildAuthReqBody(userId, bindingMessage, scope))
            .retrieve()
            .bodyToMono(JsonNode.class)
            .block(Duration.ofSeconds(30));

        if (response == null || !response.has("auth_req_id")) {
            throw new CibaException("Invalid response from Keycloak: " + response);
        }

        return new AuthReqResult(
            response.get("auth_req_id").asText(),
            response.has("expires_in") ? response.get("expires_in").asInt() : 300,
            response.has("interval") ? response.get("interval").asInt() : 5
        );
    }

    // ── Step 2: POST /token (poll) ─────────────────────────────────────────

    /**
     * Poll once. Returns CibaTokenResult on success, throws subclass on error conditions.
     */
    public CibaTokenResult pollToken(String authReqId) {
        String url = keycloakUrl(CIBA_TOKEN_PATH);
        log.debug("Polling CIBA token: authReqId={}", authReqId);

        try {
            JsonNode response = webClient.post()
                .uri(url)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .bodyValue(buildTokenPollBody(authReqId))
                .retrieve()
                .bodyToMono(JsonNode.class)
                .block(Duration.ofSeconds(30));

            if (response == null) throw new CibaException("Empty response from Keycloak");

            return new CibaTokenResult(
                response.get("access_token").asText(),
                response.has("id_token") ? response.get("id_token").asText() : null,
                response.has("token_type") ? response.get("token_type").asText() : "Bearer",
                response.has("expires_in") ? response.get("expires_in").asInt() : 300,
                response.has("scope") ? response.get("scope").asText() : ""
            );

        } catch (WebClientResponseException e) {
            String error = parseError(e.getResponseBodyAsString());
            if ("authorization_pending".equals(error)) {
                throw new AuthorizationPendingException();
            } else if ("access_denied".equals(error)) {
                throw new AccessDeniedException();
            } else if ("expired_token".equals(error)) {
                throw new ExpiredTokenException();
            } else {
                throw new CibaException("Keycloak error: " + error + " — " + e.getResponseBodyAsString());
            }
        }
    }

    // ── Nested record: token result ─────────────────────────────────────

    public record CibaTokenResult(
        String accessToken,
        String idToken,
        String tokenType,
        int expiresIn,
        String scope
    ) {}

    // ── Ping callback (called by Keycloak) ───────────────────────────────

    /** POST /ciba/ping-callback — called by Keycloak when user approves (ping mode) */
    public record PingResult(String authReqId, String accessToken) {}

    public PingResult handlePingCallback(JsonNode payload) {
        String authReqId = payload.get("auth_req_id").asText();
        // Immediately poll to get the token
        CibaTokenResult token = pollToken(authReqId);
        return new PingResult(authReqId, token.accessToken());
    }

    // ── Exception hierarchy ────────────────────────────────────────────────

    public static class AuthorizationPendingException extends RuntimeException {
        public AuthorizationPendingException() { super("authorization_pending"); }
    }

    public static class AccessDeniedException extends RuntimeException {
        public AccessDeniedException() { super("access_denied"); }
    }

    public static class ExpiredTokenException extends RuntimeException {
        public ExpiredTokenException() { super("expired_token"); }
    }

    public static class CibaException extends RuntimeException {
        public CibaException(String msg) { super(msg); }
    }

    // ── Private helpers ───────────────────────────────────────────────────

    private String keycloakUrl(String path) {
        return cibaProps.getBaseUrl() + "/realms/" + cibaProps.getRealm() + path;
    }

    private String buildAuthReqBody(String userId, String bindingMessage, String scope) {
        return "client_id=" + encode(cibaProps.getClientId())
             + "&client_secret=" + encode(cibaProps.getClientSecret())
             + "&login_hint=" + encode(userId)
             + "&binding_message=" + encode(bindingMessage)
             + "&requested_scope=" + encode(scope)
             + "&request_parameter=" + encode(cibaProps.getSigningAlg());
    }

    private String buildTokenPollBody(String authReqId) {
        return "grant_type=urn:openid:params:grant-type:ciba"
             + "&auth_req_id=" + encode(authReqId)
             + "&client_id=" + encode(cibaProps.getClientId())
             + "&client_secret=" + encode(cibaProps.getClientSecret());
    }

    private String encode(String s) {
        try {
            return java.net.URLEncoder.encode(s, java.nio.charset.StandardCharsets.UTF_8);
        } catch (Exception e) {
            return s;
        }
    }

    private String parseError(String body) {
        try {
            JsonNode node = objectMapper.readTree(body);
            return node.has("error") ? node.get("error").asText() : "";
        } catch (Exception e) {
            return "";
        }
    }
}
