package com.ciba.api.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.beans.factory.annotation.Value;

/**
 * Spring Security configuration.
 *
 * Two filter chains with different @Order to handle both modes:
 *   1. /ciba/**  → public (CIBA client initiates auth — no auth required to START the flow)
 *   2. /api/**   → Bearer JWT required (Resource Server validates CIBA tokens)
 *
 * For CIBA tokens, specific validations are done in CibaTokenValidator:
 *   - cti claim (CIBA Token Identifier) replay prevention
 *   - auth_req_id presence
 *   - nonce presence
 */
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    // ── Security Filter Chain 1: Resource Server (highest priority) ───────────
    @Bean
    @Order(1)
    public SecurityFilterChain resourceServerFilterChain(HttpSecurity http,
            @Value("${keycloak.base-url}") String keycloakBaseUrl,
            @Value("${keycloak.realm}") String realm) throws Exception {

        String jwksUri = keycloakBaseUrl + "/realms/" + realm
                + "/protocol/openid-connect/certs";

        http
            .securityMatcher("/api/**", "/protected/**")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(sm -> sm.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/health", "/api/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt
                    .decoder(jwtDecoder(jwksUri))
                    .jwtAuthenticationConverter(jwtAuthenticationConverter())
                )
            );

        return http.build();
    }

    // ── Security Filter Chain 2: CIBA client endpoints (public) ───────────────
    @Bean
    @Order(2)
    public SecurityFilterChain cibaClientFilterChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/ciba/**", "/actuator/health")
            .csrf(csrf -> csrf.disable())
            .sessionManagement(sm -> sm.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/ciba/**", "/actuator/health").permitAll()
                .anyRequest().authenticated()
            );
        return http.build();
    }

    // ── Security Filter Chain 3: default ──────────────────────────────────────
    @Bean
    @Order(3)
    public SecurityFilterChain defaultFilterChain(HttpSecurity http) throws Exception {
        http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(sm -> sm.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/health", "/actuator/**").permitAll()
                .anyRequest().denyAll()
            );
        return http.build();
    }

    // ── JWT Decoder wired to Keycloak JWKS ─────────────────────────────────────
    @Bean
    public JwtDecoder jwtDecoder(@Value("${keycloak.base-url}") String keycloakBaseUrl,
                                  @Value("${keycloak.realm}") String realm) {
        String jwksUri = keycloakBaseUrl + "/realms/" + realm
                + "/protocol/openid-connect/certs";
        return NimbusJwtDecoder.withJwkSetUri(jwksUri).build();
    }

    // ── Maps JWT claims → Spring Security authorities ───────────────────────────
    @Bean
    public JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter grantedAuthoritiesConverter =
                new JwtGrantedAuthoritiesConverter();
        // Map "scope" claim → SCOPE_xxx authorities
        grantedAuthoritiesConverter.setAuthoritiesClaimName("scope");
        grantedAuthoritiesConverter.setAuthorityPrefix("SCOPE_");

        JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(grantedAuthoritiesConverter);
        return converter;
    }
}
