package com.poc.api.security;

import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.proc.JWSVerificationKeySelector;
import com.nimbusds.jose.proc.SecurityContext;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import com.nimbusds.jwt.proc.DefaultJWTProcessor;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtException;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * Test unitario (sin Spring context) que verifica EXCLUSIVAMENTE la lógica del
 * {@link JwtAudienceValidator}.
 *
 * <p>Los 4 escenarios:</p>
 * <ul>
 *   <li>aud = ['spring-boot-api', 'account'] → NO error (resource server acepta).</li>
 *   <li>aud = [] → error invalid_token / invalid_audience.</li>
 *   <li>aud = ['otro-api'] → error invalid_audience.</li>
 *   <li>aud ausente (no es string ni Collection) → error invalid_audience.</li>
 * </ul>
 */
@DisplayName("JwtAudienceValidator — unit")
class JwtAudienceValidatorTest {

    private final JwtAudienceValidator validator = new JwtAudienceValidator("spring-boot-api");

    @Test
    @DisplayName("aud contiene spring-boot-api → success")
    void accepts_when_target_audience_is_in_claim() {
        Jwt jwt = jwtWithAudience(List.of("spring-boot-api", "account"));
        OAuth2TokenValidatorResult result = validator.validate(jwt);
        assertThat(result.hasErrors()).isFalse();
    }

    @Test
    @DisplayName("aud = ['otro-api'] → falla con OAuth2Error invalid_audience")
    void rejects_when_audience_is_wrong() {
        Jwt jwt = jwtWithAudience(List.of("some-other-api"));
        OAuth2TokenValidatorResult result = validator.validate(jwt);
        assertThat(result.hasErrors()).isTrue();
        OAuth2Error err = result.getErrors().iterator().next();
        assertThat(err.getErrorCode()).isEqualTo("invalid_audience");
        assertThat(err.getDescription()).contains("spring-boot-api");
    }

    @Test
    @DisplayName("aud ausente → falla invalid_audience")
    void rejects_when_audience_is_missing() {
        Jwt jwt = jwtWithClaims(Map.of("sub", "abc")); // sin aud
        OAuth2TokenValidatorResult result = validator.validate(jwt);
        assertThat(result.hasErrors()).isTrue();
        assertThat(result.getErrors().iterator().next().getErrorCode()).isEqualTo("invalid_audience");
    }

    @Test
    @DisplayName("aud como string simple 'spring-boot-api' → success (defensivo)")
    void accepts_when_audience_claim_is_plain_string() {
        Instant now = Instant.now();
        Jwt jwt = Jwt.withTokenValue("dummy")
                .header("alg", "RS256")
                .claim("aud", "spring-boot-api")
                .issuedAt(now.minusSeconds(5))
                .expiresAt(now.plusSeconds(60))
                .subject("user-1")
                .build();

        OAuth2TokenValidatorResult result = validator.validate(jwt);
        assertThat(result.hasErrors()).isFalse();
    }

    @Test
    @DisplayName("aud = [] → falla invalid_audience")
    void rejects_when_audience_is_empty_list() {
        Jwt jwt = jwtWithAudience(List.of());
        OAuth2TokenValidatorResult result = validator.validate(jwt);
        assertThat(result.hasErrors()).isTrue();
    }

    // ── Helpers ──────────────────────────────────────────────────────────

    private Jwt jwtWithAudience(List<String> aud) {
        return jwtWithClaims(Map.of(
                "aud", aud,
                "sub", "sub-1"
        ));
    }

    private Jwt jwtWithClaims(Map<String, Object> claims) {
        Instant now = Instant.now();
        Jwt.Builder b = Jwt.withTokenValue("dummy")
                .header("alg", "RS256")
                .issuedAt(now.minusSeconds(5))
                .expiresAt(now.plusSeconds(60));
        for (var e : claims.entrySet()) {
            b.claim(e.getKey(), e.getValue());
        }
        return b.build();
    }
}
