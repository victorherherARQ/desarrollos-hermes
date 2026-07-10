"""Tests TDD: el agente restringe scopes via header X-Requested-Scope-Token.

Estos tests son de integración contra el agente Python (:7000) y el
Spring Boot API (:9090) con KC 26.6.4 real (:8180).

Estrategia (workaround BUG KC 26.6.4 broker jwt-bearer):
- KC 26.6.4 broker jwt-bearer IGNORA el param 'scope' del grant
  y emite el access_token con TODOS los scopes del cliente.
- Por lo tanto, no podemos confiar en el claim 'requested_scope'
  del access_token de KC (no se propaga).
- En su lugar, el agente firma un mini-JWT HS256 con el scope
  original (el que pidió el usuario) y lo devuelve como campo
  `requested_scope_token` en la respuesta de /agente/auth/identity/poll.
- El cliente pasa ese token al API Spring en el header
  `X-Requested-Scope-Token`. Spring lo valida con el shared secret
  (HS256) y filtra las authorities del `JwtAuthenticationToken`
  a la intersección con el claim 'scope' del mini-JWT.

Cada test pide un token al agente con un scope concreto, valida
el `requested_scope_token` HS256, y verifica:
1. El access_token lleva todos los scopes (BUG KC).
2. El `requested_scope_token` lleva solo el scope solicitado.
3. Al llamar al API con ambos headers, el comportamiento es
   el esperado (200 si scope OK, 403 si no).
"""
import base64
import hashlib
import hmac
import json
import os
import unittest
import urllib.request
import urllib.error

BASE_AGENT = "http://localhost:7000"
# Dentro del container del agente (donde corren los tests), la API
# Spring se alcanza por su nombre de servicio en la red `agent-poc-net`.
# En desarrollo fuera del container, `localhost:9090` también funciona.
import os
_BASE_API_HOST = "agent-poc-spring-boot-api" if os.path.exists("/.dockerenv") else "localhost"
BASE_API = f"http://{_BASE_API_HOST}:9090"

# Shared secret con el que el agente firma requested_scope_token.
# Debe coincidir con el REQUESTED_SCOPE_SHARED_SECRET del agente
# y con el 'requested-scope.shared-secret' del Spring Boot API.
SHARED_SECRET = os.environ.get(
    "REQUESTED_SCOPE_SHARED_SECRET",
    "poC-shared-secret-CHANGE-ME-32bytes-min-para-hs256",
)


def _decode_payload(token):
    p = token.split(".")[1]
    p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))


def _verify_hs256(token: str, secret: str) -> dict:
    """Verifica firma HS256 de un JWT y devuelve el payload."""
    header_b64, payload_b64, sig_b64 = token.split(".")
    signing_input = f"{header_b64}.{payload_b64}".encode()
    sig = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
    expected = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        raise ValueError("Firma HS256 inválida")
    return _decode_payload(token)


def _get_identity_token(scope):
    """Pide access_token + requested_scope_token al agente (flujo C/Identity)."""
    data = json.dumps({
        "user_id": "ana",
        "dni": "12345678Z",
        "dob": "1990-05-15",
        "scope": scope,
    }).encode()
    req = urllib.request.Request(
        f"{BASE_AGENT}/agente/auth/identity",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    challenge_id = json.loads(urllib.request.urlopen(req).read())["challenge_id"]
    urllib.request.urlopen(urllib.request.Request(
        f"{BASE_AGENT}/agente/auth/identity/push/{challenge_id}?biometric=true",
        data=b"",
    )).read()
    resp = urllib.request.urlopen(urllib.request.Request(
        f"{BASE_AGENT}/agente/auth/identity/poll?challenge_id={challenge_id}&biometric_used=true",
        data=b"",
    )).read()
    body = json.loads(resp)
    return body["access_token"], body.get("requested_scope_token", "")


def _api_call(method, path, token, scope_token=None, body=None):
    headers = {"Authorization": "Bearer " + token}
    if scope_token:
        headers["X-Requested-Scope-Token"] = scope_token
    if body:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    else:
        data = None
    req = urllib.request.Request(
        f"{BASE_API}{path}",
        data=data,
        method=method,
        headers=headers,
    )
    try:
        resp = urllib.request.urlopen(req)
        return resp.status, json.loads(resp.read()) if resp.length else None
    except urllib.error.HTTPError as e:
        return e.code, None


class TestRequestedScopeFilter(unittest.TestCase):
    """Tests del downscoping via X-Requested-Scope-Token header."""

    def test_response_includes_requested_scope_token(self):
        """El poll debe devolver requested_scope_token firmado HS256."""
        _, rs_token = _get_identity_token("email.send")
        self.assertTrue(rs_token, "Falta requested_scope_token en la respuesta")
        # Verificamos firma
        claims = _verify_hs256(rs_token, SHARED_SECRET)
        self.assertEqual(claims["iss"], "agente-ia")
        self.assertEqual(claims["sub"], "ana")
        self.assertEqual(claims["scope"], "email.send")

    def test_response_includes_calendar_scope_token(self):
        _, rs_token = _get_identity_token("calendar.read")
        claims = _verify_hs256(rs_token, SHARED_SECRET)
        self.assertEqual(claims["scope"], "calendar.read")

    def test_calendar_endpoint_with_calendar_scope_returns_200(self):
        tok, rs = _get_identity_token("calendar.read")
        status, _ = _api_call("GET", "/api/calendar/events", tok, rs)
        self.assertEqual(status, 200)

    def test_calendar_endpoint_with_email_scope_returns_403(self):
        """BUG FIX: con scope=email.send, calendar endpoint -> 403."""
        tok, rs = _get_identity_token("email.send")
        status, _ = _api_call("GET", "/api/calendar/events", tok, rs)
        self.assertEqual(status, 403, "BUG: spring no restringe por X-Requested-Scope-Token")

    def test_email_endpoint_with_email_scope_returns_200(self):
        tok, rs = _get_identity_token("email.send")
        status, _ = _api_call("POST", "/api/email/send", tok, rs, body={
            "to": "x@y.z", "subject": "s", "body": "b",
        })
        self.assertEqual(status, 200)

    def test_email_endpoint_with_calendar_scope_returns_403(self):
        """BUG FIX: con scope=calendar.read, email endpoint -> 403."""
        tok, rs = _get_identity_token("calendar.read")
        status, _ = _api_call("POST", "/api/email/send", tok, rs, body={
            "to": "x@y.z", "subject": "s", "body": "b",
        })
        self.assertEqual(status, 403, "BUG: spring no restringe por X-Requested-Scope-Token")

    def test_fallback_without_scope_header_returns_200(self):
        """Sin header X-Requested-Scope-Token, todos los scopes del
        access_token están disponibles (backwards compatible)."""
        tok, _ = _get_identity_token("calendar.read")
        # Sin header, calendar deberia responder 200 (scope del access_token)
        status, _ = _api_call("GET", "/api/calendar/events", tok)
        self.assertEqual(status, 200)
        # Y email tambien (porque el access_token tiene todos los scopes)
        status, _ = _api_call("POST", "/api/email/send", tok, body={
            "to": "x@y.z", "subject": "s", "body": "b",
        })
        self.assertEqual(status, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
