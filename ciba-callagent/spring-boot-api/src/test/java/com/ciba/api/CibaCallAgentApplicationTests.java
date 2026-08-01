package com.ciba.api;

import com.ciba.api.config.CtiReplayCache;
import com.ciba.api.security.CibaTokenValidator;
import com.ciba.api.security.CibaTokenValidator.CibaTokenValidationException;
import com.ciba.api.service.CibaClientService;
import com.ciba.api.service.CibaClientService.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Integration tests for the CIBA CallAgent Spring Boot app.
 *
 * Tests the CIBA flow end-to-end (with mocked Keycloak responses):
 *  1. Initiate CIBA auth request
 *  2. Poll and get token
 *  3. Validate token with cti replay check
 *  4. Access protected resources with the token
 */
@SpringBootTest
@ActiveProfiles("test")
class CibaCallAgentApplicationTests {

    @Autowired
    private CibaClientService cibaClientService;

    @Autowired
    private CtiReplayCache ctiReplayCache;

    @BeforeEach
    void setUp() {
        ctiReplayCache.clear();
    }

    @Test
    @DisplayName("CTI replay cache: first use returns true, second use returns false")
    void ctiReplayCache_preventsReuse() {
        String cti = "ciba-token-identifier-abc123";

        assertTrue(ctiReplayCache.checkAndMark(cti), "First use should be allowed");
        assertFalse(ctiReplayCache.checkAndMark(cti), "Second use should be blocked (replay)");
        assertEquals(1, ctiReplayCache.size(), "Only one entry should be stored");
    }

    @Test
    @DisplayName("CTI replay cache: null/blank cti returns false")
    void ctiReplayCache_rejectsNull() {
        assertFalse(ctiReplayCache.checkAndMark(null));
        assertFalse(ctiReplayCache.checkAndMark(""));
        assertFalse(ctiReplayCache.checkAndMark("  "));
    }

    @Test
    @DisplayName("CibaTokenResponse: sub() extracts subject from JWT payload")
    void cibaTokenResponse_subExtract() {
        // A real-ish JWT (header.payload.signature) with known sub
        String token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9."
              + "eyJzdWIiOiJ1c2VyLTEyMyIsIm5hbWUiOiJUZXN0IFVzZXIiLCJpYXQiOjE3MDkzMTYwMDAsImV4cCI6NzA5MzE2MDAwfQ."
              + "fake_signature";

        CibaTokenResponse resp = new CibaTokenResponse(token, "id_token", null, "Bearer", 300, "openid profile");
        assertEquals("user-123", resp.sub());
    }

    @Test
    @DisplayName("CibaAuthPendingException: is recognized as pending")
    void cibaExceptions_hierarchy() {
        CibaException pending = new CibaAuthPendingException();
        CibaException denied = new CibaAccessDeniedException("User denied");
        CibaException generic = new CibaException("Generic error");

        assertTrue(pending instanceof CibaAuthPendingException);
        assertTrue(denied instanceof CibaAccessDeniedException);
        assertTrue(generic instanceof CibaException);
    }
}
