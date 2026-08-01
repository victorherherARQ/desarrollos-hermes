package com.ciba.client.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.*;

public class CibaClientDtos {

    // ==== Incoming: POST /agent/request ====
    @Data @Builder @NoArgsConstructor @AllArgsConstructor
    public static class AgentRequest {
        private String userId;          // Keycloak username/email
        private String action;          // read_calendar | read_emails | get_profile | token_info
        @JsonInclude(JsonInclude.Include.NON_NULL)
        private java.util.Map<String, Object> params;
    }

    // ==== Outgoing: 202 Accepted — CIBA request initiated ====
    @Data @Builder @NoArgsConstructor @AllArgsConstructor
    public static class AgentRequestResponse {
        private String requestId;       // local UUID for Hermes to track
        private String authReqId;       // Keycloak's auth_req_id
        private String bindingMessage;  // what user sees on their phone
        private String mode;            // "poll"
        private String statusUrl;       // /agent/status/{requestId}
        private int expiresIn;          // seconds until CIBA request expires
        private java.time.Instant createdAt;
    }

    // ==== Outgoing: GET /agent/status/{id} ====
    @Data @Builder @NoArgsConstructor @AllArgsConstructor
    public static class StatusResponse {
        private String requestId;
        private String status;          // INITIATED | PENDING | APPROVED | DENIED | EXPIRED | COMPLETED
        private String userId;
        private String action;
        private String bindingMessage;
        @JsonInclude(JsonInclude.Include.NON_NULL)
        private String accessToken;     // only set when APPROVED
        private int expiresIn;
    }

    // ==== Outgoing: POST /agent/execute/{id} ====
    @Data @Builder @NoArgsConstructor @AllArgsConstructor
    public static class ExecuteResponse {
        private boolean success;
        private String requestId;
        private String userId;
        private String action;
        @JsonInclude(JsonInclude.Include.NON_NULL)
        private Object data;            // resource data or error detail
        @JsonInclude(JsonInclude.Include.NON_NULL)
        private String error;
        private java.time.Instant executedAt;
    }

    // ==== Outgoing: Generic error ====
    @Data @Builder @NoArgsConstructor @AllArgsConstructor
    public static class ErrorResponse {
        private String error;
        private String detail;
        private java.time.Instant timestamp;
    }

    // ==== Internal: polling result from Keycloak ====
    public record CibaTokenResult(
        String accessToken,
        String idToken,
        String tokenType,
        int expiresIn,
        String scope
    ) {}
}
