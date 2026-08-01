package com.ciba.client.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;
import org.springframework.validation.annotation.Validated;

@Data
@Component
@Validated
@ConfigurationProperties(prefix = "keycloak.ciba")
public class CibaProperties {
    /** Keycloak base URL (e.g., http://localhost:8181) */
    private String baseUrl = "http://localhost:8181";

    /** Keycloak realm name (e.g., ciba-realm) */
    private String realm = "ciba-realm";

    /** CIBA client ID */
    private String clientId = "ciba-agent";

    /** CIBA client secret */
    private String clientSecret = "ciba-agent-secret";

    /** poll | ping */
    private String mode = "poll";
    private int pollIntervalSeconds = 3;
    private int maxPollAttempts = 60;
    private String signingAlg = "PS256";
}
