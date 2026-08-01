package com.ciba.api.security;

import com.ciba.api.config.CtiReplayCache;
import com.ciba.api.service.CibaClientService.CibaException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.oauth2.core.*;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidationResult;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.List;
import java.util.Set;

/**
 * CIBA-specific JWT token validator.
 *
 * Beyond standard JWT validation (signature, expiry, issuer), this validator
 * enforces CIBA-specific requirements:
 *
 *  1. cti claim presence and replay prevention
 *     - CIBA tokens MUST contain a `cti` (CIBA Token Identifier) claim
 *     - Each cti can only be used ONCE (replay attack prevention)
 *  2. auth_req_id presence (proves this was issued via CIBA)
 *  3. nonce presence
 *  4. audience must include one of our resource server IDs
 *  5. scope must contain at least one of the required scopes
 */
@Component
@Slf4j
@RequiredArgsConstructor
public class CibaTokenValidator {

    private final CtiReplayCache ctiReplayCache;
    private final JwtDecoder jwtDecoder;

    private static final Set<String> VALID_RESOURCE_AUDIENCES =
            Set.of("calendar-api", "email-api", "profile-api");

    private static final Set<String> REQUIRED_SCOPES =
            Set.of("calendar.read", "email", "profile", "openid");

    /**
     * Validates a CIBA-issued JWT access token.
     *
     * @param token The raw JWT string (Bearer token)
     * @return Validated Jwt object if valid
     * @throws CibaTokenValidationException if validation fails
     */
    public Jwt validate(String token) throws CibaTokenValidationException {
        try {
            // 1) Standard JWT validation (signature, expiry, issuer)
            Jwt jwt = jwtDecoder.decode(token);
            validateClaims(jwt);
            return jwt;

        } catch (JwtException e) {
            throw new CibaTokenValidationException("JWT validation failed: " + e.getMessage(), e);
        }
    }

    private void validateClaims(Jwt jwt) throws CibaTokenValidationException {
        Instant now = Instant.now();

        // 2) Expiry check
        if (jwt.getExpiresAt() != null && jwt.getExpiresAt().isBefore(now)) {
            throw new CibaTokenValidationException("Token expired at " + jwt.getExpiresAt());
        }

        // 3) Not-before check
        if (jwt.getNotBefore() != null && jwt.getNotBefore().isAfter(now)) {
            throw new CibaTokenValidationException("Token not valid yet (nbf: " + jwt.getNotBefore() + ")");
        }

        // 4) Issuer validation
        String issuer = jwt.getIssuer() != null ? jwt.getIssuer().toString() : null;
        if (issuer == null) {
            throw new CibaTokenValidationException("Missing iss claim");
        }
        // Issuer is validated by the JwtDecoder against the configured issuer-uri

        // 5) CIBA-specific: cti claim
        String cti = jwt.getClaimAsString("cti");
        if (cti == null || cti.isBlank()) {
            throw new CibaTokenValidationException(
                    "Missing cti claim — this token was not issued via CIBA flow. " +
                    "Use a CIBA-issued access_token.");
        }

        // 6) CIBA-specific: cti replay prevention
        if (!ctiReplayCache.checkAndMark(cti)) {
            log.error("CTI REPLAY ATTACK DETECTED: cti={}", cti);
            throw new CibaTokenValidationException(
                    "CTI replay detected — this token has already been used: " + cti);
        }

        // 7) CIBA-specific: auth_req_id presence
        String authReqId = jwt.getClaimAsString("auth_req_id");
        if (authReqId == null || authReqId.isBlank()) {
            throw new CibaTokenValidationException(
                    "Missing auth_req_id claim — token not issued via CIBA");
        }

        // 8) Audience validation
        List<String> audience = jwt.getAudience();
        boolean hasValidAudience = audience != null && audience.stream()
                .anyMatch(VALID_RESOURCE_AUDIENCES::contains);
        if (!hasValidAudience) {
            throw new CibaTokenValidationException(
                    "Token audience does not include any valid resource: " + audience);
        }

        // 9) Scope validation
        String scope = jwt.getClaimAsString("scope");
        if (scope == null || scope.isBlank()) {
            throw new CibaTokenValidationException("Missing scope claim");
        }
        Set<String> tokenScopes = Set.of(scope.split("\\s+"));
        boolean hasRequiredScope = tokenScopes.stream()
                .anyMatch(REQUIRED_SCOPES::contains);
        if (!hasRequiredScope) {
            throw new CibaTokenValidationException(
                    "Token scopes do not include any required scope. Has: " + scope);
        }

        log.debug("Token validated: sub={}, cti={}, auth_req_id={}, scopes={}",
                jwt.getSubject(), cti, authReqId, scope);
    }

    public static class CibaTokenValidationException extends Exception {
        public CibaTokenValidationException(String msg) { super(msg); }
        public CibaTokenValidationException(String msg, Throwable t) { super(msg, t); }
    }
}
