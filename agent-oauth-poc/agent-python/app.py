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
import uuid
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


# ─── FLUJO C (IDENTIDAD): modelos de request/response ────────────────────
class IdentityRequest(BaseModel):
    """Datos identificativos que el cliente pasa al agente en lugar de voz."""

    user_id: str = Field(..., min_length=1, description="ID del usuario registrado")
    dni:     str = Field(..., min_length=8, max_length=12, description="DNI/NIF (8 dígitos + letra)")
    dob:     str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="Fecha ISO-8601 YYYY-MM-DD")
    scope:   str = Field(..., min_length=1, description="Scope OAuth pedido")


class IdentityResponse(BaseModel):
    """Respuesta tras verificar DNI+DOB + disparar push al móvil."""

    challenge_id:    str
    verification_uri: str
    expires_in:      int
    acr:             str


# ─── Endpoints ────────────────────────────────────────────────────────
@app.get("/agente/health")
async def health() -> dict:
    logger.debug("health check")
    return {
        "status": "UP",
        "idp_issuer": IDP_ISSUER,
        "agent_client_id": AGENT_CLIENT_ID,
        "supported_flows": [
            "A:auth_code+pkce",
            "B:device_code",
            "C:obo",
            "C:identity",  # identidad con DNI+DOB (sin voz)
        ],
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


    # ─── FLUJO C (IDENTIDAD): endpoint + push mock + polling ─────────────
@app.post("/agente/auth/identity", response_model=IdentityResponse)
async def auth_identity(req: IdentityRequest) -> IdentityResponse:
    """
    FLUJO C (versión sin voz): el humano NO tiene sesión web abierta.

    El cliente (webapp, CLI, IVR) recoge DNI + fecha de nacimiento del humano
    por un canal seguro y los pasa al agente. El agente verifica la identidad
    contra la tabla interna y, si coincide, inicia el push step-up al móvil
    del humano para MFA.

    Pasos:
      1. Verificar DNI + DOB contra tabla interna (verify_identity)
      2. Si coincide, crear identity_assertion JWT firmada por el agente
      3. Disparar push al device del usuario (en PoC: log + URL mock)
      4. Devolver challenge_id al cliente para que haga polling
    """
    logger.info(
        "[C/Identity] Solicitud para user_id=%s (DNI len=%d, DOB=%s)",
        req.user_id, len(req.dni), req.dob,
    )

    # 1. Verificar identidad
    if not verify_identity(req.user_id, req.dni, req.dob):
        logger.warning("[C/Identity] DNI/DOB NO coincide para user_id=%s", req.user_id)
        raise HTTPException(status_code=401, detail="Credenciales identificativas inválidas")

    user = get_user(req.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"Usuario '{req.user_id}' no registrado")

    # 2. Crear identity-assertion JWT
    challenge_id = str(uuid.uuid4())
    iat = int(time.time())
    exp = iat + 120  # 2 min

    identity_assertion = {
        "iss":             AGENT_CLIENT_ID,
        "sub":             req.user_id,
        "aud":             IDP_ISSUER,
        "iat":             iat,
        "exp":             exp,
        "jti":             challenge_id,
        "acr":             "id-claim",
        "auth_time":       iat,
        "dni_verified":    True,
        "dob_verified":    True,
        "identity_method": "dni+dob",
        "channel":         "id-claim",
        "act":             {"sub": AGENT_CLIENT_ID},  # RFC 8693
        "mobile_device_id": user["mobile_token"],
    }

    # Persistir
    PENDING_CHALLENGES[challenge_id] = {
        "user_id":            req.user_id,
        "identity_assertion": identity_assertion,
        "scope":              req.scope,
        "iat":                iat,
        "exp":                exp,
        "approved":           False,
        "biometric_used":     False,
    }

    # 3. Disparar push (en PoC: log; en producción, FCM/APNs)
    push_endpoint = f"/agente/auth/identity/push/{challenge_id}"
    logger.info(
        "[C/Identity] Push enviado a device=%s challenge_id=%s",
        user["mobile_token"], challenge_id,
    )

    return IdentityResponse(
        challenge_id=challenge_id,
        verification_uri=f"http://localhost:7000{push_endpoint}",
        expires_in=120,
        acr="id-claim+push-biometric",
    )


# ─── FLUJO C (IDENTIDAD): push mock (móvil aprueba) + polling ────────
@app.post("/agente/auth/identity/push/{challenge_id}")
async def auth_identity_push(challenge_id: str, biometric: bool = True) -> dict:
    """
    Endpoint mock que simula la app móvil del usuario.

    En producción, el push llega vía FCM/APNs a la app móvil del usuario
    y la app hace un callback a este endpoint cuando el humano aprueba
    (con su biometría — fingerprint/Face ID).

    Para la PoC: el desarrollador hace un curl/Postman a esta URL
    para aprobar el challenge manualmente.
    """
    challenge = PENDING_CHALLENGES.get(challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="challenge_id inválido")
    challenge["approved"] = True
    challenge["biometric_used"] = biometric
    logger.info(
        "[C/Identity] Push APROBADO challenge_id=%s user=%s biometric=%s",
        challenge_id, challenge["user_id"], biometric,
    )
    return {"status": "approved", "challenge_id": challenge_id, "biometric": biometric}


@app.post("/agente/auth/identity/poll", response_model=TokenResponse)
async def auth_identity_poll(challenge_id: str, biometric_used: bool = True) -> TokenResponse:
    """
    Polling: el cliente pregunta si el push ya fue aprobado.

    Si sí, firma la identity-assertion JWT, llama al IdP vía
    oauth.identity_exchange, y devuelve el access_token. Limpia el challenge
    del storage tras éxito.
    """
    challenge = PENDING_CHALLENGES.get(challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="challenge_id inválido o expirado")

    if int(time.time()) > challenge["exp"]:
        PENDING_CHALLENGES.pop(challenge_id, None)
        raise HTTPException(status_code=410, detail="Challenge expirado")

    if not challenge["approved"]:
        raise HTTPException(
            status_code=425,
            detail="Push pendiente de aprobación en el móvil del usuario",
        )

    challenge["biometric_used"] = biometric_used

    # Firmar la identity-assertion JWT
    identity_jwt = _sign_identity_assertion(challenge["identity_assertion"])

    # Canjear contra el IdP (si falla conexión, devolvemos 502 claro)
    try:
        token = await oauth.identity_exchange(
            identity_assertion=identity_jwt,
            scope=challenge["scope"],
        )
    except httpx.HTTPStatusError as e:
        logger.error("[C/Identity] IdP respondió %d: %s", e.response.status_code, e.response.text[:300])
        raise HTTPException(
            status_code=502,
            detail=f"IdP rechazó la assertion: {e.response.text[:300]}",
        )
    except httpx.RequestError as e:
        logger.error("[C/Identity] Error de red con IdP: %s", e)
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo conectar con el IdP: {type(e).__name__}",
        )

    # Limpiar challenge tras éxito
    user_id = challenge["user_id"]
    PENDING_CHALLENGES.pop(challenge_id, None)

    logger.info("[C/Identity] access_token emitido para user=%s", user_id)
    return TokenResponse(
        access_token=token["access_token"],
        expires_in=token["expires_in"],
        token_type=token.get("token_type", "Bearer"),
        scope=token.get("scope", challenge["scope"]),
    )


# ─── Endpoint unificado: ejecutar la acción del agente ──────────────
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
