package com.poc.api.config;

import com.poc.api.security.JwtAudienceValidator;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.security.web.SecurityFilterChain;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;

/**
 * Configuración de seguridad del API.
 *
 * <p>Actúa como Resource Server de OAuth2/OIDC validando JWTs emitidos por
 * Keycloak contra {@code spring.security.oauth2.resourceserver.jwt.issuer-uri}.
 * Es la pieza que reemplaza a Apigee en este PoC.</p>
 */
@Configuration
@EnableMethodSecurity   // habilita @PreAuthorize("hasAuthority('SCOPE_xxx')") en controllers
public class SecurityConfig {

    /**
     * Audience que este Resource Server exige en el claim {@code aud} del JWT.
     * Debe coincidir con lo que Keycloak emite en el access_token
     * (configurado a nivel de cliente en el realm {@code agent-poc}).
     */
    private static final String EXPECTED_AUDIENCE = "spring-boot-api";

    @Bean
    public SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            // API stateless
            .csrf(csrf -> csrf.disable())
            .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))

            // Resource Server con JWT estándar (Keycloak emite JWTs estándar)
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtAuthenticationConverter()))
            )

            .authorizeHttpRequests(auth -> auth
                // Endpoints públicos de health
                .requestMatchers("/health").permitAll()
                .requestMatchers("/actuator/health", "/actuator/info").permitAll()
                // Resto requiere autenticación JWT válida
                .anyRequest().authenticated()
            );

        return http.build();
    }

    /**
     * JwtDecoder explícito: usa {@link NimbusJwtDecoder} construido a partir
     * del issuer-uri (que descubre el endpoint JWKS automáticamente) y le
     * enchufa un validador delegado compuesto por:
     * <ul>
     *   <li>Default validators de Spring (exp, nbf, iss)</li>
     *   <li>Nuestro {@link JwtAudienceValidator}</li>
     * </ul>
     *
     * <p>Sin este @Bean, Spring auto-configura un {@code NimbusJwtDecoder} sólo
     * con los validators por defecto — y NO audita {@code aud}.</p>
     */
    @Bean
    public JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}") String issuerUri
    ) {
        NimbusJwtDecoder decoder = NimbusJwtDecoder.withIssuerLocation(issuerUri).build();

        OAuth2TokenValidator<Jwt> defaults = JwtValidators.createDefaultWithIssuer(issuerUri);
        OAuth2TokenValidator<Jwt> audience = new JwtAudienceValidator(EXPECTED_AUDIENCE);

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(defaults, audience));
        return decoder;
    }

    /**
     * Convierte el JWT en un {@link JwtAuthenticationToken} cuyas
     * {@link GrantedAuthority} se construyen a partir de los claims
     * estándar de OAuth2: {@code scope} (RFC 6749) o {@code scp}
     * (variante usada por algunos IdPs).
     */
    @Bean
    public JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(new ScopeAuthoritiesConverter());
        // El principal.name por defecto es 'sub', como pide la PoC.
        return converter;
    }

    /**
     * {@link Converter} que extrae los scopes del claim {@code scope}
     * (space-separated) o {@code scp} (array) y los mapea a
     * {@link SimpleGrantedAuthority} con prefijo {@code SCOPE_},
     * tal como espera Spring Security ({@code hasAuthority("SCOPE_xxx")}).
     */
    static class ScopeAuthoritiesConverter
            implements Converter<Jwt, Collection<GrantedAuthority>> {

        private static final String SCOPE_PREFIX = "SCOPE_";
        private static final String CLAIM_SCOPE = "scope";
        private static final String CLAIM_SCP = "scp";

        @Override
        public Collection<GrantedAuthority> convert(Jwt jwt) {
            List<String> scopes = new ArrayList<>();

            Object scope = jwt.getClaim(CLAIM_SCOPE);
            if (scope instanceof String s && !s.isBlank()) {
                scopes.addAll(Arrays.asList(s.split("\\s+")));
            }

            Object scp = jwt.getClaim(CLAIM_SCP);
            if (scp instanceof Collection<?> coll) {
                for (Object o : coll) {
                    if (o != null) scopes.add(o.toString());
                }
            } else if (scp instanceof String s && !s.isBlank()) {
                scopes.addAll(Arrays.asList(s.split("\\s+")));
            }

            if (scopes.isEmpty()) {
                return Collections.emptyList();
            }

            return scopes.stream()
                    .filter(s -> !s.isBlank())
                    .distinct()
                    .map(s -> (GrantedAuthority) new SimpleGrantedAuthority(SCOPE_PREFIX + s))
                    .collect(Collectors.toList());
        }
    }
}
