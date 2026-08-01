package com.ciba.resource.controller;

import com.ciba.resource.security.CibaTokenValidator;
import com.ciba.resource.security.CibaTokenValidator.CibaTokenValidationException;
import com.ciba.resource.security.JwtClaimsExtractor;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.Map;

@RestController
@RequestMapping("/api/user")
@RequiredArgsConstructor
@Slf4j
public class UserController {

    private final CibaTokenValidator tokenValidator;
    private final JwtClaimsExtractor claimsExtractor;

    @GetMapping("/profile")
    public ResponseEntity<?> getProfile(@AuthenticationPrincipal Jwt jwt) {
        try {
            tokenValidator.validate(jwt);
        } catch (CibaTokenValidationException e) {
            return ResponseEntity.status(401)
                .body(Map.of("error", e.getCode(), "detail", e.getMessage()));
        }

        var info = claimsExtractor.extractUserInfo(jwt);

        return ResponseEntity.ok(Map.of(
            "sub", info.sub(),
            "name", info.name() != null ? info.name() : info.sub(),
            "email", info.email() != null ? info.email() : info.sub() + "@example.com",
            "username", info.preferredUsername() != null ? info.preferredUsername() : info.sub(),
            "auth_req_id", claimsExtractor.extractAuthReqId(jwt),
            "scopes", claimsExtractor.extractScopes(jwt),
            "cti", claimsExtractor.extractCti(jwt),
            "source", "ciba-resource-server"
        ));
    }

    @GetMapping("/token-info")
    public ResponseEntity<?> getTokenInfo(@AuthenticationPrincipal Jwt jwt) {
        try {
            tokenValidator.validate(jwt);
        } catch (CibaTokenValidationException e) {
            return ResponseEntity.status(401)
                .body(Map.of("error", e.getCode()));
        }

        return ResponseEntity.ok(Map.of(
            "sub", jwt.getSubject(),
            "issuer", jwt.getIssuer() != null ? jwt.getIssuer().toString() : "N/A",
            "audience", jwt.getAudience(),
            "expiresAt", jwt.getExpiresAt() != null ? jwt.getExpiresAt().toString() : "N/A",
            "issuedAt", jwt.getIssuedAt() != null ? jwt.getIssuedAt().toString() : "N/A",
            "cti", claimsExtractor.extractCti(jwt),
            "auth_req_id", claimsExtractor.extractAuthReqId(jwt),
            "scope", jwt.getClaimAsString("scope"),
            "tokenType", "CIBA-issued Bearer token"
        ));
    }

    @GetMapping("/cti-status")
    public ResponseEntity<?> ctiStatus(@AuthenticationPrincipal Jwt jwt) {
        try {
            tokenValidator.validate(jwt);
        } catch (CibaTokenValidationException e) {
            return ResponseEntity.status(401)
                .body(Map.of("error", e.getCode()));
        }

        String cti = claimsExtractor.extractCti(jwt);
        return ResponseEntity.ok(Map.of(
            "cti", cti,
            "isKnown", tokenValidator.hasScope(jwt, "calendar.read") // reusing hasScope as cti-known check
        ));
    }
}
