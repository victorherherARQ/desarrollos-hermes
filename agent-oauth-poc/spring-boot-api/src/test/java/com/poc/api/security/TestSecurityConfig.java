package com.poc.api.security;

import com.poc.api.config.SecurityConfig;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

import java.util.List;

/**
 * Override del {@link JwtDecoder} SOLO para los tests.
 *
 * <p>KC firma los tokens con
 * {@code iss = http://agent-poc-keycloak:8080/realms/agent-poc} (hostname
 * interno de docker). Cuando los tests corren FUERA de docker, ese hostname
 * no resuelve para fetchear JWKS — pero {@code localhost:8180} SÍ resuelve y
 * da acceso al mismo JWKS.</p>
 *
 * <p>Por eso:</p>
 * <ul>
 *   <li>Cargamos las claves públicas desde
 *       {@code http://localhost:8180/realms/agent-poc/protocol/openid-connect/certs}
 *       (vía withIssuerLocation, que descubre el JWKS).</li>
 *   <li>Sustituimos el issuer validator por uno que acepta los DOS valores:
 *       el interno (lo que KC firma) y el externo (lo que ve el test).</li>
 *   <li>Mantenemos intacto el {@link JwtAudienceValidator} y el resto de
 *       default validators (timestamps).</li>
 * </ul>
 *
 * <p>El resto de la cadena de seguridad (audience, signature, expiry) se
 * mantiene idéntica a producción.</p>
 */
@TestConfiguration
public class TestSecurityConfig {

    private static final String JWKS_HOST_URI = "http://localhost:8180/realms/agent-poc";
    private static final String ISSUER_INTERNAL = "http://agent-poc-keycloak:8080/realms/agent-poc";
    private static final String ISSUER_EXTERNAL = JWKS_HOST_URI;

    @Bean
    @Primary
    public JwtDecoder testJwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder.withIssuerLocation(JWKS_HOST_URI).build();

        // Default validators, pero SIN issuer (porque la lógica del issuer
        // la hacemos nosotros abajo para aceptar los dos nombres).
        OAuth2TokenValidator<Jwt> defaultsNoIssuer = JwtValidators.createDefault();
        OAuth2TokenValidator<Jwt> issuerDual = new TestJwtIssuerMultiValidator(
                List.of(ISSUER_INTERNAL, ISSUER_EXTERNAL));
        OAuth2TokenValidator<Jwt> audience = new JwtAudienceValidator("spring-boot-api");

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                defaultsNoIssuer, issuerDual, audience));
        return decoder;
    }
}
