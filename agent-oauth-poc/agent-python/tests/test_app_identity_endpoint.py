"""
Tests para POST /agente/auth/identity.

Flujo C (versión identidad):
  1. Cliente (webapp, CLI, IVR) envía DNI + fecha de nacimiento
  2. Agente verifica contra tabla interna (PoC)
  3. Si OK, dispara push step-up al móvil y devuelve challenge_id
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app
from app import PENDING_CHALLENGES


@pytest.fixture(autouse=True)
def limpiar_challenges():
    """Cada test parte con storage vacío."""
    PENDING_CHALLENGES.clear()
    yield
    PENDING_CHALLENGES.clear()


def test_endpoint_identity_existe():
    """La app debe tener POST /agente/auth/identity."""
    rutas = [r.path for r in app.app.routes if hasattr(r, "path")]
    assert "/agente/auth/identity" in rutas


def test_identity_dni_correcto_dispara_challenge():
    """DNI + DOB correctos -> 200 con challenge_id."""
    client = TestClient(app.app)
    r = client.post("/agente/auth/identity", json={
        "user_id": "ana",
        "dni": "12345678Z",
        "dob": "1990-05-15",
        "scope": "calendar.read",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "challenge_id" in body
    assert body["expires_in"] == 120
    assert body["acr"] == "id-claim+push-biometric"


def test_identity_dni_incorrecto_devuelve_401():
    """DNI + DOB incorrectos -> 401."""
    client = TestClient(app.app)
    r = client.post("/agente/auth/identity", json={
        "user_id": "ana",
        "dni": "99999999X",
        "dob": "1990-05-15",
        "scope": "calendar.read",
    })
    assert r.status_code == 401


def test_identity_dob_incorrecto_devuelve_401():
    """DOB incorrecto -> 401."""
    client = TestClient(app.app)
    r = client.post("/agente/auth/identity", json={
        "user_id": "ana",
        "dni": "12345678Z",
        "dob": "1900-01-01",
        "scope": "calendar.read",
    })
    assert r.status_code == 401


def test_identity_usuario_inexistente_devuelve_401():
    """User_id que no existe -> 401 (no 500)."""
    client = TestClient(app.app)
    r = client.post("/agente/auth/identity", json={
        "user_id": "no-existe",
        "dni": "12345678Z",
        "dob": "1990-05-15",
        "scope": "calendar.read",
    })
    assert r.status_code == 401


def test_identity_crea_challenge_en_storage():
    """Tras un identity_exitoso, debe haber un challenge pendiente."""
    client = TestClient(app.app)
    r = client.post("/agente/auth/identity", json={
        "user_id": "ana",
        "dni": "12345678Z",
        "dob": "1990-05-15",
        "scope": "calendar.read",
    })
    assert r.status_code == 200
    challenge_id = r.json()["challenge_id"]
    assert challenge_id in PENDING_CHALLENGES
    challenge = PENDING_CHALLENGES[challenge_id]
    assert challenge["user_id"] == "ana"
    assert challenge["approved"] is False
    assert "identity_assertion" in challenge


def test_identity_payload_incluye_claims_dni_dob():
    """La identity_assertion pendiente debe incluir los claims clave."""
    client = TestClient(app.app)
    r = client.post("/agente/auth/identity", json={
        "user_id": "ana",
        "dni": "12345678Z",
        "dob": "1990-05-15",
        "scope": "calendar.read",
    })
    assert r.status_code == 200
    challenge_id = r.json()["challenge_id"]
    assertion = PENDING_CHALLENGES[challenge_id]["identity_assertion"]
    assert assertion["sub"] == "ana"
    assert assertion["acr"] == "id-claim"
    assert assertion["dni_verified"] is True
    assert assertion["dob_verified"] is True
    assert assertion["identity_method"] == "dni+dob"


def test_identity_assertion_incluye_requested_scope():
    """La identity_assertion debe propagar requested_scope = req.scope.

    Esto es necesario porque KC 26.6.4 broker jwt-bearer ignora el param
    'scope' del grant (BUG) y emite el access_token con TODOS los scopes.
    Propagando requested_scope en la assertion, KC lo copia al access_token
    via IdentityProviderMapper + ClientProtocolMapper.
    Spring filtra authorities por ese claim (no por scope completo).
    """
    client = TestClient(app.app)
    r = client.post("/agente/auth/identity", json={
        "user_id": "ana",
        "dni": "12345678Z",
        "dob": "1990-05-15",
        "scope": "email.send",
    })
    assert r.status_code == 200
    challenge_id = r.json()["challenge_id"]
    assertion = PENDING_CHALLENGES[challenge_id]["identity_assertion"]
    assert assertion["requested_scope"] == "email.send"


def test_identity_assertion_requested_scope_distinto_segun_input():
    """Cada llamada con scope distinto -> requested_scope distinto."""
    client = TestClient(app.app)
    scopes_enviados = []
    for scope in ("calendar.read", "email.send", "calendar.write"):
        r = client.post("/agente/auth/identity", json={
            "user_id": "ana",
            "dni": "12345678Z",
            "dob": "1990-05-15",
            "scope": scope,
        })
        assert r.status_code == 200
        assertion = PENDING_CHALLENGES[r.json()["challenge_id"]]["identity_assertion"]
        scopes_enviados.append(assertion["requested_scope"])
    assert scopes_enviados == ["calendar.read", "email.send", "calendar.write"]


def test_identity_dni_formato_invalido_422():
    """DNI con formato inválido (no 8+letra) -> 422 (Pydantic validation)."""
    client = TestClient(app.app)
    r = client.post("/agente/auth/identity", json={
        "user_id": "ana",
        "dni": "X",  # demasiado corto
        "dob": "1990-05-15",
        "scope": "calendar.read",
    })
    assert r.status_code == 422


def test_identity_dob_formato_invalido_422():
    """DOB con formato no ISO -> 422."""
    client = TestClient(app.app)
    r = client.post("/agente/auth/identity", json={
        "user_id": "ana",
        "dni": "12345678Z",
        "dob": "15/05/1990",  # formato español, no ISO
        "scope": "calendar.read",
    })
    assert r.status_code == 422


def test_identity_scope_requerido():
    """Sin scope -> 422."""
    client = TestClient(app.app)
    r = client.post("/agente/auth/identity", json={
        "user_id": "ana",
        "dni": "12345678Z",
        "dob": "1990-05-15",
    })
    assert r.status_code == 422
