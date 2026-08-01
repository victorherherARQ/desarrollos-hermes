package com.ciba.api;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * CIBA CallAgent — AI Agent acting on behalf of a user via OpenID Connect CIBA.
 *
 * This Spring Boot application runs in TWO modes:
 *
 *  ┌──────────────────────────────────────────────────────────────┐
 *  │  CIBA CLIENT MODE (port 8080)                                │
 *  │  Exposes: POST /ciba/auth-request                            │
 *  │  Initiates CIBA flow: POST → Keycloak → push to user phone  │
 *  │  Polls for result until user approves/denies                 │
 *  └──────────────────────────────────────────────────────────────┘
 *
 *  ┌──────────────────────────────────────────────────────────────┐
 *  │  RESOURCE SERVER MODE (port 8080, same process)              │
 *  │  Exposes: GET /api/calendar, /api/email, /api/profile        │
 *  │  Validates CIBA tokens: JWT sig + cti replay + scope        │
 *  └──────────────────────────────────────────────────────────────┘
 */
@SpringBootApplication
@EnableAsync
@EnableScheduling
public class CibaCallAgentApplication {

    public static void main(String[] args) {
        SpringApplication.run(CibaCallAgentApplication.class, args);
    }
}
