package com.poc.api.controller;

import com.fasterxml.jackson.annotation.JsonProperty;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.Map;
import java.util.Objects;

/**
 * Endpoint protegido por el scope {@code email.send}.
 *
 * <p>Aquí se evidencia la cadena de delegación:
 * <pre>
 *   sub = usuario real (ana)
 *   azp = cliente agente-ia
 * </pre>
 * </p>
 */
@RestController
@RequestMapping("/api/email")
public class EmailController {

    private static final Logger log = LoggerFactory.getLogger(EmailController.class);

    @PostMapping("/send")
    @PreAuthorize("hasAuthority('SCOPE_email.send')")
    public Map<String, Object> send(
            @RequestBody EmailRequest body,
            @AuthenticationPrincipal Jwt jwt
    ) {
        Objects.requireNonNull(body, "body is required");
        String sub = jwt.getSubject();             // usuario real
        String azp = jwt.getClaimAsString("azp");  // cliente agente-ia

        log.info("email.send | to={} | subject={} | on_behalf_of(sub)={} | by(azp)={}",
                body.to(), body.subject(), sub, azp);

        return Map.of(
                "status", "sent",
                "to", body.to(),
                "subject", body.subject(),
                "logged_at", Instant.now().toString(),
                "on_behalf_of", sub,
                "by", azp,
                "agent_client_id", azp
        );
    }

    public static class EmailRequest {
        @JsonProperty("to")
        private String to;

        @JsonProperty("subject")
        private String subject;

        @JsonProperty("body")
        private String body;

        public String to()        { return to; }
        public String subject()   { return subject; }
        public String body()      { return body; }

        public void setTo(String to)               { this.to = to; }
        public void setSubject(String subject)     { this.subject = subject; }
        public void setBody(String body)           { this.body = body; }
    }
}
