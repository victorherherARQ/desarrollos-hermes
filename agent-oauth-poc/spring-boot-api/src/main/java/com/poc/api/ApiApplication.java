package com.poc.api;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Apigee-stub: API Spring Boot que actúa como Resource Server validando
 * JWTs emitidos por Keycloak (realm "agent-poc") para reemplazar a Apigee
 * en este PoC de OAuth/OIDC + agente IA.
 */
@SpringBootApplication
public class ApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(ApiApplication.class, args);
    }
}
