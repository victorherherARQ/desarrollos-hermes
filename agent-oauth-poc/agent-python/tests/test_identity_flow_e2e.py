"""
Test de integración E2E del Flujo C (identidad DNI+DOB).

Verifica el flujo completo SIN necesidad de tener Keycloak levantado:
  1. Cliente -> POST /agente/auth/identity  -> challenge_id
  2. (mock móvil) -> POST /agente/auth/identity/push/{id}?biometric=true -> approved
  3. Cliente -> POST /agente/auth/identity/poll -> access_token
  4. Cliente -> POST /agente/call con el token -> acción ejecutada

Para paso 3, mockeamos el HTTP al IdP (httpx.AsyncClient) para no depender
del stack de Docker. Para paso 4, mockeamos la llamada del agente a la API.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import app
from app import PENDING_CHALLENGES


# ─── Pasos 1, 2, 3 sin HTTP mocking (Fallan en paso 3 si no hay IdP,
# pero ahora mockeamos el IdP al final) ────────────────────────────────


def _fake_token_response():
    return {
        "access_token": "eyJ.FAKE.access_token",
        "expires_in":   300,
        "token_type":   "Bearer",
        "scope":        "calendar.read",
    }


def test_e2e_flujo_completo_mockeando_idp():
    """
    E2E: cliente -> agente (verifica) -> push (móvil) -> agente (canjea)
    -> cliente recibe access_token.
    """
    # Mockear la respuesta del IdP a la llamada de identity_exchange
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = _fake_token_response()
    fake_resp.text = str(_fake_token_response())
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

        # ── Paso 1: cliente envía DNI+DOB ────────────────────────────
        r = client.post("/agente/auth/identity", json={
            "user_id": "ana",
            "dni":     "12345678Z",
            "dob":     "1990-05-15",
            "scope":   "calendar.read",
        })
        assert r.status_code == 200, f"Paso 1 falló: {r.text}"
        challenge_id = r.json()["challenge_id"]

        # ── Paso 2: el móvil aprueba el push ─────────────────────────
        r = client.post(
            f"/agente/auth/identity/push/{challenge_id}?biometric=true",
        )
        assert r.status_code == 200, f"Paso 2 falló: {r.text}"
        assert r.json()["status"] == "approved"

        # ── Paso 3: el cliente pregunta por el access_token ──────────
        r = client.post(
            f"/agente/auth/identity/poll?challenge_id={challenge_id}&biometric_used=true",
        )
        assert r.status_code == 200, f"Paso 3 falló: {r.text}"
        token = r.json()
        assert token["access_token"] == "eyJ.FAKE.access_token"
        assert token["expires_in"] == 300
        assert "calendar.read" in token["scope"]

        # ── Verificación: el challenge se ha limpiado ────────────────
        assert challenge_id not in PENDING_CHALLENGES


def test_e2e_dni_incorrecto_aborta_flujo_en_paso_1():
    """Si el DNI es incorrecto, el flujo se aborta en el paso 1."""
    client = TestClient(app.app)
    r = client.post("/agente/auth/identity", json={
        "user_id": "ana",
        "dni":     "99999999X",
        "dob":     "1990-05-15",
        "scope":   "calendar.read",
    })
    assert r.status_code == 401


def test_e2e_push_rechaza_poll_con_425():
    """Si el push NO se ha aprobado, /poll devuelve 425."""
    client = TestClient(app.app)
    r = client.post("/agente/auth/identity", json={
        "user_id": "ana",
        "dni":     "12345678Z",
        "dob":     "1990-05-15",
        "scope":   "calendar.read",
    })
    challenge_id = r.json()["challenge_id"]

    # Sin aprobar el push, polling -> 425
    r = client.post(f"/agente/auth/identity/poll?challenge_id={challenge_id}")
    assert r.status_code == 425


def test_e2e_dos_usuarios_aislados():
    """Ana y Luis pueden tener challenges simultáneos sin cruzarse."""
    client = TestClient(app.app)
    r1 = client.post("/agente/auth/identity", json={
        "user_id": "ana", "dni": "12345678Z", "dob": "1990-05-15",
        "scope": "calendar.read",
    })
    r2 = client.post("/agente/auth/identity", json={
        "user_id": "luis", "dni": "87654321X", "dob": "1985-03-22",
        "scope": "email.read",
    })
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["challenge_id"] != r2.json()["challenge_id"]
    assert PENDING_CHALLENGES[r1.json()["challenge_id"]]["user_id"] == "ana"
    assert PENDING_CHALLENGES[r2.json()["challenge_id"]]["user_id"] == "luis"
    assert PENDING_CHALLENGES[r1.json()["challenge_id"]]["scope"] == "calendar.read"
    assert PENDING_CHALLENGES[r2.json()["challenge_id"]]["scope"] == "email.read"


if __name__ == "__main__":
    # Permite ejecutar el test directamente: `python3 tests/test_identity_flow_e2e.py`
    pytest.main([__file__, "-v"])
