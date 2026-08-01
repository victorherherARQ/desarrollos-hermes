package com.ciba.resource.controller;

import com.ciba.resource.security.CibaTokenValidator;
import com.ciba.resource.security.CibaTokenValidator.CibaTokenValidationException;
import com.ciba.resource.security.JwtClaimsExtractor;
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
 * Scopes:
 *   - calendar.read  → list events, get event
 *   - calendar.write → create event, update event
 */
@RestController
@RequestMapping("/api/calendar")
@RequiredArgsConstructor
@Slf4j
public class CalendarController {

    private final CibaTokenValidator tokenValidator;
    private final JwtClaimsExtractor claimsExtractor;

    // ── calendar.read ────────────────────────────────────────────────────

    @GetMapping("/events")
    public ResponseEntity<?> listEvents(@AuthenticationPrincipal Jwt jwt) {
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
        String cti = claimsExtractor.extractCti(jwt);
        log.info("Calendar list: user={}, cti={}", userId, cti);

        List<Map<String, Object>> events = List.of(
            Map.of(
                "id", "evt-001",
                "summary", "Sprint Planning",
                "start", "2026-08-03T09:00:00Z",
                "end", "2026-08-03T10:30:00Z",
                "location", "Zoom",
                "attendees", List.of("alice@example.com", "bob@example.com"),
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
            "cti", cti != null ? cti : "N/A",
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
            "cti", claimsExtractor.extractCti(jwt),
            "scope", "calendar.read"
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

    // ── calendar.write ───────────────────────────────────────────────────

    @PostMapping("/events")
    public ResponseEntity<?> createEvent(
            @RequestBody Map<String, Object> body,
            @AuthenticationPrincipal Jwt jwt) {

        try {
            tokenValidator.validate(jwt);
        } catch (CibaTokenValidationException e) {
            return ResponseEntity.status(401)
                .body(Map.of("error", e.getCode(), "detail", e.getMessage()));
        }

        if (!tokenValidator.hasScope(jwt, "calendar.write")) {
            return ResponseEntity.status(403)
                .body(Map.of("error", "insufficient_scope", "required", "calendar.write"));
        }

        String userId = jwt.getSubject();
        String eventId = "evt-" + UUID.randomUUID().toString().substring(0, 8);

        log.info("Calendar create: user={}, summary={}, cti={}",
            userId, body.get("summary"), claimsExtractor.extractCti(jwt));

        Map<String, Object> created = new HashMap<>();
        created.put("id", eventId);
        created.put("summary", body.getOrDefault("summary", "Untitled"));
        created.put("start", body.getOrDefault("start", Instant.now().toString()));
        created.put("end", body.getOrDefault("end", Instant.now().plusSeconds(3600).toString()));
        created.put("location", body.getOrDefault("location", ""));
        created.put("description", body.getOrDefault("description", ""));
        created.put("allDay", body.getOrDefault("allDay", false));
        created.put("organizer", userId);
        created.put("createdBy", "ciba-agent");
        created.put("cti", claimsExtractor.extractCti(jwt));
        created.put("_note", "Mock — integrate with Google Calendar API in production");

        return ResponseEntity.status(201).body(Map.of(
            "action", "calendar.create",
            "scope", "calendar.write",
            "event", created
        ));
    }

    @PutMapping("/events/{eventId}")
    public ResponseEntity<?> updateEvent(
            @PathVariable String eventId,
            @RequestBody Map<String, Object> body,
            @AuthenticationPrincipal Jwt jwt) {

        try {
            tokenValidator.validate(jwt);
        } catch (CibaTokenValidationException e) {
            return ResponseEntity.status(401)
                .body(Map.of("error", e.getCode()));
        }

        if (!tokenValidator.hasScope(jwt, "calendar.write")) {
            return ResponseEntity.status(403)
                .body(Map.of("error", "insufficient_scope", "required", "calendar.write"));
        }

        log.info("Calendar update: eventId={}, user={}, cti={}",
            eventId, jwt.getSubject(), claimsExtractor.extractCti(jwt));

        Map<String, Object> updated = new HashMap<>();
        updated.put("id", eventId);
        updated.put("summary", body.getOrDefault("summary", "Updated event"));
        updated.put("start", body.getOrDefault("start", ""));
        updated.put("end", body.getOrDefault("end", ""));
        updated.put("location", body.getOrDefault("location", ""));
        updated.put("description", body.getOrDefault("description", ""));
        updated.put("allDay", body.getOrDefault("allDay", false));
        updated.put("updatedBy", "ciba-agent");
        updated.put("cti", claimsExtractor.extractCti(jwt));
        updated.put("_note", "Mock — integrate with Google Calendar API in production");

        return ResponseEntity.ok(Map.of(
            "action", "calendar.update",
            "scope", "calendar.write",
            "event", updated
        ));
    }

    @DeleteMapping("/events/{eventId}")
    public ResponseEntity<?> deleteEvent(
            @PathVariable String eventId,
            @AuthenticationPrincipal Jwt jwt) {

        try {
            tokenValidator.validate(jwt);
        } catch (CibaTokenValidationException e) {
            return ResponseEntity.status(401)
                .body(Map.of("error", e.getCode()));
        }

        if (!tokenValidator.hasScope(jwt, "calendar.write")) {
            return ResponseEntity.status(403)
                .body(Map.of("error", "insufficient_scope", "required", "calendar.write"));
        }

        log.info("Calendar delete: eventId={}, user={}, cti={}",
            eventId, jwt.getSubject(), claimsExtractor.extractCti(jwt));

        return ResponseEntity.ok(Map.of(
            "action", "calendar.delete",
            "scope", "calendar.write",
            "eventId", eventId,
            "deleted", true,
            "cti", claimsExtractor.extractCti(jwt)
        ));
    }
}
