package com.poc.api.security;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.util.Assert;

import java.util.List;

/**
 * Validador que rechaza tokens JWT cuyo claim {@code aud} NO incluye el audience
 * esperado para este Resource Server.
 *
 * <p>Spring Security NO valida audience por defecto (RFC 7519 lo define como
 * obligatorio, pero Spring lo deja a la app). Este validator se enchufa en el
 * {@code NimbusJwtDecoder} vía {@code DelegatingOAuth2TokenValidator} dentro de
 * {@link com.poc.api.config.SecurityConfig}.</p>
 *
 * <p>Acepta tanto {@code aud} como {@code List<String>} (caso típico de KC y
 * Azure AD) como {@code String} simple (RFC minimalista).</p>
 */
public class JwtAudienceValidator implements OAuth2TokenValidator<Jwt> {

    private static final String ERROR_CODE = "invalid_audience";

    private final String expectedAudience;

    public JwtAudienceValidator(String expectedAudience) {
        Assert.hasText(expectedAudience, "expectedAudience must not be empty");
        this.expectedAudience = expectedAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        // Jwt#getAudience() devuelve List<String> ya normalizado por Spring;
        // si aud=string, Spring lo envuelve en singletonList. Si aud=ausente,
        // devuelve lista vacía.
        List<String> audiences = jwt.getAudience();
        if (audiences == null || audiences.isEmpty()) {
            return OAuth2TokenValidatorResult.failure(buildError("missing"));
        }
        if (audiences.contains(expectedAudience)) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(buildError("mismatch"));
    }

    private OAuth2Error buildError(String reason) {
        return new OAuth2Error(
                ERROR_CODE,
                "The required audience '" + expectedAudience + "' is missing or wrong ("
                        + reason + ")",
                "https://tools.ietf.org/html/rfc7519#section-4.1.3"
        );
    }
}
