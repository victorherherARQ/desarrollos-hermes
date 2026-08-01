"""Configuration loaded from environment variables."""
from __future__ import annotations

import os

# Keycloak
KEYCLOAK_BASE_URL: str = os.getenv("KEYCLOAK_BASE_URL", "http://localhost:8180")
KEYCLOAK_REALM: str = os.getenv("KEYCLOAK_REALM", "ciba-realm")
KEYCLOAK_ISSUER: str = f"{KEYCLOAK_BASE_URL}/realms/{KEYCLOAK_REALM}"

# Spring Boot CIBA Client API
CIBA_AGENT_URL: str = os.getenv("CIBA_AGENT_URL", "http://localhost:8080")

# CIBA client credentials (must match Keycloak registration)
CIBA_CLIENT_ID: str = os.getenv("CIBA_CLIENT_ID", "ciba-agent")
CIBA_CLIENT_SECRET: str = os.getenv("CIBA_CLIENT_SECRET", "ciba-agent-secret")

# Agent settings
AGENT_PORT: int = int(os.getenv("AGENT_PORT", "7000"))
AGENT_LOG_LEVEL: str = os.getenv("AGENT_LOG_LEVEL", "INFO")

# Resource server audiences (what the CIBA token should be audience for)
RESOURCE_SERVERS: list[str] = [
    "calendar-api",
    "email-api",
    "profile-api",
]
