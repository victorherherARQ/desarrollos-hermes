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

@RestController
@RequestMapping("/api/email")
@RequiredArgsConstructor
@Slf4j
public class EmailController {

    private final CibaTokenValidator tokenValidator;
    private final JwtClaimsExtractor claimsExtractor;

    @GetMapping("/inbox")
    public ResponseEntity<?> listInbox(
            @AuthenticationPrincipal Jwt jwt,
            @RequestParam(defaultValue = "20") int limit) {

        try {
            tokenValidator.validate(jwt);
        } catch (CibaTokenValidationException e) {
            return ResponseEntity.status(401)
                .body(Map.of("error", e.getCode(), "detail", e.getMessage()));
        }

        String userId = claimsExtractor.extractUserInfo(jwt).sub();

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

        return ResponseEntity.ok(Map.of(
            "user", userId,
            "folder", "INBOX",
            "total", messages.size(),
            "messages", messages.subList(0, Math.min(messages.size(), limit)),
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

        return ResponseEntity.ok(Map.of(
            "id", messageId,
            "from", "sender@example.com",
            "to", List.of(jwt.getSubject()),
            "subject", "Email " + messageId,
            "body", "This is a mock email body.",
            "date", Instant.now().toString(),
            "user", jwt.getSubject()
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
            "folders", List.of(
                Map.of("id", "INBOX", "name", "Inbox", "unread", 2),
                Map.of("id", "SENT", "name", "Sent", "unread", 0),
                Map.of("id", "DRAFT", "name", "Drafts", "unread", 0),
                Map.of("id", "TRASH", "name", "Trash", "unread", 0)
            )
        ));
    }
}
