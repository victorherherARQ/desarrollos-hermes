"""
Tests para firma RS256 de identity-assertion (KC 26+ requiere algoritmo
asimetrico; HS256 esta hardcodeado a false en AbstractBaseJWTValidator).

Migracion 2026-07-08: el agente firma con su clave privada RSA, y registra
la clave publica (PEM) en el IdP broker `jwt-authorization-grant` de KC
como `config.publicKeySignatureVerifier`.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


# ── Helpers para tests ──────────────────────────────────────────────────────
def _gen_rsa_keypair(tmp_path: Path) -> tuple[bytes, bytes]:
    """Genera keypair RSA 2048 en disco, devuelve (priv_pem, pub_pem)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv, pub


# ── Tests del config: carga de claves ────────────────────────────────────────
def test_load_signing_key_returns_dict_with_private_and_public_keys(tmp_path):
    """load_signing_key() debe devolver dict con 'private' y 'public' en PEM."""
    from config import load_signing_key

    priv, pub = _gen_rsa_keypair(tmp_path)
    priv_file = tmp_path / "agent_signing.pem"
    priv_file.write_bytes(priv)

    signing = load_signing_key(private_key_path=str(priv_file))
    assert signing["private"] == priv
    assert signing["public"] == pub


def test_load_signing_key_autogen_si_no_hay_pem(tmp_path):
    """Si AGENT_SIGNING_KEY_PATH no existe, genera keypair en /tmp persistente."""
    from config import load_signing_key, AGENT_SIGNING_KEY_PATH

    # Limpiamos cualquier pem previo
    Path(AGENT_SIGNING_KEY_PATH).unlink(missing_ok=True)

    signing1 = load_signing_key()
    assert signing1["private"]
    assert signing1["public"]
    # Debe haber persistido el pem
    assert Path(AGENT_SIGNING_KEY_PATH).exists()
    # Segunda llamada debe reusar el mismo key (no rotar en cada arranque)
    signing2 = load_signing_key()
    assert signing1["private"] == signing2["private"]
    # Limpieza
    Path(AGENT_SIGNING_KEY_PATH).unlink(missing_ok=True)


def test_load_signing_key_rechaza_pem_invalido(tmp_path):
    """Si el PEM no se puede parsear, debe lanzar error explicito."""
    from config import load_signing_key

    bad = tmp_path / "bad.pem"
    bad.write_text("-----BEGIN PRIVATE KEY-----\nXXXXXX\n-----END PRIVATE KEY-----\n")

    with pytest.raises(ValueError, match="[Pp]rivate key|[Ii]nvalid|[Pp]arse"):
        load_signing_key(private_key_path=str(bad))


# ── Tests del app: firma RS256 ──────────────────────────────────────────────
def test_sign_identity_assertion_usa_rs256_con_kid(monkeypatch, tmp_path):
    """_sign_identity_assertion debe firmar con RS256 (no HS256)."""
    from config import load_signing_key

    priv, pub = _gen_rsa_keypair(tmp_path)
    priv_file = tmp_path / "agent_signing.pem"
    priv_file.write_bytes(priv)

    # Parcheamos config (NO app) para que _sign_identity_assertion use estas keys
    signing = load_signing_key(private_key_path=str(priv_file))
    import config as config_mod
    monkeypatch.setattr(config_mod, "AGENT_SIGNING_PRIVATE_PEM", signing["private"])
    monkeypatch.setattr(config_mod, "AGENT_SIGNING_PUBLIC_PEM", signing["public"].decode())

    import app as app_mod
    # Tambien parchear la importacion cacheada en app
    monkeypatch.setattr(app_mod, "AGENT_SIGNING_PRIVATE_PEM", signing["private"])

    from config import IDP_ISSUER as IDP
    jwt_str = app_mod._sign_identity_assertion({"sub": "ana", "aud": IDP})
    header = pyjwt.get_unverified_header(jwt_str)
    assert header["alg"] == "RS256"
    assert header.get("kid")
    assert header.get("typ") == "JWT"


def test_sign_identity_assertion_se_puede_verificar_con_public_key(monkeypatch, tmp_path):
    """El JWT firmado con la private key debe verificarse con la public key."""
    from config import load_signing_key

    priv, pub = _gen_rsa_keypair(tmp_path)
    priv_file = tmp_path / "agent_signing.pem"
    priv_file.write_bytes(priv)

    signing = load_signing_key(private_key_path=str(priv_file))
    import config as config_mod
    import app as app_mod
    monkeypatch.setattr(config_mod, "AGENT_SIGNING_PRIVATE_PEM", signing["private"])
    monkeypatch.setattr(app_mod, "AGENT_SIGNING_PRIVATE_PEM", signing["private"])

    from config import IDP_ISSUER as IDP
    payload = {"iss": "broker-idp", "sub": "ana", "aud": IDP}
    jwt_str = app_mod._sign_identity_assertion(payload)

    decoded = pyjwt.decode(
        jwt_str, signing["public"], algorithms=["RS256"], audience=IDP
    )
    assert decoded["sub"] == "ana"


def test_sign_identity_assertion_incluye_claims_de_identidad_rs256(monkeypatch, tmp_path):
    """Los claims custom siguen llegando aunque firmemos con RS256."""
    from config import load_signing_key

    priv, pub = _gen_rsa_keypair(tmp_path)
    priv_file = tmp_path / "agent_signing.pem"
    priv_file.write_bytes(priv)

    signing = load_signing_key(private_key_path=str(priv_file))
    import config as config_mod
    import app as app_mod
    monkeypatch.setattr(config_mod, "AGENT_SIGNING_PRIVATE_PEM", signing["private"])
    monkeypatch.setattr(app_mod, "AGENT_SIGNING_PRIVATE_PEM", signing["private"])

    from config import IDP_ISSUER as IDP
    payload = {
        "iss":             "broker-idp",
        "sub":             "ana",
        "aud":             IDP,
        "dni_verified":    True,
        "dob_verified":    True,
        "identity_method": "dni+dob",
    }
    jwt_str = app_mod._sign_identity_assertion(payload)
    decoded = pyjwt.decode(jwt_str, signing["public"], algorithms=["RS256"], audience=IDP)
    assert decoded["dni_verified"] is True
    assert decoded["dob_verified"] is True
    assert decoded["identity_method"] == "dni+dob"


def test_sign_identity_assertion_no_se_puede_verificar_con_otra_public_key(monkeypatch, tmp_path):
    """Si intentamos verificar con OTRA public key, debe fallar (firma real)."""
    from config import load_signing_key

    priv_agent, _ = _gen_rsa_keypair(tmp_path)
    _, pub_atacante = _gen_rsa_keypair(tmp_path)
    priv_file = tmp_path / "agent_signing.pem"
    priv_file.write_bytes(priv_agent)

    signing = load_signing_key(private_key_path=str(priv_file))
    import config as config_mod
    import app as app_mod
    monkeypatch.setattr(config_mod, "AGENT_SIGNING_PRIVATE_PEM", signing["private"])
    monkeypatch.setattr(app_mod, "AGENT_SIGNING_PRIVATE_PEM", signing["private"])

    jwt_str = app_mod._sign_identity_assertion({"sub": "ana"})
    with pytest.raises(pyjwt.InvalidSignatureError):
        pyjwt.decode(jwt_str, pub_atacante, algorithms=["RS256"])
