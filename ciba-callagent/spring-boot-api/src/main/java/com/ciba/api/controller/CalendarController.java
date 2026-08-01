package com.ciba.api.controller;

import com.ciba.api.security.CibaTokenValidator;
import com.ciba.api.security.CibaTokenValidator.CibaTokenValidationException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;

import java.util.*;

/**
 * Calendar API — protected resource server endpoints.
 * Requires a valid CIBA-issued JWT access_token in Authorization header.
 */
@RestController
@RequestMapping("/api/calendar")
@RequiredArgsConstructor
@Slf4j
public class CalendarController {

    private final CibaTokenValidator tokenValidator;

    /**
     * GET /api/calendar/events
     * Returns calendar events for the authenticated user.
     * Validates CIBA token: cti replay check, scope, audience.
     */
    @GetMapping("/events")
    public ResponseEntity<?> getEvents(
            @RequestHeader("Authorization") String authHeader,
            @RequestParam(value = "from", required = false) String from,
            @RequestParam(value = "to", required = false) String to,
            @RequestParam(value = "limit", defaultValue = "50") int limit) {

        try {
            String token = extractToken(authHeader);
            Jwt jwt = tokenValidator.validate(token);
            String userId = jwt.getSubject();
            log.info("Calendar access: user={}, scopes={}", userId, jwt.getClaimAsString("scope"));
            return ResponseEntity.ok(buildCalendarResponse(userId, from, to, limit));
        } catch (CibaTokenValidationException e) {
            log.warn("Token validation failed: {}", e.getMessage());
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .body(Map.of("error", "invalid_token", "detail", e.getMessage()));
        }
    }

    /**
     * GET /api/calendar/events/{eventId}
     */
    @GetMapping("/events/{eventId}")
    public ResponseEntity<?> getEvent(
            @RequestHeader("Authorization") String authHeader,
            @PathVariable String eventId) {
        try {
            String token = extractToken(authHeader);
            Jwt jwt = tokenValidator.validate(token);
            return ResponseEntity.ok(buildEventResponse(eventId, jwt.getSubject()));
        } catch (CibaTokenValidationException e) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .body(Map.of("error", "invalid_token", "detail", e.getMessage()));
        }
    }

    /**
     * GET /api/calendar/calendars
     * List all calendars accessible to the user.
     */
    @GetMapping("/calendars")
    public ResponseEntity<?> getCalendars(
            @RequestHeader("Authorization") String authHeader) {
        try {
            String token = extractToken(authHeader);
            Jwt jwt = tokenValidator.validate(token);
            return ResponseEntity.ok(buildCalendarsResponse(jwt.getSubject()));
        } catch (CibaTokenValidationException e) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .body(Map.of("error", "invalid_token"));
        }
    }

    private String extractToken(String authHeader) {
        if (authHeader == null || !authHeader.startsWith("Bearer ")) {
            throw new IllegalArgumentException("Missing or malformed Authorization header");
        }
        return authHeader.substring(7);
    }

    private Map<String, Object> buildCalendarResponse(String userId, String from, String to, int limit) {
        return Map.of(
                "user_id", userId,
                "events", List.of(
                        Map.of("id", "evt1", "title", "Team Standup", "start", "2026-08-03T09:00:00Z",
                                "end", "2026-08-03T09:30:00Z", "attendees", List.of("alice","bob")),
                        Map.of("id", "evt2", "title", "Q3 Planning", "start", "2026-08-05T14:00:00Z",
                                "end", "2026-08-05T16:00:00Z", "attendees", List.of("charlie"))
                ),
                "total", 2, "limit", limit,
                "_note", "This is mock data — replace with Google Calendar / Microsoft Graph API calls"
        );
    }

    private Map<String, Object> buildEventResponse(String eventId, String userId) {
        return Map.of(
                "id", eventId, "title", "Sample Event",
                "start", "2026-08-03T09:00:00Z", "end", "2026-08-03T10:00:00Z",
                "organizer", userId, "attendees", List.of("alice","bob"),
                "location", "Room 101",
                "_note", "Mock data"
        );
    }

    private Map<String, Object> buildCalendarsResponse(String userId) {
        return Map.of(
                "calendars", List.of(
                        Map.of("id", "primary", "name", "Primary Calendar", "color", "#4285F4"),
                        Map.of("id", "work", "name", "Work", "color", "#EA4335"),
                        Map.of("id", "personal", "name", "Personal", "color", "#34A853")
                )
        );
    }
}
