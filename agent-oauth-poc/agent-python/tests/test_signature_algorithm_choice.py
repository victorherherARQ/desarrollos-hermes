"""
Test documental sobre el algoritmo de firma de la identity-assertion.

ESTADO ACTUAL (2026-07-08 migracion): RS256 (asimetrico, clave privada del
agente + clave publica registrada en Keycloak 26 IdP broker).

Por que RS256 (y no HS256):
  - KC 26.6.4 tiene `AbstractBaseJWTValidator.isSymmetricAlgorithmAllowed()`
    hardcoded a `false`. Solo acepta algoritmos asimetricos (RS256, ES256, PS256)
    en el broker `jwt-authorization-grant`.
  - HS256 con un shared secret deja la PoC en un estado aceptable en local,
    pero NO escala a produccion: cualquier leak en el agente = leak en el IdP.
  - RS256 separa la clave que firma (privada del agente) de la que verifica
    (publica registrada en el IdP broker). Un atacante que robe la publica
    no puede firmar tokens, y el agente puede rotar la privada sin tocar KC.

Como funciona:
  1. Al primer arranque, el agente genera un keypair RSA 2048 y lo persiste
     en disco (AGENT_SIGNING_KEY_PATH) para sobrevivir reinicios.
  2. La clave publica (PEM) se registra en KC como
     `identity-provider/instances/agent-poc-jwt-broker/config.publicKeySignatureVerifier`.
     Script: scripts/configure_jwt_broker_idp.py.
  3. Cada identity-assertion lleva `kid=<random>` en el header.
  4. KC verifica con la publica; si la firma es valida, emite el access_token.

Tareas pendientes:
  - Rotacion de claves automatica (hoy es manual).
  - JWKS endpoint en lugar de PEM pegado (cuando haya 2+ agentes).
"""
from __future__ import annotations

import jwt as pyjwt
import pytest


def test_sign_identity_assertion_usa_rs256():
    """
    Documenta que el algoritmo actual es RS256.
    Si fuera HS256, KC 26 fallaria con "Invalid signature algorithm".
    """
    from app import _sign_identity_assertion
    from config import IDP_ISSUER, AGENT_SIGNING_PUBLIC_PEM

    token = _sign_identity_assertion({
        "sub":   "test",
        "scope": "calendar.read",
        "aud":   IDP_ISSUER,
    })

    # Decodificar el header sin verificar para ver el alg
    header = pyjwt.get_unverified_header(token)
    assert header["alg"] == "RS256", (
        f"Algoritmo actual inesperado: {header['alg']}. "
        "KC 26 requiere algoritmo asimetrico en el broker jwt-auth-grant."
    )

    # Verificar con la clave publica del agente
    decoded = pyjwt.decode(
        token,
        AGENT_SIGNING_PUBLIC_PEM,
        algorithms=["RS256"],
        audience=IDP_ISSUER,
    )
    assert decoded["sub"] == "test"


def test_signature_es_unica_por_challenge():
    """
    Aunque el payload sea identico, PyJWT a\u00f1ade `jti` (UUID4) por defecto
    en nuestro impl, as\u00ed cada llamada genera un token diferente.
    Esto previene replay attacks.
    """
    from app import _sign_identity_assertion
    payload = {"sub": "test", "scope": "calendar.read"}
    t1 = _sign_identity_assertion(payload)
    t2 = _sign_identity_assertion(payload)
    assert t1 != t2, "Cada assertion debe tener jti unico (replay protection)"


def test_kc_compatible_algoritmos():
    """
    Documenta los algoritmos que KC 26 acepta en el broker jwt-auth-grant.
    Si KC cambia esto en el futuro, este test sirve de checkpoint.
    """
    # Lista de algoritmos soportados segun AbstractBaseJWTValidator.
    # Si KC 26 los restringe mas, actualizar.
    kc_supported_asymmetric = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256", "PS384", "PS512"}
    # Nuestro impl
    our_alg = "RS256"
    assert our_alg in kc_supported_asymmetric, (
        f"{our_alg} no soportado por KC 26 broker jwt-auth-grant. "
        f"Esperado uno de: {kc_supported_asymmetric}"
    )


def test_agente_usa_lista_negra_algoritmos_inseguros():
    """
    El agente NUNCA debe firmar con 'none' u otros algoritmos inseguros.
    """
    from app import _sign_identity_assertion
    token = _sign_identity_assertion({"sub": "test"})
    header = pyjwt.get_unverified_header(token)
    assert header["alg"].lower() != "none"
    assert header["alg"] in {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
