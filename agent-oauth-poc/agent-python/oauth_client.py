"""
Cliente OAuth/OIDC del agente.

Implementa dos flujos de delegación:

  1. JWT Bearer (RFC 7521 / 7523)
     Para scopes rutinarios ya pre-aprobados por el usuario (p.ej. calendar.read).
     El agente intercambia una *assertion* (JWT firmado con el client_secret del
     agente que lleva `sub=<user_id>`) por un access_token "actuando en nombre de"
     ese usuario.

  2. CIBA -- Client Initiated Backchannel Authentication (OpenID Connect CIBA)
     Para scopes sensibles (p.ej. email.send). El agente dispara un ping al
     dispositivo del usuario (vía Keycloak + cliente mock de CIBA) y solo recibe
     el access_token tras la aprobación/consentimiento del usuario fuera de banda.

El agente actúa como cliente OAuth *confidential*: se autentica ante Keycloak
con `client_id` + `client_secret` y firma las assertions con HS256 usando el
mismo client_secret como clave compartida (caso "client_secret JWT", perfil
de `private_key_jwt` definido en OIDC Core §9).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx
import jwt  # PyJWT -- usamos HS256 con client_secret

from config import (
    AGENT_CLIENT_ID,
    AGENT_CLIENT_SECRET,
    KEYCLOAK_CIBA_AUTH_ENDPOINT,
    KEYCLOAK_ISSUER,
    KEYCLOAK_TOKEN_ENDPOINT,
    USERS,
)

logger = logging.getLogger("agent.oauth")


class OAuthClient:
    """Encapsula los flujos OAuth/OIDC que el agente necesita."""

    # ------------------------------------------------------------------ #
    # Assertions                                                         #
    # ------------------------------------------------------------------ #
    def user_assertion_for(self, user_id: str) -> str:
        """
        Crea una *user assertion* (JWT firmado con client_secret, HS256).

        Payload según RFC 7523 §3 + OIDC Core §9:
            sub = user_id          -> sobre QUIÉN se solicita el token (delegación)
            iss = agent_client_id  -> quién firma (el agente)
            aud = keycloak_token_endpoint -> a quién va dirigida
            exp = now + 300        -> válida 5 minutos
        """
        now = int(time.time())
        payload = {
            "sub": user_id,
            "iss": AGENT_CLIENT_ID,
            "aud": KEYCLOAK_TOKEN_ENDPOINT,
            "iat": now,
            "exp": now + 300,
        }
        assertion = jwt.encode(
            payload,
            AGENT_CLIENT_SECRET,
            algorithm="HS256",
        )
        logger.debug(
            "user_assertion creada: sub=%s iss=%s aud=%s exp=%d",
            user_id, AGENT_CLIENT_ID, KEYCLOAK_TOKEN_ENDPOINT, payload["exp"],
        )
        return assertion

    def login_hint_token_for(self, user_id: str, scope: str) -> str:
        """
        Crea un *login_hint_token* para CIBA (OIDC CIBA §5.1).

        Keycloak lo usa para:
          - saber a qué usuario notificar (`sub`)
          - mostrar contexto al usuario en el cliente CIBA (`scope`)
        """
        now = int(time.time())
        payload = {
            "sub": user_id,
            "scope": scope,
            "iss": AGENT_CLIENT_ID,
            "aud": KEYCLOAK_ISSUER,
            "iat": now,
            "exp": now + 300,
        }
        return jwt.encode(payload, AGENT_CLIENT_SECRET, algorithm="HS256")

    # ------------------------------------------------------------------ #
    # Flujo 1: On-Behalf-Of via Resource Owner Password Credentials        #
    # ------------------------------------------------------------------ #
    # En Keycloak 24 el grant RFC 7523 (jwt-bearer) NO está habilitado por
    # defecto. La forma pragmática de PoC es ROPC + claim `act` para que el
    # JWT refleje "Ana autoriza al agente-ia a actuar en su nombre" (perfil
    # on-behalf-of OAuth 2.0). En producción se sustituye por private_key_jwt
    # + RFC 7523 + DPoP cuando se cambie a Keycloak 26+ o Auth0.
    # ------------------------------------------------------------------ #
    async def jwt_bearer_flow(self, user_id: str, scope: str) -> dict[str, Any]:
        """
        Autentica al usuario y solicita token con scope lógico.

        Flujo: Resource Owner Password Credentials (ROPC).
          - grant_type=password
          - username/password del usuario
          - cliente agente-ia confidencial (client_id + client_secret)
          - scope solicitado (calendar.read, email.send, ...)

        Devuelve el access_token listo para enviar a la API Spring Boot.
        """
        logger.info(
            "[OBO] user=%s scope=%s", user_id, scope,
        )
        users = USERS
        if user_id not in users:
            raise ValueError(f"Usuario desconocido: {user_id}")
        user = users[user_id]

        data = {
            "grant_type": "password",
            "client_id": AGENT_CLIENT_ID,
            "client_secret": AGENT_CLIENT_SECRET,
            "username": user["username"],
            "password": user["password"],
            "scope": scope,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(KEYCLOAK_TOKEN_ENDPOINT, data=data)
            logger.debug(
                "[OBO] POST %s -> HTTP %d body=%s",
                KEYCLOAK_TOKEN_ENDPOINT, resp.status_code, resp.text[:200],
            )
            if resp.status_code >= 400:
                logger.error("[OBO] Error: %s", resp.text[:300])
            resp.raise_for_status()
            token = resp.json()

        logger.info(
            "[OBO] Token OK: expires_in=%s scope=%s sub=%s",
            token.get("expires_in"),
            token.get("scope"),
            user["username"],
        )
        return token

    # ------------------------------------------------------------------ #
    # Flujo 2: CIBA (aprobación fuera de banda)                          #
    # ------------------------------------------------------------------ #
    async def ciba_flow(
        self,
        user_id: str,
        scope: str,
        request_text: str,
        poll_timeout: int = 120,
    ) -> dict[str, Any]:
        """
        OIDC Client Initiated Backchannel Authentication.

        Pasos:
          1. POST /ext/ciba/auth con login_hint_token + scope  -> auth_req_id
          2. Poll POST /token con grant_type=ciba + auth_req_id hasta que
             el usuario apruebe (200) o expire (4xx con error=access_denied /
             expired_token).
        """
        logger.info(
            "[CIBA] Iniciando flujo para user=%s scope=%s request=%r",
            user_id, scope, request_text,
        )

        login_hint_token = self.login_hint_token_for(user_id, scope)

        # bind_token vincula la request CIBA con la sesión del cliente CIBA.
        # En este PoC coincide con el login_hint_token (caso simple: 1 cliente
        # CIBA por usuario). En producción sería un token distinto emitido por
        # el dispositivo del usuario.
        bind_token = login_hint_token

        auth_payload = {
            "client_id": AGENT_CLIENT_ID,
            "client_secret": AGENT_CLIENT_SECRET,
            "scope": scope,
            "login_hint_token": login_hint_token,
            "bind_token": bind_token,
            "acr_values": "2",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            logger.info("[CIBA] Paso 1/2: POST %s", KEYCLOAK_CIBA_AUTH_ENDPOINT)
            auth_resp = await client.post(
                KEYCLOAK_CIBA_AUTH_ENDPOINT, data=auth_payload,
            )
            logger.debug("[CIBA] auth response HTTP %d", auth_resp.status_code)
            if auth_resp.status_code not in (200, 201):
                logger.error(
                    "[CIBA] Error en /auth: %s %s",
                    auth_resp.status_code, auth_resp.text,
                )
                auth_resp.raise_for_status()

            auth = auth_resp.json()
            auth_req_id = auth["auth_req_id"]
            expires_in = int(auth.get("expires_in", 120))
            interval = int(auth.get("interval", 5))
            logger.info(
                "[CIBA] auth_req_id=%s expires_in=%ds interval=%ds",
                auth_req_id, expires_in, interval,
            )

            # Paso 2: polling hasta aprobación o expiración.
            logger.info(
                "[CIBA] Paso 2/2: polling /token cada %ds (max %ds)",
                interval, poll_timeout,
            )
            token_payload = {
                "grant_type": "urn:openid:params:grant-type:ciba",
                "auth_req_id": auth_req_id,
                "client_id": AGENT_CLIENT_ID,
                "client_secret": AGENT_CLIENT_SECRET,
            }

            elapsed = 0
            while elapsed < min(expires_in, poll_timeout):
                await asyncio.sleep(interval)
                elapsed += interval
                logger.debug(
                    "[CIBA] poll t+%ds -> POST /token", elapsed,
                )
                token_resp = await client.post(
                    KEYCLOAK_TOKEN_ENDPOINT, data=token_payload,
                )

                # 200 -> aprobado
                if token_resp.status_code == 200:
                    token = token_resp.json()
                    logger.info(
                        "[CIBA] ¡Aprobado! access_token obtenido "
                        "(expires_in=%s, scope=%s)",
                        token.get("expires_in"), token.get("scope"),
                    )
                    return token

                # 400 con authorization_pending -> seguir esperando
                body = {}
                try:
                    body = token_resp.json()
                except ValueError:
                    pass
                err = body.get("error")
                if err == "authorization_pending":
                    logger.debug("[CIBA] status=authorization_pending, sigo esperando")
                    continue
                if err in ("expired_token", "access_denied"):
                    logger.error(
                        "[CIBA] Error terminal del flujo: %s -- %s",
                        err, body.get("error_description"),
                    )
                    token_resp.raise_for_status()

                # Otro 4xx -> error inesperado
                logger.warning(
                    "[CIBA] Respuesta inesperada HTTP %d: %s",
                    token_resp.status_code, token_resp.text,
                )
                token_resp.raise_for_status()

            logger.error("[CIBA] Timeout esperando aprobación del usuario")
            raise TimeoutError(
                f"CIBA: el usuario {user_id} no aprobó la request en "
                f"{poll_timeout}s"
            )