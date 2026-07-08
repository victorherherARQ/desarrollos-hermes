package com.poc.api.controller;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * Endpoint protegido por el scope {@code calendar.read}.
 * En este PoC el scope viene en el JWT claim `scope`, mapeado por
 * {@link com.poc.api.config.SecurityConfig.ScopeAuthoritiesConverter} a
 * {@code SCOPE_calendar.read}.
 */
@RestController
@RequestMapping("/api/calendar")
public class CalendarController {

    private static final Logger log = LoggerFactory.getLogger(CalendarController.class);

    @GetMapping("/events")
    @PreAuthorize("hasAuthority('SCOPE_calendar.read')")
    public Map<String, Object> events(
            @RequestParam(name = "user_id", defaultValue = "ana") String userId,
            @AuthenticationPrincipal Jwt jwt
    ) {
        log.info("calendar.events | sub={} | aud={} | scope_claim={}",
                jwt.getSubject(),
                jwt.getAudience(),
                jwt.getClaim("scope"));

        return Map.of(
                "user", userId,
                "events", List.of(
                        Map.of(
                                "id", "evt1",
                                "title", "Reunión con el equipo",
                                "when", "2026-07-08T10:00:00Z"
                        ),
                        Map.of(
                                "id", "evt2",
                                "title", "Demo OAuth PoC a Víctor",
                                "when", "2026-07-08T16:00:00Z"
                        )
                ),
                "served_at", Instant.now().toString(),
                "agent_principal", jwt.getClaimAsString("azp"),
                "on_behalf_of", jwt.getSubject()
        );
    }
}
