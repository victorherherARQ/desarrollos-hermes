"""
Tests para _sign_identity_assertion() de app.py.

El agente firma su identity-assertion con RS256 (clave privada RSA). KC 26+
verifica la firma con la clave publica registrada en el IdP broker.

Tests detallados de RS256 con kid + keypair vars:
  - tests/test_sign_assertion_rs256.py (migracion 2026-07-08)
"""
from __future__ import annotations

import jwt as pyjwt
import pytest

from app import _sign_identity_assertion
from config import AGENT_SIGNING_PUBLIC_PEM, IDP_ISSUER


def test_sign_identity_assertion_existe():
    """app debe tener _sign_identity_assertion."""
    import app
    assert hasattr(app, "_sign_identity_assertion")
    assert callable(app._sign_identity_assertion)


def test_sign_identity_assertion_devuelve_string_compact():
    """Debe devolver un JWT en formato compacto (xxx.yyy.zzz)."""
    jwt_str = _sign_identity_assertion({"sub": "ana", "iss": "broker"})
    assert isinstance(jwt_str, str)
    parts = jwt_str.split(".")
    assert len(parts) == 3, f"JWT compacto debe tener 3 partes, got {len(parts)}"


def test_sign_identity_assertion_se_puede_verificar_con_public_key():
    """El JWT firmado debe poder verificarse con la public key del agente."""
    payload = {
        "iss": "broker-idp",
        "sub": "ana",
        "aud": IDP_ISSUER,
    }
    jwt_str = _sign_identity_assertion(payload)
    decoded = pyjwt.decode(
        jwt_str,
        AGENT_SIGNING_PUBLIC_PEM,
        algorithms=["RS256"],
        audience=IDP_ISSUER,
    )
    assert decoded["sub"] == "ana"


def test_sign_identity_assertion_incluye_claims_de_identidad():
    """El JWT firmado debe incluir los claims que le pasemos."""
    payload = {
        "iss":             "broker-idp",
        "sub":             "ana",
        "aud":             IDP_ISSUER,
        "dni_verified":    True,
        "dob_verified":    True,
        "identity_method": "dni+dob",
    }
    jwt_str = _sign_identity_assertion(payload)
    decoded = pyjwt.decode(
        jwt_str, AGENT_SIGNING_PUBLIC_PEM, algorithms=["RS256"], audience=IDP_ISSUER,
    )
    assert decoded["dni_verified"] is True
    assert decoded["dob_verified"] is True
    assert decoded["identity_method"] == "dni+dob"


def test_sign_identity_assertion_incluye_kid_en_header():
    """El header debe incluir 'kid' para que el IdP sepa que clave usar."""
    jwt_str = _sign_identity_assertion({"sub": "ana"})
    header = pyjwt.get_unverified_header(jwt_str)
    assert header["alg"] == "RS256"
    assert header.get("kid")
    assert header.get("typ") == "JWT"


def test_sign_identity_assertion_no_se_puede_verificar_con_otra_public_key(tmp_path):
    """Si intentamos verificar con otra public key, debe fallar (firma RSA real)."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    # Generamos una public key atacante DIFERENTE
    atacante_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    atacante_pub = atacante_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    jwt_str = _sign_identity_assertion({"sub": "ana"})
    with pytest.raises(pyjwt.InvalidSignatureError):
        pyjwt.decode(jwt_str, atacante_pub, algorithms=["RS256"])
