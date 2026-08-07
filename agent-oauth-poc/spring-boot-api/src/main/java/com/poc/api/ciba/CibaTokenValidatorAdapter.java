package com.poc.api.ciba;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

/**
 * Adapter que envuelve {@link CibaTokenValidator} en una
 * {@link OAuth2TokenValidator<Jwt>} compatible con Spring Security.
 *
 * <p>Se enchufa al {@code JwtDecoder} cuando CIBA está habilitado
 * (vía {@code ciba.enabled=true}). Si está deshabilitado, el bean queda
 * registrado pero NO se añade al decoder (ver
 * {@code SecurityConfig#jwtDecoder}).</p>
 *
 * <p>Decisión de diseño (ADR-001): para B2C compatibility, el CIBA validator
 * es <b>opt-in</b>. Por defecto {@code ciba.enabled=false}.</p>
 */
@Component
public class CibaTokenValidatorAdapter implements OAuth2TokenValidator<Jwt> {

    private static final Logger log = LoggerFactory.getLogger(CibaTokenValidatorAdapter.class);

    private final CibaTokenValidator cibaValidator;

    public CibaTokenValidatorAdapter(CibaTokenValidator cibaValidator) {
        this.cibaValidator = cibaValidator;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        try {
            cibaValidator.validate(jwt);
            return OAuth2TokenValidatorResult.success();
        } catch (CibaTokenValidator.CibaTokenValidationException e) {
            log.warn("CIBA validation failed: code={}, msg={}",
                     e.getCode(), e.getMessage());
            return OAuth2TokenValidatorResult.failure(
                new org.springframework.security.oauth2.core.OAuth2Error(
                    "ciba_validation_failed",
                    "CIBA: " + e.getMessage() + " (code=" + e.getCode() + ")",
                    null
                )
            );
        }
    }
}
