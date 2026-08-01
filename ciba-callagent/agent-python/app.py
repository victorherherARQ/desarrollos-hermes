"""
CIBA CallAgent — Python FastAPI agent.

This is the AI agent (Hermes) that acts ON BEHALF OF a user.
It uses OpenID Connect CIBA to get the user's consent via push notification,
then uses the resulting access_token to call protected resources.

Flow:
  1. Receive request from user: "check my calendar for tomorrow"
  2. Initiate CIBA auth request via Spring Boot API
  3. User approves on their phone (Keycloak push)
  4. Receive tokens from Spring Boot
  5. Call /api/calendar/events with the CIBA access_token
  6. Return result to user
"""
from __future__ import annotations

import os
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Header, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s"
)
log = logging.getLogger("ciba-agent")

# ── Config from environment ───────────────────────────────────────────────────
KEYCLOAK_BASE_URL: str = os.getenv("KEYCLOAK_BASE_URL", "http://localhost:8180")
KEYCLOAK_REALM: str = os.getenv("KEYCLOAK_REALM", "ciba-realm")
CIBA_AGENT_URL: str = os.getenv("CIBA_AGENT_URL", "http://localhost:8080")
CIBA_CLIENT_ID: str = os.getenv("CIBA_CLIENT_ID", "ciba-agent")
CIBA_CLIENT_SECRET: str = os.getenv("CIBA_CLIENT_SECRET", "ciba-agent-secret")

# ── FastAPI app ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="CIBA CallAgent",
    description="AI Agent acting on behalf of a user via OpenID Connect CIBA",
    version="1.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory token store ──────────────────────────────────────────────────────
# In production, use Redis with TTL matching token expiry
_token_store: dict[str, dict] = {}


# ── Pydantic models ────────────────────────────────────────────────────────────
class AuthRequest(BaseModel):
    """Request for the agent to act on behalf of a user."""

    user_id: str  # email, username, or sub claim of the user
    action: str  # e.g. "read_calendar", "send_email", "get_profile"
    params: dict = {}  # action-specific parameters


class AuthResponse(BaseModel):
    """Response after initiating CIBA auth request."""

    request_id: str  # local tracking ID (maps to auth_req_id)
    auth_req_id: str  # Keycloak's auth_req_id
    binding_message: str  # what the user will see on their phone
    mode: str  # "poll" or "ping"
    poll_url: str  # URL to check status
    expires_in: int  # seconds until request expires


class TokenInfo(BaseModel):
    """Token information after user approval."""

    request_id: str
    user_id: str
    access_token: str
    id_token: str
    expires_in: int
    scope: str
    token_type: str = "Bearer"


class CalendarRequest(BaseModel):
    request_id: str
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    limit: int = 50


class ActionResult(BaseModel):
    success: bool
    action: str
    user_id: str
    data: dict | None = None
    error: str | None = None


# ── HTTP client ───────────────────────────────────────────────────────────────
http = httpx.Client(timeout=60.0)


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_binding_message(action: str) -> str:
    """Human-readable message shown to user on their phone."""
    messages = {
        "read_calendar": "Read your calendar",
        "send_email": "Send an email on your behalf",
        "get_profile": "Access your profile",
        "list_events": "List your upcoming events",
        "read_emails": "Read your recent emails",
    }
    return messages.get(action, f"Perform: {action}")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "UP", "service": "ciba-agent", "version": "1.0.0"}


@app.get("/")
async def root():
    return {
        "service": "CIBA CallAgent",
        "version": "1.0.0",
        "description": "AI agent acting on behalf of a user via OpenID Connect CIBA",
        "docs": "/docs",
    }


# ── 1. POST /auth/ciba-request ────────────────────────────────────────────────
# Agent initiates a CIBA auth request on behalf of the user.
#
# Body:
# {
#   "user_id": "testuser@example.com",
#   "action": "read_calendar",
#   "params": {}
# }
#
# Response (202 Accepted):
# {
#   "request_id": "req-uuid",
#   "auth_req_id": "AR-xxx",
#   "binding_message": "Read your calendar",
#   "mode": "poll",
#   "poll_url": "/auth/status/req-uuid",
#   "expires_in": 300
# }

@app.post("/auth/ciba-request", response_model=AuthResponse, status_code=status.HTTP_202_ACCEPTED)
async def ciba_auth_request(req: AuthRequest):
    log.info(f"CIBA request: user={req.user_id}, action={req.action}")

    binding_msg = get_binding_message(req.action)
    scope = _action_to_scope(req.action)

    try:
        # Tell Spring Boot to initiate CIBA flow with Keycloak
        resp = http.post(
            f"{CIBA_AGENT_URL}/ciba/auth-request",
            json={
                "loginHint": req.user_id,
                "bindingMessage": binding_msg,
                "scope": scope,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()

    except httpx.HTTPStatusError as e:
        log.error(f"Keycloak CIBA init failed: {e.response.text}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"CIBA initiation failed: {e.response.text}",
        )
    except httpx.RequestError as e:
        log.error(f"Cannot reach Spring Boot API: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cannot reach CIBA agent API at {CIBA_AGENT_URL}",
        )

    auth_req_id = data["auth_req_id"]
    request_id = str(uuid.uuid4())

    # Store mapping: request_id → auth_req_id + user_id + action
    _token_store[request_id] = {
        "auth_req_id": auth_req_id,
        "user_id": req.user_id,
        "action": req.action,
        "params": req.params,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    log.info(f"CIBA request created: request_id={request_id}, auth_req_id={auth_req_id}")

    return AuthResponse(
        request_id=request_id,
        auth_req_id=auth_req_id,
        binding_message=binding_msg,
        mode=data.get("mode", "poll"),
        poll_url=f"/auth/status/{request_id}",
        expires_in=data.get("timeout_seconds", 300),
    )


# ── 2. GET /auth/status/{request_id} ─────────────────────────────────────────
# Check if the CIBA auth request has been approved by the user.

@app.get("/auth/status/{request_id}")
async def auth_status(request_id: str):
    entry = _token_store.get(request_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Request not found")

    if entry["status"] == "approved":
        return {
            "request_id": request_id,
            "status": "approved",
            "user_id": entry["user_id"],
            "action": entry["action"],
            "expires_in": entry.get("expires_in", 0),
        }

    if entry["status"] == "denied":
        return {
            "request_id": request_id,
            "status": "denied",
            "user_id": entry["user_id"],
        }

    # Still pending — poll Spring Boot
    try:
        resp = http.post(
            f"{CIBA_AGENT_URL}/ciba/poll/{entry['auth_req_id']}",
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") == "approved":
            entry["status"] = "approved"
            entry["access_token"] = data["access_token"]
            entry["id_token"] = data.get("id_token", "")
            entry["expires_in"] = data.get("expires_in", 300)
            entry["scope"] = data.get("scope", "")
            return {
                "request_id": request_id,
                "status": "approved",
                "user_id": entry["user_id"],
                "action": entry["action"],
                "expires_in": entry["expires_in"],
            }

        if data.get("status") == "denied":
            entry["status"] = "denied"
            return {
                "request_id": request_id,
                "status": "denied",
                "user_id": entry["user_id"],
            }

    except httpx.HTTPStatusError as e:
        log.warn(f"Poll failed: {e.response.text}")

    return {
        "request_id": request_id,
        "status": "pending",
        "user_id": entry["user_id"],
        "binding_message": get_binding_message(entry["action"]),
    }


# ── 3. POST /agent/execute/{request_id} ──────────────────────────────────────
# Execute the requested action using the CIBA token.
# Fails if user hasn't approved yet.

@app.post("/agent/execute/{request_id}", response_model=ActionResult)
async def execute_action(request_id: str):
    entry = _token_store.get(request_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Request not found")

    if entry["status"] != "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Action not approved yet. Current status: {entry['status']}",
        )

    action = entry["action"]
    params = entry["params"]

    if action in ("read_calendar", "list_events"):
        return await _do_calendar_action(entry, params)
    elif action == "read_emails":
        return await _do_email_action(entry, params)
    elif action == "get_profile":
        return await _do_profile_action(entry)
    else:
        return ActionResult(
            success=False,
            action=action,
            user_id=entry["user_id"],
            error=f"Action '{action}' not implemented yet",
        )


# ── Action implementations ─────────────────────────────────────────────────────

async def _do_calendar_action(entry: dict, params: dict) -> ActionResult:
    try:
        headers = {"Authorization": f"Bearer {entry['access_token']}"}
        resp = http.get(
            f"{CIBA_AGENT_URL}/api/calendar/events",
            headers=headers,
            params={
                "from": params.get("from", ""),
                "to": params.get("to", ""),
                "limit": params.get("limit", 50),
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        return ActionResult(
            success=True,
            action=entry["action"],
            user_id=entry["user_id"],
            data=resp.json(),
        )
    except httpx.HTTPStatusError as e:
        return ActionResult(
            success=False,
            action=entry["action"],
            user_id=entry["user_id"],
            error=f"Calendar API error {e.response.status_code}: {e.response.text}",
        )
    except httpx.RequestError as e:
        return ActionResult(
            success=False,
            action=entry["action"],
            user_id=entry["user_id"],
            error=f"Cannot reach calendar API: {e}",
        )


async def _do_email_action(entry: dict, params: dict) -> ActionResult:
    try:
        headers = {"Authorization": f"Bearer {entry['access_token']}"}
        resp = http.get(
            f"{CIBA_AGENT_URL}/api/email/messages",
            headers=headers,
            params={"folder": params.get("folder", "INBOX"), "limit": params.get("limit", 20)},
            timeout=30.0,
        )
        resp.raise_for_status()
        return ActionResult(
            success=True,
            action=entry["action"],
            user_id=entry["user_id"],
            data=resp.json(),
        )
    except httpx.HTTPStatusError as e:
        return ActionResult(
            success=False,
            action=entry["action"],
            user_id=entry["user_id"],
            error=f"Email API error: {e.response.text}",
        )
    except httpx.RequestError as e:
        return ActionResult(
            success=False,
            action=entry["action"],
            user_id=entry["user_id"],
            error=f"Cannot reach email API: {e}",
        )


async def _do_profile_action(entry: dict) -> ActionResult:
    try:
        headers = {"Authorization": f"Bearer {entry['access_token']}"}
        resp = http.get(
            f"{CIBA_AGENT_URL}/api/profile/me",
            headers=headers,
            timeout=30.0,
        )
        resp.raise_for_status()
        return ActionResult(
            success=True,
            action="get_profile",
            user_id=entry["user_id"],
            data=resp.json(),
        )
    except httpx.HTTPStatusError as e:
        return ActionResult(
            success=False,
            action="get_profile",
            user_id=entry["user_id"],
            error=f"Profile API error: {e.response.text}",
        )
    except httpx.RequestError as e:
        return ActionResult(
            success=False,
            action="get_profile",
            user_id=entry["user_id"],
            error=f"Cannot reach profile API: {e}",
        )


# ── Scope mapping ─────────────────────────────────────────────────────────────
def _action_to_scope(action: str) -> str:
    scopes = {
        "read_calendar": "openid profile calendar.read email",
        "list_events": "openid profile calendar.read",
        "send_email": "openid profile email",
        "read_emails": "openid profile email",
        "get_profile": "openid profile email",
    }
    return scopes.get(action, "openid profile")


# ── Run ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7000, log_level="info")
