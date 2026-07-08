package com.poc.api.security;

import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

import java.util.List;

/** Test-only: accepts tokens whose iss matches ANY of the given issuers. */
class TestJwtIssuerMultiValidator implements OAuth2TokenValidator<Jwt> {
    private final List<String> validIssuers;

    TestJwtIssuerMultiValidator(List<String> validIssuers) {
        this.validIssuers = validIssuers;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        String iss = jwt.getIssuer() == null ? null : jwt.getIssuer().toString();
        if (iss != null && validIssuers.contains(iss)) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_issuer",
                        "iss claim '" + iss + "' not in valid set: " + validIssuers,
                        "https://tools.ietf.org/html/rfc7519#section-4.1.1"));
    }
}
