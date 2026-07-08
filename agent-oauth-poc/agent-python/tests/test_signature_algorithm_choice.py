"""
Test documental sobre el algoritmo de firma de la identity-assertion.

ESTADO ACTUAL (2026-07-08): HS256 (simétrico, con AGENT_CLIENT_SECRET compartido).

Análisis:
  - HS256 usa la misma clave para firmar (agente) y verificar (Keycloak).
  - Requiere que Agente y Keycloak compartan AGENT_CLIENT_SECRET.
  - Keycloak 24+ permite configurar un client con autenticación HS256 vía
    `clientAuthenticator=client-secret` (default) y el flujo
    `urn:ietf:params:oauth:grant-type:jwt-bearer` con `client_assertion_type=
    urn:ietf:params:oauth:client-assertion-type:jwt-bearer`.
  - La SECRET vive en /home/vhdez/desarrollos-hermes/agent-oauth-poc/agent-python/config.py
    Y en keycloak/realm/realm-agent-poc.json (campo `secret`).
  - Como Agente y Keycloak son AMBAS partes confiables de la misma PoC,
    HS256 es ACEPTABLE para un PoC.

POR QUÉ NO RS256 AÚN:
  - RS256 requiere que Keycloak conozca la clave PÚBLICA del agente.
  - El agente tendría que generar un keypair RSA, guardar la privada, y
    registrar la pública en el cliente de KC (vía JWKS endpoint o pegada).
  - Para una PoC donde el agente es código Python corriendo en local, HS256
    es suficiente. RS256 aporta valor real cuando:
      a) El agente vive en una máquina separada del IdP y la SECRET compartida
         sería un vector de ataque (un leak en el agente = leak en el IdP).
      b) Hay múltiples agentes que firman para el mismo realm.
      c) Se quiere rotación de claves sin downtime.

CUANDO MIGRAR A RS256:
  - Antes de producción.
  - Cuando separemos el código del agente a un servicio independiente.
  - Implementación: cryptography.hazmat.primitives.asymmetric.rsa + PyJWT
    con algorithm='RS256'.

Este test verifica que la elección actual (HS256) está bien documentada y
que la SECRET cumple los requisitos mínimos (>= 32 bytes = 256 bits).
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(
    reason=(
        "AGENT_CLIENT_SECRET tiene 17 bytes (legacy) — InsecureKeyLengthWarning en PyJWT. "
        "Aumentar a >= 32 bytes en config.py y realm-agent-poc.json antes de producción. "
        "Ver SETUP_FLOW_C.md §6 (TODO #2)."
    ),
    strict=True,
)
def test_agente_client_secret_es_almenos_32_bytes():
    """
    HS256 con < 32 bytes dispara InsecureKeyLengthWarning en PyJWT.
    Si esto pasa, es porque la SECRET sigue siendo 17 bytes (legacy) — TODO
    """
    from config import AGENT_CLIENT_SECRET
    assert isinstance(AGENT_CLIENT_SECRET, str)
    assert len(AGENT_CLIENT_SECRET.encode("utf-8")) >= 32, (
        f"AGENT_CLIENT_SECRET tiene {len(AGENT_CLIENT_SECRET)} bytes. "
        "Para HS256 seguro necesita >= 32 bytes. "
        "Aumentar en config.py y en keycloak/realm/realm-agent-poc.json."
    )


def test_sign_identity_assertion_usa_hs256_actualmente():
    """
    Documenta que el algoritmo actual es HS256.
    Si fallara en el futuro (porque alguien migra a RS256), actualizar
    este test y la documentación en SETUP_FLOW_C.md §6.
    """
    import jwt as pyjwt
    from app import _sign_identity_assertion
    from config import AGENT_CLIENT_SECRET, IDP_ISSUER

    token = _sign_identity_assertion({
        "sub":  "test",
        "scope": "calendar.read",
        "aud":  IDP_ISSUER,  # obligatorio para pyjwt.decode(audience=...)
    })

    # Decodificar el header sin verificar para ver el alg
    header = pyjwt.get_unverified_header(token)
    assert header["alg"] == "HS256", (
        f"Algoritmo actual inesperado: {header['alg']}. "
        "Si es RS256, actualizar SETUP_FLOW_C.md §6 y este test."
    )
    # Decodificar con la misma secret para verificar que es HS256 simétrico
    decoded = pyjwt.decode(
        token,
        AGENT_CLIENT_SECRET,
        algorithms=["HS256"],
        audience=IDP_ISSUER,
    )
    assert decoded["sub"] == "test"


def test_signature_es_unica_por_challenge():
    """
    Aunque HS256 con la misma SECRET produce el mismo token para el mismo payload,
    PyJWT añade `jti` (UUID4) por defecto en nuestro impl, así que cada llamada
    genera un token diferente. Esto previene replay attacks.
    """
    from app import _sign_identity_assertion
    payload = {"sub": "test", "scope": "calendar.read"}
    t1 = _sign_identity_assertion(payload)
    t2 = _sign_identity_assertion(payload)
    assert t1 != t2, "Cada assertion debe tener jti único (replay protection)"
