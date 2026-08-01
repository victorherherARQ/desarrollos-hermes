package com.ciba.api.controller;

import com.ciba.api.security.CibaTokenValidator;
import com.ciba.api.security.CibaTokenValidator.CibaTokenValidationException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * Email API — protected resource server endpoints.
 * Requires a valid CIBA-issued JWT access_token.
 */
@RestController
@RequestMapping("/api/email")
@RequiredArgsConstructor
@Slf4j
public class EmailController {

    private final CibaTokenValidator tokenValidator;

    /**
     * GET /api/email/messages
     * Returns recent email messages for the authenticated user.
     */
    @GetMapping("/messages")
    public ResponseEntity<?> getMessages(
            @RequestHeader("Authorization") String authHeader,
            @RequestParam(value = "folder", defaultValue = "INBOX") String folder,
            @RequestParam(value = "limit", defaultValue = "20") int limit,
            @RequestParam(value = "unread", required = false) Boolean unreadOnly) {

        try {
            String token = extractToken(authHeader);
            var jwt = tokenValidator.validate(token);
            log.info("Email access: user={}, folder={}", jwt.getSubject(), folder);
            return ResponseEntity.ok(buildMessagesResponse(jwt.getSubject(), folder, limit, unreadOnly));
        } catch (CibaTokenValidationException e) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .body(Map.of("error", "invalid_token", "detail", e.getMessage()));
        }
    }

    /**
     * GET /api/email/messages/{messageId}
     */
    @GetMapping("/messages/{messageId}")
    public ResponseEntity<?> getMessage(
            @RequestHeader("Authorization") String authHeader,
            @PathVariable String messageId) {
        try {
            String token = extractToken(authHeader);
            var jwt = tokenValidator.validate(token);
            return ResponseEntity.ok(buildMessageResponse(messageId, jwt.getSubject()));
        } catch (CibaTokenValidationException e) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .body(Map.of("error", "invalid_token"));
        }
    }

    /**
     * GET /api/email/folders
     */
    @GetMapping("/folders")
    public ResponseEntity<?> getFolders(@RequestHeader("Authorization") String authHeader) {
        try {
            String token = extractToken(authHeader);
            var jwt = tokenValidator.validate(token);
            return ResponseEntity.ok(Map.of("folders", List.of(
                    Map.of("id", "INBOX", "name", "Inbox", "unread", 3),
                    Map.of("id", "SENT", "name", "Sent", "unread", 0),
                    Map.of("id", "DRAFT", "name", "Drafts", "unread", 0),
                    Map.of("id", "TRASH", "name", "Trash", "unread", 0)
            )));
        } catch (CibaTokenValidationException e) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                    .body(Map.of("error", "invalid_token"));
        }
    }

    private String extractToken(String authHeader) {
        if (authHeader == null || !authHeader.startsWith("Bearer "))
            throw new IllegalArgumentException("Missing Authorization header");
        return authHeader.substring(7);
    }

    private Map<String, Object> buildMessagesResponse(String userId, String folder, int limit, Boolean unreadOnly) {
        return Map.of(
                "user_id", userId, "folder", folder,
                "messages", List.of(
                        Map.of("id", "msg1", "from", "hr@company.com", "subject",
                                "Welcome to the team!", "date", "2026-08-01T08:00:00Z",
                                "unread", true, "snippet", "We're excited to have you..."),
                        Map.of("id", "msg2", "from", "noreply@github.com", "subject",
                                "[GitHub] PR merged", "date", "2026-07-31T15:30:00Z",
                                "unread", false, "snippet", "The PR #42 has been merged")
                ),
                "total", 2, "limit", limit,
                "_note", "Mock data — integrate with Gmail API or Microsoft Graph"
        );
    }

    private Map<String, Object> buildMessageResponse(String messageId, String userId) {
        return Map.of(
                "id", messageId, "from", "sender@example.com",
                "to", List.of(userId), "subject", "Sample Subject",
                "date", "2026-08-01T10:00:00Z",
                "body_text", "This is a mock email body.",
                "body_html", "<p>This is a <strong>mock</strong> email body.</p>",
                "attachments", List.of()
        );
    }
}
