package com.poc.api.config;

import com.auth0.jwt.JWT;
import com.auth0.jwt.JWTVerifier;
import com.auth0.jwt.algorithms.Algorithm;
import com.auth0.jwt.exceptions.JWTVerificationException;
import com.auth0.jwt.interfaces.DecodedJWT;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * Filtro HTTP que se ejecuta DESPUÉS de la autenticación JWT de Keycloak
 * (gracias a {@code @Order} alto en securityFilterChain). Lee el header
 * {@code X-Requested-Scope-Token} enviado por el cliente, lo valida con
 * {@code REQUESTED_SCOPE_SHARED_SECRET} (HS256), y filtra las authorities
 * del {@link JwtAuthenticationToken} a la intersección con el claim
 * {@code scope} del mini-JWT.
 *
 * <p><b>BUG KC 26.6.4 workaround:</b> el broker jwt-bearer ignora el param
 * {@code scope} del grant y emite el access_token con TODOS los scopes.
 * Para que el API pueda discriminar, el agente firma un mini-JWT HS256
 * con el scope original y lo pasa como header. Este filtro hace de
 * "down-scope" en el Resource Server.</p>
 *
 * <p>Si el header NO está presente, el filtro no hace nada (no narrowing).
 * Si está presente pero la firma es inválida, el filtro NO rechaza (200 OK
 * con authorities del access_token original). El cliente siempre puede
 * pasar el header si quiere down-scoping.</p>
 */
@Component
public class RequestedScopeFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(RequestedScopeFilter.class);
    private static final String HEADER = "X-Requested-Scope-Token";
    private static final String SCOPE_PREFIX = "SCOPE_";

    private final JWTVerifier verifier;

    public RequestedScopeFilter(
            @Value("${requested-scope.shared-secret:poC-shared-secret-CHANGE-ME-32bytes-min-para-hs256}")
            String sharedSecret
    ) {
        Algorithm alg = Algorithm.HMAC256(sharedSecret);
        this.verifier = JWT.require(alg)
                .withIssuer("agente-ia")
                .acceptLeeway(30)  // 30s clock skew
                .build();
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain
    ) throws ServletException, IOException {

        String requestedScopeToken = request.getHeader(HEADER);

        if (requestedScopeToken != null && !requestedScopeToken.isBlank()) {
            try {
                DecodedJWT jwt = verifier.verify(requestedScopeToken);
                String requestedScope = jwt.getClaim("scope").asString();

                if (requestedScope != null && !requestedScope.isBlank()) {
                    applyDownscoping(requestedScope);
                }
            } catch (JWTVerificationException e) {
                log.warn("X-Requested-Scope-Token inválido: {}", e.getMessage());
                // No rechazamos — el cliente puede haber omitido el header.
            }
        }

        chain.doFilter(request, response);
    }

    /**
     * Filtra las authorities del {@link JwtAuthenticationToken} en el
     * SecurityContext a la intersección con el requested_scope.
     */
    private void applyDownscoping(String requestedScope) {
        var auth = SecurityContextHolder.getContext().getAuthentication();
        if (!(auth instanceof JwtAuthenticationToken jat)) {
            return;  // No es JWT auth, no aplicamos
        }

        Set<String> requested = Arrays.stream(requestedScope.split("\\s+"))
                .filter(s -> !s.isBlank())
                .collect(Collectors.toSet());

        List<GrantedAuthority> filtered = jat.getAuthorities().stream()
                .filter(a -> {
                    String name = a.getAuthority();
                    if (name.startsWith(SCOPE_PREFIX)) {
                        return requested.contains(name.substring(SCOPE_PREFIX.length()));
                    }
                    return true;  // No es scope (es role), lo mantenemos
                })
                .collect(Collectors.toList());

        if (filtered.size() != jat.getAuthorities().size()) {
            log.debug("Downscoping: {} authorities -> {} (requested: {})",
                    jat.getAuthorities().size(), filtered.size(), requested);

            // Crear nuevo token con authorities filtradas
            AbstractAuthenticationToken narrowed = new JwtAuthenticationToken(
                    jat.getToken(), filtered, jat.getName());
            narrowed.setDetails(jat.getDetails());
            SecurityContextHolder.getContext().setAuthentication(narrowed);
        }
    }
}
