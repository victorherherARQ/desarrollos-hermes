"""
Tests para:
  - POST /agente/auth/identity/push/{challenge_id}  (mock del móvil que aprueba)
  - POST /agente/auth/identity/poll                 (cliente pregunta si push fue aprobado)

Estos dos endpoints cierran el flujo de identidad: el push se aprueba en el
móvil (mockeado por este endpoint) y el cliente hace polling para recoger
el access_token.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import app
from app import PENDING_CHALLENGES


@pytest.fixture(autouse=True)
def limpiar():
    PENDING_CHALLENGES.clear()
    yield
    PENDING_CHALLENGES.clear()


def _crear_challenge(user_id: str = "ana") -> str:
    """Helper: crea un challenge pendiente (como si /auth/identity ya hubiera pasado)."""
    challenge_id = "test-challenge-1234"
    PENDING_CHALLENGES[challenge_id] = {
        "user_id":            user_id,
        "identity_assertion": {"sub": user_id, "iss": "agente-ia"},
        "scope":              "calendar.read",
        "iat":                100,
        "exp":                99999999999,  # muy futuro
        "approved":           False,
        "biometric_used":     False,
    }
    return challenge_id


# ─── Push (mock del móvil) ────────────────────────────────────────────
def test_push_endpoint_existe():
    rutas = [r.path for r in app.app.routes if hasattr(r, "path")]
    assert any("/agente/auth/identity/push/" in p for p in rutas)


def test_push_aprueba_challenge():
    """El endpoint del push debe marcar el challenge como aprobado."""
    challenge_id = _crear_challenge()
    client = TestClient(app.app)
    r = client.post(f"/agente/auth/identity/push/{challenge_id}?biometric=true")
    assert r.status_code == 200
    assert PENDING_CHALLENGES[challenge_id]["approved"] is True
    assert PENDING_CHALLENGES[challenge_id]["biometric_used"] is True


def test_push_con_biometric_false_marca_aprobado_sin_biometria():
    """Si biometric=false, aprobado=True pero biometric_used=False."""
    challenge_id = _crear_challenge()
    client = TestClient(app.app)
    r = client.post(f"/agente/auth/identity/push/{challenge_id}?biometric=false")
    assert r.status_code == 200
    challenge = PENDING_CHALLENGES[challenge_id]
    assert challenge["approved"] is True
    assert challenge["biometric_used"] is False


def test_push_challenge_inexistente_404():
    """Si el challenge_id no existe en storage, devuelve 404."""
    client = TestClient(app.app)
    r = client.post("/agente/auth/identity/push/no-existe")
    assert r.status_code == 404


# ─── Polling (cliente pregunta si push fue aprobado) ──────────────────
def test_poll_endpoint_existe():
    rutas = [r.path for r in app.app.routes if hasattr(r, "path")]
    assert "/agente/auth/identity/poll" in rutas


def test_poll_challenge_pendiente_425():
    """Si el push NO está aprobado, devuelve 425 (Too Early) hasta que apruebe."""
    challenge_id = _crear_challenge()
    client = TestClient(app.app)
    r = client.post(f"/agente/auth/identity/poll?challenge_id={challenge_id}")
    assert r.status_code == 425


def test_poll_challenge_inexistente_404():
    """challenge_id inválido -> 404."""
    client = TestClient(app.app)
    r = client.post("/agente/auth/identity/poll?challenge_id=no-existe")
    assert r.status_code == 404


def test_poll_challenge_expirado_410():
    """Si el challenge expiró, devolver 410 (Gone)."""
    import time
    challenge_id = _crear_challenge()
    PENDING_CHALLENGES[challenge_id]["exp"] = int(time.time()) - 1  # expirado
    client = TestClient(app.app)
    r = client.post(f"/agente/auth/identity/poll?challenge_id={challenge_id}")
    assert r.status_code == 410


@pytest.mark.asyncio
async def test_poll_aprobado_sin_idp_devuelve_502_o_500():
    """
    Si todo OK pero no hay IdP levantado, devuelve error HTTP (502 por conexión
    o 500 por httpx). Lo importante: NO devuelve 200 con datos falsos.
    """
    challenge_id = _crear_challenge()
    PENDING_CHALLENGES[challenge_id]["approved"] = True

    client = TestClient(app.app)
    r = client.post(f"/agente/auth/identity/poll?challenge_id={challenge_id}")

    # Sin IdP levantdo: cualquier 4xx/5xx es aceptable, lo importante
    # es que NO devuelva 200 con un access_token falso.
    assert r.status_code != 200, (
        f"No debe devolver 200 sin IdP levantado, got {r.status_code} {r.text}"
    )


def test_poll_aprobado_firma_assertion_y_llama_idp():
    """
    Si push aprobado, el endpoint debe firmar la assertion JWT y llamar
    a oauth.identity_exchange. Mockeamos httpx para no depender de IdP.
    """
    challenge_id = _crear_challenge()
    PENDING_CHALLENGES[challenge_id]["approved"] = True

    # Mockear la respuesta del IdP
    fake_token_response = {
        "access_token": "eyJ.FAKE.access",
        "expires_in":   300,
        "token_type":   "Bearer",
        "scope":        "calendar.read",
    }
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = fake_token_response
    fake_resp.text = str(fake_token_response)
    fake_resp.raise_for_status = MagicMock()

    class FakeAsyncCtx:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def post(self, url, data=None, **kwargs):
            return fake_resp

    with patch("oauth_client.httpx.AsyncClient", return_value=FakeAsyncCtx()):
        client = TestClient(app.app)
        r = client.post(f"/agente/auth/identity/poll?challenge_id={challenge_id}")

    # Tras éxito, devuelve 200 con access_token
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"] == "eyJ.FAKE.access"
    assert body["expires_in"] == 300
    # El challenge debe haberse limpiado del storage tras éxito
    assert challenge_id not in PENDING_CHALLENGES
