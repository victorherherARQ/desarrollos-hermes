package com.ciba.resource.controller;

import com.ciba.resource.security.CibaTokenValidator;
import com.ciba.resource.security.CibaTokenValidator.CibaTokenValidationException;
import com.ciba.resource.security.JwtClaimsExtractor;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.*;

/**
 * Calendar API — protected by CIBA JWT.
 * 
 * The token must have scope "calendar.read" and pass CTI replay validation.
 */
@RestController
@RequestMapping("/api/calendar")
@RequiredArgsConstructor
@Slf4j
public class CalendarController {

    private final CibaTokenValidator tokenValidator;
    private final JwtClaimsExtractor claimsExtractor;

    @GetMapping("/events")
    public ResponseEntity<?> listEvents(
            @AuthenticationPrincipal Jwt jwt,
            HttpServletRequest request) {

        try {
            tokenValidator.validate(jwt);
        } catch (CibaTokenValidationException e) {
            log.warn("Calendar access denied: {}", e.getMessage());
            return ResponseEntity.status(401)
                .body(Map.of("error", e.getCode(), "detail", e.getMessage()));
        }

        if (!tokenValidator.hasScope(jwt, "calendar.read")) {
            return ResponseEntity.status(403)
                .body(Map.of("error", "insufficient_scope", "required", "calendar.read"));
        }

        String userId = claimsExtractor.extractUserInfo(jwt).sub();
        String authReqId = claimsExtractor.extractAuthReqId(jwt);
        String cti = claimsExtractor.extractCti(jwt);

        log.info("Calendar access: user={}, auth_req_id={}, cti={}", userId, authReqId, cti);

        // Mock data — in production, call Google Calendar API / Microsoft Graph
        List<Map<String, Object>> events = List.of(
            Map.of(
                "id", "evt-001",
                "summary", "Sprint Planning",
                "start", "2026-08-03T09:00:00Z",
                "end", "2026-08-03T10:30:00Z",
                "location", "Zoom",
                "attendees", List.of("alice@example.com", "bob@example.com"),
                "organizer", "alice@example.com",
                "allDay", false
            ),
            Map.of(
                "id", "evt-002",
                "summary", "Team Standup",
                "start", "2026-08-03T08:30:00Z",
                "end", "2026-08-03T08:45:00Z",
                "allDay", false
            ),
            Map.of(
                "id", "evt-003",
                "summary", "Code Review",
                "start", "2026-08-04T14:00:00Z",
                "end", "2026-08-04T15:00:00Z",
                "allDay", false
            )
        );

        return ResponseEntity.ok(Map.of(
            "user", userId,
            "auth_req_id", authReqId != null ? authReqId : "N/A",
            "scope", "calendar.read",
            "count", events.size(),
            "events", events,
            "_note", "Mock data — integrate with Google Calendar API in production"
        ));
    }

    @GetMapping("/events/{eventId}")
    public ResponseEntity<?> getEvent(
            @PathVariable String eventId,
            @AuthenticationPrincipal Jwt jwt) {

        try {
            tokenValidator.validate(jwt);
        } catch (CibaTokenValidationException e) {
            return ResponseEntity.status(401)
                .body(Map.of("error", e.getCode(), "detail", e.getMessage()));
        }

        if (!tokenValidator.hasScope(jwt, "calendar.read")) {
            return ResponseEntity.status(403)
                .body(Map.of("error", "insufficient_scope", "required", "calendar.read"));
        }

        return ResponseEntity.ok(Map.of(
            "id", eventId,
            "summary", "Event " + eventId,
            "description", "Mock event for " + eventId,
            "user", jwt.getSubject(),
            "source", "ciba-resource-server"
        ));
    }

    @GetMapping("/calendars")
    public ResponseEntity<?> listCalendars(@AuthenticationPrincipal Jwt jwt) {
        try {
            tokenValidator.validate(jwt);
        } catch (CibaTokenValidationException e) {
            return ResponseEntity.status(401)
                .body(Map.of("error", e.getCode()));
        }

        return ResponseEntity.ok(Map.of(
            "user", jwt.getSubject(),
            "calendars", List.of(
                Map.of("id", "primary", "name", "Primary Calendar", "color", "#4285F4"),
                Map.of("id", "work", "name", "Work", "color", "#EA4335")
            )
        ));
    }
}
