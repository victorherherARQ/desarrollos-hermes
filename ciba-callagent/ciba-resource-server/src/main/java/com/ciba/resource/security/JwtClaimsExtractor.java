package com.ciba.resource.security;

import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * Extracts standard + CIBA-specific claims from a validated JWT.
 */
@Component
public class JwtClaimsExtractor {

    public record UserInfo(
        String sub,
        String name,
        String email,
        String preferredUsername,
        Instant updatedAt
    ) {}

    public UserInfo extractUserInfo(Jwt jwt) {
        return new UserInfo(
            jwt.getSubject(),
            jwt.getClaimAsString("name"),
            jwt.getClaimAsString("email"),
            jwt.getClaimAsString("preferred_username"),
            jwt.getClaim("updated_at") != null
                ? Instant.ofEpochSecond(((Number) jwt.getClaim("updated_at")).longValue())
                : null
        );
    }

    public String extractCti(Jwt jwt) {
        return jwt.getClaimAsString("cti");
    }

    public String extractAuthReqId(Jwt jwt) {
        return jwt.getClaimAsString("auth_req_id");
    }

    public List<String> extractScopes(Jwt jwt) {
        String scope = jwt.getClaimAsString("scope");
        if (scope == null) return List.of();
        return List.of(scope.split(" "));
    }
}
