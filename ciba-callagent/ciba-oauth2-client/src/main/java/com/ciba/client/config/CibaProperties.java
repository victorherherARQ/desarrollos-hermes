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
    /** poll | ping */
    private String mode = "poll";
    private int pollIntervalSeconds = 3;
    private int maxPollAttempts = 60;
    private String signingAlg = "PS256";
}
