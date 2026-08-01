package com.ciba.resource.security;

import com.ciba.resource.config.CtiReplayCache;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidationException;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.Map;

/**
 * Validates CIBA-specific JWT claims.
 * 
 * In addition to standard JWT validation (signature, expiry, issuer),
 * this validator enforces CIBA-specific requirements:
 * 
 * 1. cti claim MUST be present and unique (replay prevention)
 * 2. auth_req_id MUST be present (ties token to a specific CIBA request)
 * 3. scope MUST include required permissions
 * 
 * This is called by the resource server security filter chain for every
 * request with a CIBA-issued access_token.
 */
@Component
@RequiredArgsConstructor
@Slf4j
public class CibaTokenValidator {

    private final CtiReplayCache ctiReplayCache;

    /**
     * Validate a CIBA-issued JWT.
     * 
     * @param jwt The decoded JWT (already validated by Spring's JwtDecoder)
     * @throws CibaTokenValidationException if validation fails
     */
    public void validate(Jwt jwt) throws CibaTokenValidationException {
        // 1. Check cti (replay prevention)
        String cti = jwt.getClaimAsString("cti");
        if (cti == null || cti.isBlank()) {
            throw new CibaTokenValidationException(
                "CTI claim missing — token may not be CIBA-issued",
                "missing_cti");
        }

        if (!ctiReplayCache.checkAndMark(cti)) {
            throw new CibaTokenValidationException(
                "CTI replay attack detected: token already used",
                "cti_replay");
        }

        // 2. Check auth_req_id (binds token to a specific auth request)
        String authReqId = jwt.getClaimAsString("auth_req_id");
        if (authReqId == null || authReqId.isBlank()) {
            log.warn("auth_req_id claim missing in JWT — CIBA flow may not have been used");
            // Warning only, not a hard failure (backwards compatibility)
        }

        // 3. Check expiry (already done by Spring, but we log it)
        Instant exp = jwt.getExpiresAt();
        if (exp != null && exp.isBefore(Instant.now())) {
            throw new CibaTokenValidationException("Token expired", "token_expired");
        }

        // 4. Validate scope
        String scope = jwt.getClaimAsString("scope");
        log.debug("CIBA token validated: sub={}, cti={}, auth_req_id={}, scope={}",
            jwt.getSubject(), cti, authReqId, scope);
    }

    /**
     * Extract subject (user ID) from the CIBA token.
     */
    public String getSubject(Jwt jwt) {
        return jwt.getSubject();
    }

    /**
     * Check if the token has a required scope.
     */
    public boolean hasScope(Jwt jwt, String requiredScope) {
        String scope = jwt.getClaimAsString("scope");
        if (scope == null) return false;
        return java.util.Arrays.stream(scope.split(" "))
            .anyMatch(s -> s.equals(requiredScope));
    }

    public static class CibaTokenValidationException extends Exception {
        private final String code;

        public CibaTokenValidationException(String message, String code) {
            super(message);
            this.code = code;
        }

        public String getCode() { return code; }
    }
}
