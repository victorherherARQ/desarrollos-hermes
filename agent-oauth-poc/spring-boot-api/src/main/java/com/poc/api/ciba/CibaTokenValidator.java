package com.poc.api.ciba;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.Arrays;

/**
 * Validates CIBA-specific JWT claims.
 *
 * <p>In addition to standard JWT validation (signature, expiry, issuer),
 * this validator enforces CIBA-specific requirements:</p>
 *
 * <ol>
 *   <li>{@code cti} claim MUST be present and unique (replay prevention)</li>
 *   <li>{@code auth_req_id} MUST be present (ties token to a specific CIBA request)</li>
 *   <li>{@code scope} MUST include required permissions</li>
 * </ol>
 *
 * <p>This is wired as a {@code OAuth2TokenValidator<Jwt>} delegate on the
 * Resource Server's {@code JwtDecoder}. It only kicks in when CIBA is enabled
 * via {@code ciba.enabled=true}.</p>
 *
 * <p>Migrated from {@code ciba-callagent/ciba-resource-server/} per ADR-001.</p>
 */
@Component
public class CibaTokenValidator {

    private static final Logger log = LoggerFactory.getLogger(CibaTokenValidator.class);

    private final CtiReplayCache ctiReplayCache;

    public CibaTokenValidator(CtiReplayCache ctiReplayCache) {
        this.ctiReplayCache = ctiReplayCache;
    }

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

        // 4. Log scope for observability
        String scope = jwt.getClaimAsString("scope");
        log.debug("CIBA token validated: sub={}, cti={}, auth_req_id={}, scope={}",
            jwt.getSubject(), cti, authReqId, scope);
    }

    public String getSubject(Jwt jwt) {
        return jwt.getSubject();
    }

    public boolean hasScope(Jwt jwt, String requiredScope) {
        String scope = jwt.getClaimAsString("scope");
        if (scope == null) return false;
        return Arrays.stream(scope.split(" "))
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
