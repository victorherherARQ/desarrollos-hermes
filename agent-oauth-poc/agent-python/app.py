"""
FastAPI del agente IA.

Endpoint principal:  POST /agente/call
  - Recibe {user_id, request, action_type, scope}
  - Decide el flujo OAuth según la sensibilidad del scope:
      *.read   -> JWT Bearer (pre-aprobado, rutinario)
      *.send   -> CIBA        (requiere aprobación fuera de banda del usuario)
  - Con el access_token obtenido, invoca la API de negocio correspondiente.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from config import API_BASE_URL, USERS, get_user
from oauth_client import OAuthClient

# --- Logging ---------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
logger = logging.getLogger("agent.app")
# Subimos el detalle de httpx sólo si hace falta
logging.getLogger("httpx").setLevel(LOG_LEVEL)

app = FastAPI(
    title="Agente IA -- OAuth/OIDC PoC",
    version="1.0.0",
    description=(
        "Agente que actúa en nombre de usuarios delegando en Keycloak. "
        "Usa JWT Bearer para acciones rutinarias y CIBA para sensibles."
    ),
)
oauth = OAuthClient()


# --- Modelos ---------------------------------------------------------------
class CallRequest(BaseModel):
    user_id: str = Field(..., description="ID del usuario en nombre de quien actúa el agente")
    request: str = Field(..., description="Frase/petición en lenguaje natural")
    action_type: str = Field(..., description="Tipo lógico de acción (read_calendar, send_email, ...)")
    scope: str = Field(..., description="Scope OAuth pedido, p.ej. calendar.read, email.send")


class CallResponse(BaseModel):
    result: Any


# --- Endpoints -------------------------------------------------------------
@app.get("/agente/health")
async def health() -> dict:
    logger.debug("health check")
    return {"status": "UP"}


@app.post("/agente/call", response_model=CallResponse)
async def agente_call(req: CallRequest) -> CallResponse:
    logger.info(
        "Llamada recibida: user=%s scope=%s action=%s request=%r",
        req.user_id, req.scope, req.action_type, req.request,
    )

    if get_user(req.user_id) is None:
        logger.warning("user_id desconocido: %s", req.user_id)
        raise HTTPException(
            status_code=404,
            detail=f"Usuario '{req.user_id}' no registrado",
        )

    # 1) Decidir flujo OAuth según sensibilidad del scope
    if req.scope.endswith(".read"):
        logger.info("[DECISION] scope rutinario -> JWT Bearer (OBO via password)")
        token_resp = await oauth.jwt_bearer_flow(req.user_id, req.scope)
    elif req.scope.endswith(".send"):
        logger.info("[DECISION] scope sensible -> CIBA (backchannel al usuario)")
        token_resp = await oauth.ciba_flow(
            user_id=req.user_id,
            scope=req.scope,
            request_text=req.request,
        )
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Scope '{req.scope}' no soportado (debe terminar en .read o .send)",
        )

    access_token = token_resp.get("access_token")
    if not access_token:
        logger.error("Keycloak no devolvió access_token: %s", token_resp)
        raise HTTPException(
            status_code=502,
            detail="Keycloak no devolvió access_token",
        )

    # 2) Llamar a la API de negocio con el token del usuario.
    # Authorization: Bearer <jwt>. Spring Boot valida el JWT contra Keycloak
    # y extrae el claim `scope` con la lista de scopes granted.
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        if req.scope == "calendar.read":
            logger.info(
                "[API] GET %s/api/calendar/events?user_id=%s",
                API_BASE_URL, req.user_id,
            )
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{API_BASE_URL}/api/calendar/events",
                    params={"user_id": req.user_id},
                    headers=headers,
                )
            logger.debug("[API] respuesta HTTP %d body=%s", resp.status_code, resp.text)
            resp.raise_for_status()
            result: Any = resp.json()

        elif req.scope == "email.send":
            # El cuerpo del email sale del campo request / action_type del payload.
            # En un agente "real" esto vendría del LLM; aquí lo tomamos literal.
            user = get_user(req.user_id) or {}
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
            logger.debug("[API] respuesta HTTP %d body=%s", resp.status_code, resp.text)
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
        logger.error(
            "[API] Error HTTP %d desde %s: %s",
            e.response.status_code, e.request.url, e.response.text,
        )
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"API upstream: {e.response.text}",
        )
    except httpx.RequestError as e:
        logger.error("[API] Error de conexión: %s", e)
        raise HTTPException(
            status_code=503,
            detail=f"No se pudo conectar a la API: {e}",
        )

    logger.info("Llamada finalizada OK para user=%s scope=%s", req.user_id, req.scope)
    return CallResponse(result=result)