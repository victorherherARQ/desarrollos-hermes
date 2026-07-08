package com.poc.api.security;

import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import java.time.Instant;
import java.util.Base64;
import java.util.Date;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * Tests de integración del Resource Server contra Keycloak real (KC 26.6.4).
 *
 * <p>Cubre la matriz de seguridad del endpoint {@code GET /api/calendar/events}:</p>
 * <ol>
 *   <li>(a) Sin Authorization → 401</li>
 *   <li>(b) JWT con firma inválida → 401</li>
 *   <li>(c) JWT válido (KC, RS256, aud=spring-boot-api, scope=calendar.read) → 200</li>
 *   <li>(d) JWT firmado con clave desconocida y aud NO contiene spring-boot-api → 401</li>
 * </ol>
 *
 * <p>Perfil {@code test}: usa {@code http://localhost:8180/realms/agent-poc} como
 * issuer-uri para que las pruebas en el host WSL puedan resolver Keycloak
 * (que publica el puerto 8180 al host).</p>
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureMockMvc
@Import(TestSecurityConfig.class)
@ActiveProfiles("test")
@DisplayName("CalendarController Security — KC 26 access_token")
class CalendarControllerSecurityTest {

    private static final String ANA_DNI = "12345678Z";
    private static final String ANA_DOB = "1990-05-15";

    @Autowired
    private MockMvc mockMvc;

    // ──────────────────────────────────────────────────────────────────
    // (a) Sin header Authorization → 401
    // ──────────────────────────────────────────────────────────────────
    @Test
    @DisplayName("(a) Sin Authorization header → 401 Unauthorized")
    void unauthenticated_request_is_rejected_with_401() throws Exception {
        mockMvc.perform(get("/api/calendar/events"))
                .andExpect(status().isUnauthorized());
    }

    // ──────────────────────────────────────────────────────────────────
    // (b) JWT con firma inválida → 401
    // ──────────────────────────────────────────────────────────────────
    @Test
    @DisplayName("(b) JWT con firma corrupta → 401 (firma no verifica contra KC)")
    void jwt_with_bad_signature_is_rejected_with_401() throws Exception {
        String validToken = obtainRealAnaAccessToken("calendar.read");

        String[] parts = validToken.split("\\.");
        assertThat(parts).hasSize(3);

        // Flip un byte del segmento de firma para invalidarlo.
        byte[] sigBytes = Base64.getUrlDecoder().decode(parts[2]);
        sigBytes[0] = (byte) (sigBytes[0] ^ 0x01);
        String mutatedSig = Base64.getUrlEncoder().withoutPadding().encodeToString(sigBytes);
        String tamperedToken = parts[0] + "." + parts[1] + "." + mutatedSig;
        assertThat(tamperedToken).isNotEqualTo(validToken);

        mockMvc.perform(get("/api/calendar/events")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + tamperedToken))
                .andExpect(status().isUnauthorized());
    }

    // ──────────────────────────────────────────────────────────────────
    // (c) JWT válido (KC, RS256, aud=spring-boot-api) → 200 + JSON
    // ──────────────────────────────────────────────────────────────────
    @Test
    @DisplayName("(c) JWT REAL de ana (aud=spring-boot-api, scope=calendar.read) → 200 + JSON")
    void valid_jwt_from_keycloak_is_accepted_and_returns_events_json() throws Exception {
        String token = obtainRealAnaAccessToken("calendar.read");

        mockMvc.perform(get("/api/calendar/events")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.user").value("ana"))
                .andExpect(jsonPath("$.events").isArray())
                .andExpect(jsonPath("$.agent_principal").value("agente-ia"))
                .andExpect(jsonPath("$.on_behalf_of").exists());
    }

    // ──────────────────────────────────────────────────────────────────
    // (d) JWT firmado localmente con aud=otro-api → 401 (audience validator)
    // ──────────────────────────────────────────────────────────────────
    @Test
    @DisplayName("(d) JWT firmado con clave propia y aud ≠ spring-boot-api → 401")
    void jwt_with_wrong_audience_is_rejected_with_401() throws Exception {
        // Generamos un JWT firmado con un RSA keypair LOCAL — kid desconocido
        // para KC. aud=['some-other-api'].
        //
        // Esto aísla el test del audience validator: la firma NO valida
        // contra KC (kid desconocido) y la aud NO contiene spring-boot-api.
        // El resultado final sigue siendo 401 (lo exigimos). La lógica
        // PURA del audience validator se cubre en JwtAudienceValidatorTest.
        RSAKey rsaKey = new RSAKeyGenerator(2048)
                .keyID("test-wrong-audience-" + UUID.randomUUID())
                .generate();

        Instant now = Instant.now();
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
                .issuer("http://agent-poc-keycloak:8080/realms/agent-poc")
                .subject(UUID.randomUUID().toString())
                .audience(List.of("some-other-api"))
                .issueTime(Date.from(now.minusSeconds(5)))
                .expirationTime(Date.from(now.plusSeconds(300)))
                .claim("scope", "calendar.read calendar.write email.send")
                .claim("azp", "agente-ia")
                .claim("preferred_username", "ana")
                .jwtID(UUID.randomUUID().toString())
                .build();

        SignedJWT signedJWT = new SignedJWT(
                new JWSHeader.Builder(JWSAlgorithm.RS256)
                        .type(JOSEObjectType.JWT)
                        .keyID(rsaKey.getKeyID())
                        .build(),
                claims
        );
        signedJWT.sign(new RSASSASigner(rsaKey.toPrivateKey()));
        String token = signedJWT.serialize();

        mockMvc.perform(get("/api/calendar/events")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
                .andExpect(status().isUnauthorized());
    }

    // ──────────────────────────────────────────────────────────────────
    // Helpers
    // ──────────────────────────────────────────────────────────────────

    /**
     * Llama al endpoint del agente PoC para obtener un access_token REAL
     * firmado por Keycloak en nombre del usuario ana.
     *
     * @param requestedScope scope solicitado al agente (e.g. "calendar.read")
     * @return access_token JWT firmado por KC (RS256, kid=kc-realm-key)
     */
    private String obtainRealAnaAccessToken(String requestedScope) {
        try {
            String body = "{\"user_id\":\"ana\",\"dni\":\"" + ANA_DNI + "\",\"dob\":\""
                    + ANA_DOB + "\",\"scope\":\"" + requestedScope + "\"}";

            java.net.http.HttpClient http = java.net.http.HttpClient.newBuilder()
                    .version(java.net.http.HttpClient.Version.HTTP_1_1)
                    .connectTimeout(java.time.Duration.ofSeconds(5))
                    .build();
            // 1) challenge
            java.net.http.HttpRequest req1 = java.net.http.HttpRequest.newBuilder()
                    .uri(java.net.URI.create("http://127.0.0.1:7000/agente/auth/identity"))
                    .header("Content-Type", "application/json")
                    .header("Accept", "application/json")
                    .timeout(java.time.Duration.ofSeconds(10))
                    .POST(java.net.http.HttpRequest.BodyPublishers.ofString(body))
                    .build();
            java.net.http.HttpResponse<String> r1 = http.send(req1,
                    java.net.http.HttpResponse.BodyHandlers.ofString());
            java.util.regex.Matcher m = java.util.regex.Pattern
                    .compile("\"challenge_id\"\\s*:\\s*\"([^\"]+)\"")
                    .matcher(r1.body());
            if (!m.find()) throw new IllegalStateException("no challenge_id in " + r1.body());
            String challengeId = m.group(1);

            // 2) push (simula aprobación biométrica)
            java.net.http.HttpRequest req2 = java.net.http.HttpRequest.newBuilder()
                    .uri(java.net.URI.create(
                            "http://127.0.0.1:7000/agente/auth/identity/push/" + challengeId + "?biometric=true"))
                    .timeout(java.time.Duration.ofSeconds(10))
                    .POST(java.net.http.HttpRequest.BodyPublishers.noBody())
                    .build();
            http.send(req2, java.net.http.HttpResponse.BodyHandlers.ofString());

            // 3) poll → access_token
            java.net.http.HttpRequest req3 = java.net.http.HttpRequest.newBuilder()
                    .uri(java.net.URI.create(
                            "http://127.0.0.1:7000/agente/auth/identity/poll?challenge_id="
                                    + challengeId + "&biometric_used=true"))
                    .timeout(java.time.Duration.ofSeconds(10))
                    .POST(java.net.http.HttpRequest.BodyPublishers.noBody())
                    .build();
            java.net.http.HttpResponse<String> r3 = http.send(req3,
                    java.net.http.HttpResponse.BodyHandlers.ofString());
            java.util.regex.Matcher mtok = java.util.regex.Pattern
                    .compile("\"access_token\"\\s*:\\s*\"([^\"]+)\"")
                    .matcher(r3.body());
            if (!mtok.find()) throw new IllegalStateException("no access_token in " + r3.body());
            return mtok.group(1);
        } catch (Exception e) {
            throw new RuntimeException("obtainRealAnaAccessToken failed", e);
        }
    }
}
