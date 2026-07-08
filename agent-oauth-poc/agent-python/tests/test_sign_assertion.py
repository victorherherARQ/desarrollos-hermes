"""
Tests para _sign_identity_assertion() de app.py.

Helper que firma el payload con PyJWT HS256 usando AGENT_CLIENT_SECRET.
"""
from __future__ import annotations

import jwt as pyjwt
import pytest

from app import _sign_identity_assertion
from config import AGENT_CLIENT_ID, AGENT_CLIENT_SECRET


def test_sign_identity_assertion_existe():
    """app debe tener _sign_identity_assertion."""
    import app
    assert hasattr(app, "_sign_identity_assertion")
    assert callable(app._sign_identity_assertion)


def test_sign_identity_assertion_devuelve_string_compact():
    """Debe devolver un JWT en formato compacto (xxx.yyy.zzz)."""
    jwt_str = _sign_identity_assertion({"sub": "ana", "iss": "agente"})
    assert isinstance(jwt_str, str)
    parts = jwt_str.split(".")
    assert len(parts) == 3, f"JWT compacto debe tener 3 partes, got {len(parts)}"


def test_sign_identity_assertion_se_puede_verificar_con_misma_clave():
    """El JWT firmado debe poder verificarse con la misma client_secret."""
    import time
    iat = int(time.time())
    payload = {
        "iss":  AGENT_CLIENT_ID,
        "sub":  "ana",
        "aud":  "idp-realm",
        "iat":  iat,
        "exp":  iat + 120,
        "jti":  "test-jti",
    }
    jwt_str = _sign_identity_assertion(payload)
    decoded = pyjwt.decode(
        jwt_str,
        AGENT_CLIENT_SECRET,
        algorithms=["HS256"],
        audience="idp-realm",
    )
    assert decoded["sub"] == "ana"
    assert decoded["iss"] == AGENT_CLIENT_ID
    assert decoded["aud"] == "idp-realm"


def test_sign_identity_assertion_incluye_claims_de_identidad():
    """El JWT firmado debe incluir los claims que le pasemos."""
    payload = {
        "iss":              AGENT_CLIENT_ID,
        "sub":              "ana",
        "dni_verified":     True,
        "dob_verified":     True,
        "identity_method":  "dni+dob",
    }
    jwt_str = _sign_identity_assertion(payload)
    decoded = pyjwt.decode(
        jwt_str,
        AGENT_CLIENT_SECRET,
        algorithms=["HS256"],
    )
    assert decoded["dni_verified"] is True
    assert decoded["dob_verified"] is True
    assert decoded["identity_method"] == "dni+dob"


def test_sign_identity_assertion_incluye_kid_en_header():
    """El header debe incluir 'kid' = AGENT_CLIENT_ID para que el IdP
    sepa qué clave usar para verificar."""
    jwt_str = _sign_identity_assertion({"sub": "ana"})
    header = pyjwt.get_unverified_header(jwt_str)
    assert header["alg"] == "HS256"
    assert header.get("kid") == AGENT_CLIENT_ID
    assert header.get("typ") == "JWT"


def test_sign_identity_assertion_no_se_puede_verificar_con_otra_clave():
    """Si intentamos verificar con otra clave, debe fallar."""
    jwt_str = _sign_identity_assertion({"sub": "ana"})
    with pytest.raises(pyjwt.InvalidSignatureError):
        pyjwt.decode(jwt_str, "otra-clave-distinta", algorithms=["HS256"])
