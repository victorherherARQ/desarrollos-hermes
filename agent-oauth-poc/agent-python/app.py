"""
FastAPI del agente IA — Versión A+B+C portable.

Endpoints:
  GET  /agente/health                        -- healthcheck
  POST /agente/auth/authorize                -- FLUJO A: devuelve authorize_url con PKCE
  POST /agente/auth/device                   -- FLUJO B: pide device_code
  POST /agente/auth/token                    -- (uso interno) intercambia code/refresh
  POST /agente/call                          -- endpoint unificado de acción

Flujo A (Auth Code + PKCE):
  1. Cliente llama POST /agente/auth/authorize con {user_id, scope}
  2. El agente devuelve {authorize_url, code_verifier, state}
  3. Cliente redirige al browser del humano a authorize_url
  4. Humano aprueba en IdP, vuelve a client-mock/callback con ?code=...&state=...
  5. Cliente llama POST /agente/auth/token con {code, code_verifier}
  6. El agente hace OBO (FLUJO C) para reducir el scope y devuelve el access_token
  7. Cliente usa el access_token para llamar a /agente/call (o lo pasa a la API)

Flujo B (Device Code):
  1. Cliente llama POST /agente/auth/device con {user_id, scope}
  2. Agente pide device_code al IdP y devuelve {user_code, verification_uri, ...}
  3. Cliente muestra al humano "ve a <verification_uri> e introduce <user_code>"
  4. Agente hace polling en background
  5. Cuando el humano aprueba, el agente tiene access_token
  6. Cliente usa el access_token para llamar a /agente/call

Flujo C (OBO / JWT Bearer): interno, no expuesto al cliente (lo llama el
agente a sí mismo para refinar el scope).
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx
import jwt as pyjwt
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from config import (
    AGENT_CLIENT_ID,
    AGENT_CLIENT_SECRET,
    API_BASE_URL,
    CLIENT_MOCK_REDIRECT_URI,
    IDP_ISSUER,
    USERS,
    get_user,
    verify_identity,
)
from oauth_client import OAuthClient


# ─── Storage en memoria para challenges de identidad (PoC — en prod: Redis)
PENDING_CHALLENGES: dict[str, dict[str, Any]] = {}


# ─── Helper: firmar identity-assertion JWT (HS256 con AGENT_CLIENT_SECRET)
def _sign_identity_assertion(payload: dict[str, Any]) -> str:
    """
    Firma una identity-assertion JWT con HS256.

    En PoC usamos HS256 (mismo secreto que el client). En producción sería
    RS256 con la private_key del agente y la public_key registrada en el
    IdP — o un client_assertion JWT firmado con la key del cliente.

    Returns:
        JWT en formato compacto (xxx.yyy.zzz).
    """
    return pyjwt.encode(
        payload,
        AGENT_CLIENT_SECRET,
        algorithm="HS256",
        headers={"typ": "JWT", "kid": AGENT_CLIENT_ID},
    )

# ─── Logging ────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
logger = logging.getLogger("agent.app")
logging.getLogger("httpx").setLevel(LOG_LEVEL)

app = FastAPI(
    title="Agente IA -- OAuth/OIDC PoC (A+B+C)",
    version="2.0.0",
    description=(
        "Agente que actúa en nombre de usuarios delegando en un IdP OIDC. "
        "Soporta 3 flujos: Auth Code + PKCE (A), Device Code (B), OBO (C). "
        "Portable entre Keycloak y Azure B2C External ID."
    ),
)
oauth = OAuthClient()


# ─── Modelos ────────────────────────────────────────────────────────────────
class AuthorizeRequest(BaseModel):
    user_id: str = Field(..., description="ID del usuario")
    scope: str = Field(
        ...,
        description="Scope OAuth pedido, p.ej. 'openid profile calendar.read'",
    )
    acr_values: str | None = Field(
        None,
        description="Forzar MFA: '2' o 'c2' según el IdP",
    )


class AuthorizeResponse(BaseModel):
    authorize_url: str
    code_verifier: str
    state: str
    redirect_uri: str


class TokenRequest(BaseModel):
    code: str | None = Field(None, description="Authorization code (flujo A)")
    code_verifier: str | None = Field(None, description="PKCE verifier (flujo A)")
    refresh_token: str | None = Field(None, description="Refresh token (renovación)")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    id_token: str | None = None
    expires_in: int | None = None
    scope: str | None = None
    token_type: str | None = "Bearer"


class DeviceRequest(BaseModel):
    user_id: str
    scope: str


class DeviceResponse(BaseModel):
    user_code: str
    device_code: str
    verification_uri: str
    verification_uri_complete: str | None = None
    expires_in: int
    interval: int


class CallRequest(BaseModel):
    access_token: str = Field(..., description="Access token (obtenido vía A o B)")
    request: str = Field(..., description="Frase/petición en lenguaje natural")
    action_type: str = Field(..., description="Tipo lógico de acción")
    scope: str = Field(
        ...,
        description="Scope OAuth que debe llevar el token (para OBO/verificación)",
    )


class CallResponse(BaseModel):
    flow: str
    result: Any


# ─── Endpoints ──────────────────────────────────────────────────────────────
@app.get("/agente/health")
async def health() -> dict:
    logger.debug("health check")
    return {
        "status": "UP",
        "idp_issuer": IDP_ISSUER,
        "agent_client_id": AGENT_CLIENT_ID,
        "supported_flows": ["A:auth_code+pkce", "B:device_code", "C:obo"],
    }


# ─── FLUJO A: paso 1 — construir authorize URL ─────────────────────────────
@app.post("/agente/auth/authorize", response_model=AuthorizeResponse)
async def auth_authorize(req: AuthorizeRequest) -> AuthorizeResponse:
    """
    Construye la URL de authorize con PKCE.
    El cliente (webapp) redirige al humano a esa URL.
    """
    if get_user(req.user_id) is None:
        raise HTTPException(status_code=404, detail=f"Usuario '{req.user_id}' no registrado")
    logger.info(
        "[A] Construyendo authorize URL: user=%s scope=%s acr_values=%s",
        req.user_id, req.scope, req.acr_values,
    )
    out = oauth.build_authorize_url(
        scope=req.scope,
        acr_values=req.acr_values,
    )
    return AuthorizeResponse(
        authorize_url=out["authorize_url"],
        code_verifier=out["code_verifier"],
        state=out["state"],
        redirect_uri=CLIENT_MOCK_REDIRECT_URI,
    )


# ─── FLUJO A: paso 2 — intercambiar code por tokens ────────────────────────
@app.post("/agente/auth/token", response_model=TokenResponse)
async def auth_token(req: TokenRequest) -> TokenResponse:
    """
    Intercambia el authorization code por tokens (paso final de A).
    """
    if not req.code or not req.code_verifier:
        raise HTTPException(
            status_code=400,
            detail="code y code_verifier son obligatorios",
        )
    try:
        tok = await oauth.exchange_code_for_tokens(req.code, req.code_verifier)
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"IdP rechazó el code: {e.response.text}",
        )
    return TokenResponse(**tok)


# ─── FLUJO A: refresh ───────────────────────────────────────────────────────
@app.post("/agente/auth/refresh", response_model=TokenResponse)
async def auth_refresh(req: TokenRequest) -> TokenResponse:
    """Renueva el access_token del humano usando su refresh_token."""
    if not req.refresh_token:
        raise HTTPException(status_code=400, detail="refresh_token obligatorio")
    try:
        tok = await oauth.refresh_user_token(req.refresh_token)
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"IdP rechazó el refresh: {e.response.text}",
        )
    return TokenResponse(**tok)


# ─── FLUJO B: device code (paso 1) ──────────────────────────────────────────
@app.post("/agente/auth/device", response_model=DeviceResponse)
async def auth_device(req: DeviceRequest) -> DeviceResponse:
    """
    Pide un device_code al IdP. El cliente debe mostrar al humano
    verification_uri + user_code.
    """
    if get_user(req.user_id) is None:
        raise HTTPException(status_code=404, detail=f"Usuario '{req.user_id}' no registrado")
    logger.info("[B] Solicitando device_code: user=%s scope=%s", req.user_id, req.scope)
    out = await oauth.device_authorize(scope=req.scope)
    return DeviceResponse(
        user_code=out["user_code"],
        device_code=out["device_code"],
        verification_uri=out["verification_uri"],
        verification_uri_complete=out.get("verification_uri_complete"),
        expires_in=int(out.get("expires_in", 600)),
        interval=int(out.get("interval", 5)),
    )


# ─── FLUJO B: device poll (paso 2) ─────────────────────────────────────────
@app.post("/agente/auth/device/poll", response_model=TokenResponse)
async def auth_device_poll(req: DeviceRequest) -> TokenResponse:
    """
    Hace polling al token endpoint con device_code hasta que el humano apruebe.
    ATENCIÓN: este endpoint bloquea hasta expires_in segundos. Úsalo solo en
    PoC o con un timeout explícito en el cliente.
    """
    # En producción, el cliente-mock debería hacer el polling y notificar
    # al agente cuando llegue el access_token. Esto es solo para PoC.
    raise HTTPException(
        status_code=501,
        detail=(
            "Use el cliente-mock como UI para device code. "
            "El agente hace polling interno."
        ),
    )


# ─── Endpoint unificado: ejecutar la acción del agente ──────────────────────
@app.post("/agente/call", response_model=CallResponse)
async def agente_call(req: CallRequest) -> CallResponse:
    """
    Ejecuta una acción del agente usando el access_token del usuario.
    Si el scope pedido NO está ya en el access_token, hace OBO (flujo C)
    para reducir el scope.
    """
    logger.info(
        "Llamada recibida: scope=%s action=%s request=%r",
        req.scope, req.action_type, req.request,
    )

    # 1) Decidir si el access_token ya sirve o hace falta OBO
    access_token = req.access_token
    flow_used = "A_or_B"

    # Decodificar el JWT (sin verificar firma) para ver el scope actual.
    # OJO: en producción la verificación de firma la hace la API destino,
    # no el agente. Aquí solo inspeccionamos el claim.
    claims: dict[str, Any] = {}
    current_scope: list[str] = []
    try:
        import base64
        import json as _json
        payload_b64 = access_token.split(".")[1]
        # Pad base64
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = base64.urlsafe_b64decode(payload_b64.encode("ascii"))
        claims = _json.loads(payload)
        _sc = claims.get("scope") or claims.get("scp") or ""
        current_scope = [str(s) for s in _sc.split()]
    except Exception as e:
        logger.warning("No pude decodificar el JWT: %s", e)

    if req.scope not in current_scope:
        logger.info(
            "[DECISION] scope=%s NO está en el token. Aplicando FLUJO C (OBO)...",
            req.scope,
        )
        try:
            delegated = await oauth.obo_exchange(
                user_access_token=req.access_token,
                requested_scope=req.scope,
            )
            access_token = delegated["access_token"]
            flow_used = "A+C" if "device" not in current_scope else "B+C"
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=(
                    f"OBO falló: {e.response.text}. "
                    "¿El IdP soporta jwt-bearer con requested_token_use=on_behalf_of? "
                    "Keycloak 24 NO lo soporta nativo (necesita KC 26+); "
                    "en ese caso, pide el scope completo al IdP en el authorize inicial."
                ),
            )
    else:
        logger.info(
            "[DECISION] scope=%s ya está en el token, no hace falta OBO",
            req.scope,
        )

    # 2) Llamar a la API de negocio con el access_token
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        if req.scope == "calendar.read":
            logger.info("[API] GET %s/api/calendar/events", API_BASE_URL)
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{API_BASE_URL}/api/calendar/events",
                    params={"user_id": claims.get("preferred_username", "ana")},
                    headers=headers,
                )
            resp.raise_for_status()
            result = resp.json()

        elif req.scope == "email.send":
            user = get_user(claims.get("preferred_username", "ana")) or {}
            email_body = {
                "to": user.get("email", "unknown@example.com"),
                "subject": req.action_type,
                "body": req.request,
            }
            logger.info(
                "[API] POST %s/api/email/send body=%s",
                API_BASE_URL, {**email_body, "body": "<...>"},
            )
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{API_BASE_URL}/api/email/send",
                    json=email_body,
                    headers=headers,
                )
            resp.raise_for_status()
            result = resp.json()

        else:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Scope '{req.scope}' no tiene mapeo a endpoint de API. "
                    "Soporta: calendar.read, email.send"
                ),
            )

    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"API upstream: {e.response.text}",
        )
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"No se pudo conectar a la API: {e}")

    logger.info("Llamada finalizada OK: flow=%s scope=%s", flow_used, req.scope)
    return CallResponse(flow=flow_used, result=result)
