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
 * Email API — protected by CIBA JWT.
 *
 * Scopes:
 *   - (no scope required) → list inbox, read message, list folders
 *   - email.send  → send email
 *   - email.modify → modify labels/folders
 */
@RestController
@RequestMapping("/api/email")
@RequiredArgsConstructor
@Slf4j
public class EmailController {

    private final CibaTokenValidator tokenValidator;
    private final JwtClaimsExtractor claimsExtractor;

    // ── Read (no specific scope beyond openid/profile/email) ─────────────

    @GetMapping("/inbox")
    public ResponseEntity<?> listInbox(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam(defaultValue = "20") int limit,
            @RequestParam(defaultValue = "0") int offset) {

        try {
            tokenValidator.validate(jwt);
        } catch (CibaTokenValidationException e) {
            return ResponseEntity.status(401)
                .body(Map.of("error", e.getCode(), "detail", e.getMessage()));
        }

        String userId = claimsExtractor.extractUserInfo(jwt).sub();
        String cti = claimsExtractor.extractCti(jwt);
        log.info("Email inbox: user={}, cti={}", userId, cti);

        // Mock data — in production, call Gmail API / Microsoft Graph
        List<Map<String, Object>> messages = List.of(
            Map.of(
                "id", "msg-001",
                "from", "hr@company.com",
                "subject", "Welcome to the team!",
                "snippet", "Dear colleague, welcome...",
                "date", "2026-08-01T08:00:00Z",
                "unread", true,
                "labels", List.of("INBOX", "IMPORTANT")
            ),
            Map.of(
                "id", "msg-002",
                "from", "github@noreply.github.com",
                "subject", "[repo] PR #42 merged",
                "snippet", "The PR has been successfully merged...",
                "date", "2026-07-31T15:30:00Z",
                "unread", false,
                "labels", List.of("INBOX")
            ),
            Map.of(
                "id", "msg-003",
                "from", "calendar@company.com",
                "subject", "Reminder: Sprint Planning in 1 hour",
                "snippet", "This is a reminder...",
                "date", "2026-08-03T07:00:00Z",
                "unread", true,
                "labels", List.of("INBOX", "Calendar")
            )
        );

        int fromIndex = Math.min(offset, messages.size());
        int toIndex = Math.min(offset + limit, messages.size());
        List<Map<String, Object>> page = messages.subList(fromIndex, toIndex);

        return ResponseEntity.ok(Map.of(
            "user", userId,
            "cti", cti != null ? cti : "N/A",
            "folder", "INBOX",
            "total", messages.size(),
            "offset", offset,
            "limit", limit,
            "messages", page,
            "_note", "Mock data — integrate with Gmail API in production"
        ));
    }

    @GetMapping("/message/{messageId}")
    public ResponseEntity<?> getMessage(
            @PathVariable String messageId,
            @AuthenticationPrincipal Jwt jwt) {

        try {
            tokenValidator.validate(jwt);
        } catch (CibaTokenValidationException e) {
            return ResponseEntity.status(401)
                .body(Map.of("error", e.getCode()));
        }

        String userId = claimsExtractor.extractUserInfo(jwt).sub();
        return ResponseEntity.ok(Map.of(
            "id", messageId,
            "from", "sender@example.com",
            "to", List.of(userId),
            "subject", "Email " + messageId,
            "body", "This is a mock email body.\n\nReplace with Gmail API in production.",
            "date", Instant.now().toString(),
            "user", userId,
            "cti", claimsExtractor.extractCti(jwt),
            "labels", List.of("INBOX")
        ));
    }

    @GetMapping("/folders")
    public ResponseEntity<?> listFolders(@AuthenticationPrincipal Jwt jwt) {
        try {
            tokenValidator.validate(jwt);
        } catch (CibaTokenValidationException e) {
            return ResponseEntity.status(401)
                .body(Map.of("error", e.getCode()));
        }

        return ResponseEntity.ok(Map.of(
            "user", jwt.getSubject(),
            "folders", List.of(
                Map.of("id", "INBOX",  "name", "Inbox",    "unread", 2, "total", 47),
                Map.of("id", "SENT",   "name", "Sent",     "unread", 0, "total", 12),
                Map.of("id", "DRAFT",  "name", "Drafts",   "unread", 0, "total", 3),
                Map.of("id", "TRASH",  "name", "Trash",    "unread", 0, "total", 8),
                Map.of("id", "SPAM",   "name", "Spam",     "unread", 1, "total", 5)
            )
        ));
    }

    // ── email.send ───────────────────────────────────────────────────────

    @PostMapping("/send")
    public ResponseEntity<?> sendEmail(
            @RequestBody Map<String, Object> body,
            @AuthenticationPrincipal Jwt jwt) {

        try {
            tokenValidator.validate(jwt);
        } catch (CibaTokenValidationException e) {
            return ResponseEntity.status(401)
                .body(Map.of("error", e.getCode(), "detail", e.getMessage()));
        }

        if (!tokenValidator.hasScope(jwt, "email.send")) {
            return ResponseEntity.status(403)
                .body(Map.of("error", "insufficient_scope", "required", "email.send"));
        }

        String userId = jwt.getSubject();
        String to = (String) body.getOrDefault("to", "");
        String subject = (String) body.getOrDefault("subject", "");
        String bodyText = (String) body.getOrDefault("body", "");
        String cti = claimsExtractor.extractCti(jwt);

        log.info("Email send: from={}, to={}, subject={}, cti={}", userId, to, subject, cti);

        if (to == null || to.isBlank()) {
            return ResponseEntity.badRequest()
                .body(Map.of("error", "MISSING_FIELD", "field", "to"));
        }

        return ResponseEntity.status(201).body(Map.of(
            "action", "email.send",
            "scope", "email.send",
            "messageId", "sent-" + UUID.randomUUID().toString().substring(0, 8),
            "from", userId,
            "to", to,
            "subject", subject,
            "sentAt", Instant.now().toString(),
            "cti", cti != null ? cti : "N/A",
            "_note", "Mock — integrate with Gmail API / SendGrid / SMTP in production"
        ));
    }

    // ── email.modify ────────────────────────────────────────────────────

    @PatchMapping("/message/{messageId}/labels")
    public ResponseEntity<?> modifyLabels(
            @PathVariable String messageId,
            @RequestBody Map<String, Object> body,
            @AuthenticationPrincipal Jwt jwt) {

        try {
            tokenValidator.validate(jwt);
        } catch (CibaTokenValidationException e) {
            return ResponseEntity.status(401)
                .body(Map.of("error", e.getCode()));
        }

        if (!tokenValidator.hasScope(jwt, "email.modify")) {
            return ResponseEntity.status(403)
                .body(Map.of("error", "insufficient_scope", "required", "email.modify"));
        }

        @SuppressWarnings("unchecked")
        List<String> labels = (List<String>) body.getOrDefault("labels", List.of());

        log.info("Email modify labels: messageId={}, labels={}, user={}, cti={}",
            messageId, labels, jwt.getSubject(), claimsExtractor.extractCti(jwt));

        return ResponseEntity.ok(Map.of(
            "action", "email.modify",
            "scope", "email.modify",
            "messageId", messageId,
            "labels", labels,
            "modifiedAt", Instant.now().toString(),
            "cti", claimsExtractor.extractCti(jwt),
            "_note", "Mock — integrate with Gmail API in production"
        ));
    }

    @PostMapping("/message/{messageId}/archive")
    public ResponseEntity<?> archiveMessage(
            @PathVariable String messageId,
            @AuthenticationPrincipal Jwt jwt) {

        try {
            tokenValidator.validate(jwt);
        } catch (CibaTokenValidationException e) {
            return ResponseEntity.status(401)
                .body(Map.of("error", e.getCode()));
        }

        if (!tokenValidator.hasScope(jwt, "email.modify")) {
            return ResponseEntity.status(403)
                .body(Map.of("error", "insufficient_scope", "required", "email.modify"));
        }

        log.info("Email archive: messageId={}, user={}, cti={}",
            messageId, jwt.getSubject(), claimsExtractor.extractCti(jwt));

        return ResponseEntity.ok(Map.of(
            "action", "email.modify",
            "scope", "email.modify",
            "messageId", messageId,
            "archived", true,
            "cti", claimsExtractor.extractCti(jwt)
        ));
    }

    @DeleteMapping("/message/{messageId}")
    public ResponseEntity<?> deleteMessage(
            @PathVariable String messageId,
            @AuthenticationPrincipal Jwt jwt) {

        try {
            tokenValidator.validate(jwt);
        } catch (CibaTokenValidationException e) {
            return ResponseEntity.status(401)
                .body(Map.of("error", e.getCode()));
        }

        if (!tokenValidator.hasScope(jwt, "email.modify")) {
            return ResponseEntity.status(403)
                .body(Map.of("error", "insufficient_scope", "required", "email.modify"));
        }

        log.info("Email delete: messageId={}, user={}, cti={}",
            messageId, jwt.getSubject(), claimsExtractor.extractCti(jwt));

        return ResponseEntity.ok(Map.of(
            "action", "email.modify",
            "scope", "email.modify",
            "messageId", messageId,
            "deleted", true,
            "cti", claimsExtractor.extractCti(jwt)
        ));
    }
}
