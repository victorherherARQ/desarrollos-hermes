"""
Cliente OAuth/OIDC del agente — Versión "A+B+C portable".

Implementa TRES flujos de delegación, todos sin que el humano comparta password
con el agente:

  A) Authorization Code + PKCE (RFC 6749 + RFC 7636)
     El humano se autentica en `client-mock` (webapp) usando Auth Code + PKCE
     contra el IdP. client-mock recibe el `access_token` + `refresh_token` y
     los entrega al agente (vía canal seguro: API interna en la PoC, en
     producción sería deep link / clipboard firmado / etc.).

  C) On-Behalf-Of / JWT Bearer (RFC 7523)
     El agente intercambia el `user_access_token` recibido de client-mock
     por un nuevo access_token delegado con el scope específico.
     Funciona idéntico en Keycloak 26+ y Azure B2C External ID.

  B) Device Code Flow (RFC 8628)
     Fallback para escenarios headless. El agente pide un `device_code` al IdP,
     imprime el `user_code` + URL. El humano va a su dispositivo, introduce el
     código y aprueba. El agente hace polling al token endpoint.

El agente actúa como cliente OAuth *confidential* (client_id + client_secret)
o *public* (con PKCE), según el flujo.

Referencia: docs/ESTUDIO_AZURE_B2C.md §14 (replanteamiento de flujos).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import time
import uuid
from typing import Any
from urllib.parse import urlencode

import httpx

from config import (
    AGENT_CLIENT_ID,
    AGENT_CLIENT_SECRET,
    DEVICE_AUTHORIZATION_ENDPOINT,
    IDP_AUTHORIZE_ENDPOINT,
    IDP_ISSUER,
    IDP_TOKEN_ENDPOINT,
    IDP_USERINFO_ENDPOINT,
)

logger = logging.getLogger("agent.oauth")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers PKCE (RFC 7636)
# ─────────────────────────────────────────────────────────────────────────────
def _b64url_nopad(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def make_pkce_pair() -> tuple[str, str]:
    """
    Genera un par (code_verifier, code_challenge) para PKCE (RFC 7636 §4).

    code_verifier:  43-128 chars random [A-Z][a-z][0-9]-._~
    code_challenge: BASE64URL(SHA256(code_verifier))
    """
    verifier = _b64url_nopad(os.urandom(32))
    challenge = _b64url_nopad(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


# ─────────────────────────────────────────────────────────────────────────────
# OAuthClient
# ─────────────────────────────────────────────────────────────────────────────
class OAuthClient:
    """Encapsula los tres flujos OAuth/OIDC: A (Auth Code + PKCE), B (Device), C (OBO)."""

    # ----------------------------------------------------------------- #
    # FLUJO A: Authorization Code + PKCE (lado del agente)              #
    # ----------------------------------------------------------------- #
    # El cliente-mock hace el dance del Auth Code (es el "cliente público"
    # que el humano usa para autenticarse). El agente solo GENERA el PKCE
    # pair y se lo entrega a client-mock para que lo use en el redirect.
    # Tras el callback, el agente (con su client_id/secret) intercambia
    # el `code` por tokens.
    # ----------------------------------------------------------------- #
    def build_authorize_url(
        self,
        scope: str,
        state: str | None = None,
        acr_values: str | None = None,
    ) -> dict[str, str]:
        """
        Construye la URL de authorize + PKCE pair + state.

        Devuelve:
          {
            "authorize_url":  "https://idp/...?...",
            "code_verifier":  "<verifier>",   # el agente lo guarda
            "state":          "<state>",      # CSRF token
          }
        El cliente-mock debe:
          1. Redirigir al browser del humano a authorize_url
          2. Cuando vuelva con ?code=...&state=... llamar a
             oauth.exchange_code_for_tokens(code, code_verifier)
        """
        verifier, challenge = make_pkce_pair()
        state = state or _b64url_nopad(os.urandom(16))

        params = {
            "response_type": "code",
            "client_id": AGENT_CLIENT_ID,
            "scope": scope,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            # Redirect URI donde client-mock recibe el code
            "redirect_uri": os.getenv(
                "CLIENT_MOCK_REDIRECT_URI",
                "http://localhost:3000/callback",
            ),
        }
        if acr_values:
            params["acr_values"] = acr_values

        url = f"{IDP_AUTHORIZE_ENDPOINT}?{urlencode(params)}"
        logger.info(
            "[A] authorize_url construido: scope=%s acr_values=%s state=%s",
            scope, acr_values, state,
        )
        return {
            "authorize_url": url,
            "code_verifier": verifier,
            "state": state,
        }

    async def exchange_code_for_tokens(
        self,
        code: str,
        code_verifier: str,
    ) -> dict[str, Any]:
        """
        Intercambia el `code` (recibido por client-mock) por tokens.
        Este paso es donde el agente prueba su identidad con client_secret.

        Devuelve: {access_token, refresh_token, id_token, expires_in, scope, ...}
        """
        logger.info("[A] Intercambiando code por tokens...")
        data = {
            "grant_type": "authorization_code",
            "client_id": AGENT_CLIENT_ID,
            "client_secret": AGENT_CLIENT_SECRET,
            "code": code,
            "code_verifier": code_verifier,
            "redirect_uri": os.getenv(
                "CLIENT_MOCK_REDIRECT_URI",
                "http://localhost:3000/callback",
            ),
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(IDP_TOKEN_ENDPOINT, data=data)
            logger.debug(
                "[A] POST %s -> HTTP %d body=%s",
                IDP_TOKEN_ENDPOINT, resp.status_code, resp.text[:200],
            )
            if resp.status_code >= 400:
                logger.error("[A] Error: %s", resp.text[:300])
            resp.raise_for_status()
            return resp.json()

    async def refresh_user_token(
        self,
        refresh_token: str,
        scope: str | None = None,
    ) -> dict[str, Any]:
        """
        Renueva el access_token del humano usando su refresh_token.
        Importante: en muchos IdPs (incluido Keycloak 24) el refresh_token
        rota con cada uso. El cliente-mock debe actualizarlo tras cada call.
        """
        data = {
            "grant_type": "refresh_token",
            "client_id": AGENT_CLIENT_ID,
            "client_secret": AGENT_CLIENT_SECRET,
            "refresh_token": refresh_token,
        }
        if scope:
            data["scope"] = scope
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(IDP_TOKEN_ENDPOINT, data=data)
            if resp.status_code >= 400:
                logger.error("[A] refresh error: %s", resp.text[:300])
            resp.raise_for_status()
            return resp.json()

    # ----------------------------------------------------------------- #
    # FLUJO C: On-Behalf-Of (RFC 7523 / JWT Bearer)                    #
    # ----------------------------------------------------------------- #
    # El agente canjea el access_token del humano por un access_token
    # delegado con el scope específico.
    # ----------------------------------------------------------------- #
    async def obo_exchange(
        self,
        user_access_token: str,
        requested_scope: str,
    ) -> dict[str, Any]:
        """
        On-Behalf-Of: canjea un user_access_token por un token delegado.

        El scope del token delegado se limita a `requested_scope` (no el
        scope completo del user_token). Esto implementa el principio de
        menor privilegio.

        Devuelve: {access_token, expires_in, scope, token_type}
        """
        logger.info(
            "[C/OBO] user_token=<elided> scope=%s",
            requested_scope,
        )
        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "client_id": AGENT_CLIENT_ID,
            "client_secret": AGENT_CLIENT_SECRET,
            "assertion": user_access_token,
            "scope": requested_scope,
            "requested_token_use": "on_behalf_of",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(IDP_TOKEN_ENDPOINT, data=data)
            logger.debug(
                "[C/OBO] POST %s -> HTTP %d body=%s",
                IDP_TOKEN_ENDPOINT, resp.status_code, resp.text[:200],
            )
            if resp.status_code >= 400:
                logger.error("[C/OBO] Error: %s", resp.text[:300])
            resp.raise_for_status()
            return resp.json()

    # ----------------------------------------------------------------- #
    # FLUJO C (IDENTIDAD): JWT Bearer con identity-assertion           #
    # ----------------------------------------------------------------- #
    # El agente firma una identity-assertion JWT (con claims
    # dni_verified=true, dob_verified=true) y la presenta al IdP
    # junto con su client_secret. El IdP emite el access_token sin
    # pedir password porque la assertion prueba que el agente ya
    # verificó la identidad del humano.
    #
    # Diferencia con obo_exchange (que usa el access_token del humano):
    # aquí NO hay access_token previo — el agente demuestra la identidad
    # directamente con su firma + claims.
    # ----------------------------------------------------------------- #
    async def identity_exchange(
        self,
        identity_assertion: str,
        scope: str,
    ) -> dict[str, Any]:
        """
        Canjea una identity-assertion JWT por un access_token del IdP.

        Args:
            identity_assertion: JWT firmado por el agente con los claims
                                dni_verified / dob_verified / identity_method.
            scope: Scope OAuth pedido (p.ej. 'calendar.read').

        Returns:
            {access_token, expires_in, scope, token_type}

        Raises:
            httpx.HTTPStatusError si el IdP responde con >= 400.
        """
        logger.info("[C/Identity] canjeando identity_assertion scope=%s", scope)
        data = {
            "grant_type":    "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "client_id":     AGENT_CLIENT_ID,
            "client_secret": AGENT_CLIENT_SECRET,
            "assertion":     identity_assertion,
            "scope":         scope,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(IDP_TOKEN_ENDPOINT, data=data)
            logger.debug(
                "[C/Identity] POST %s -> HTTP %d",
                IDP_TOKEN_ENDPOINT, resp.status_code,
            )
            if resp.status_code >= 400:
                logger.error("[C/Identity] Error: %s", resp.text[:300])
            resp.raise_for_status()
            return resp.json()

    # ----------------------------------------------------------------- #
    # FLUJO B: Device Code Flow (RFC 8628)                             #
    # ----------------------------------------------------------------- #
    # Para agentes headless: el agente imprime un código + URL, el humano
    # va a su dispositivo, introduce el código y aprueba. Mientras tanto
    # el agente hace polling.
    # ----------------------------------------------------------------- #
    async def device_authorize(self, scope: str) -> dict[str, Any]:
        """
        Paso 1: pide un device_code al IdP.
        Devuelve: {
          device_code, user_code, verification_uri, verification_uri_complete,
          expires_in, interval
        }
        """
        logger.info("[B/Device] Solicitando device_code para scope=%s", scope)
        data = {
            "client_id": AGENT_CLIENT_ID,
            "client_secret": AGENT_CLIENT_SECRET,
            "scope": scope,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(DEVICE_AUTHORIZATION_ENDPOINT, data=data)
            if resp.status_code >= 400:
                logger.error("[B/Device] /device auth error: %s", resp.text[:300])
            resp.raise_for_status()
            return resp.json()

    async def device_poll_for_tokens(
        self,
        device_code: str,
        interval: int = 5,
        expires_in: int = 600,
    ) -> dict[str, Any]:
        """
        Paso 2: polling al token endpoint con el device_code hasta que el
        humano apruebe o expire.

        Devuelve: {access_token, refresh_token, ...} cuando el humano aprueba.
        Lanza TimeoutError si expira sin aprobación.
        """
        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "client_id": AGENT_CLIENT_ID,
            "client_secret": AGENT_CLIENT_SECRET,
            "device_code": device_code,
        }
        elapsed = 0
        async with httpx.AsyncClient(timeout=10.0) as client:
            while elapsed < expires_in:
                await asyncio.sleep(interval)
                elapsed += interval
                logger.debug("[B/Device] poll t+%ds", elapsed)
                resp = await client.post(IDP_TOKEN_ENDPOINT, data=data)

                if resp.status_code == 200:
                    token = resp.json()
                    logger.info(
                        "[B/Device] ¡Aprobado! access_token=%s",
                        "<elided>",
                    )
                    return token

                body = {}
                try:
                    body = resp.json()
                except ValueError:
                    pass
                err = body.get("error", "")
                if err == "authorization_pending":
                    continue
                if err == "slow_down":
                    interval += 5
                    continue
                if err in ("expired_token", "access_denied"):
                    logger.error("[B/Device] Error terminal: %s", err)
                    resp.raise_for_status()
                # Otro error inesperado
                logger.warning(
                    "[B/Device] HTTP %d: %s", resp.status_code, resp.text,
                )
                resp.raise_for_status()

        raise TimeoutError(
            f"[B/Device] El humano no aprobó en {expires_in}s"
        )

    # ----------------------------------------------------------------- #
    # UserInfo (opcional, para debugging / ver quién es el humano)      #
    # ----------------------------------------------------------------- #
    async def userinfo(self, access_token: str) -> dict[str, Any]:
        """Llama al endpoint /userinfo con el token del usuario."""
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(IDP_USERINFO_ENDPOINT, headers=headers)
            resp.raise_for_status()
            return resp.json()
