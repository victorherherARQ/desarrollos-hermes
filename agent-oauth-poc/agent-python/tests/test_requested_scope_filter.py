"""Tests TDD: el agente restringe scopes via claim requested_scope.

Estos tests son de integración contra el agente Python (:7000) y el
Spring Boot API (:9090) con KC 26.6.4 real (:8180).

Cada test pide un token al agente con un scope concreto, decodifica
el access_token y verifica:
1. El claim requested_scope esta presente y es el scope solicitado.
2. Al llamar al API endpoint calendar o email, el comportamiento es
   el esperado (200 si scope OK, 403 si no).
"""
import base64
import json
import sys
import unittest
import urllib.request
import urllib.error

BEARER = "Bearer "
BASE_AGENT = "http://localhost:7000"
BASE_API = "http://localhost:9090"


def _decode_payload(token):
    p = token.split(".")[1]
    p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))


def _get_token(scope):
    """Pide access_token al agente con un scope concreto."""
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
    return json.loads(resp)["access_token"]


def _api_call(method, path, token, body=None):
    headers = {"Authorization": BEARER + token}
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
    """Tests rojos: requested_scope debe restringir el access_token."""

    def test_token_includes_requested_scope_claim(self):
        """El access_token debe tener un claim requested_scope."""
        tok = _get_token("email.send")
        payload = _decode_payload(tok)
        self.assertIn("requested_scope", payload, "BUG: el access_token no incluye requested_scope")
        self.assertEqual(payload["requested_scope"], "email.send")

    def test_token_includes_calendar_scope_claim(self):
        """El access_token debe tener un claim requested_scope=calendar.read."""
        tok = _get_token("calendar.read")
        payload = _decode_payload(tok)
        self.assertEqual(payload["requested_scope"], "calendar.read")

    def test_calendar_endpoint_with_calendar_scope_returns_200(self):
        tok = _get_token("calendar.read")
        status, _ = _api_call("GET", "/api/calendar/events", tok)
        self.assertEqual(status, 200)

    def test_calendar_endpoint_with_email_scope_returns_403(self):
        """BUG FIX: con requested_scope=email.send, calendar endpoint -> 403."""
        tok = _get_token("email.send")
        status, _ = _api_call("GET", "/api/calendar/events", tok)
        self.assertEqual(status, 403, "BUG: spring no restringe por requested_scope")

    def test_email_endpoint_with_email_scope_returns_200(self):
        tok = _get_token("email.send")
        status, _ = _api_call("POST", "/api/email/send", tok, body={
            "to": "x@y.z", "subject": "s", "body": "b",
        })
        self.assertEqual(status, 200)

    def test_email_endpoint_with_calendar_scope_returns_403(self):
        """BUG FIX: con requested_scope=calendar.read, email endpoint -> 403."""
        tok = _get_token("calendar.read")
        status, _ = _api_call("POST", "/api/email/send", tok, body={
            "to": "x@y.z", "subject": "s", "body": "b",
        })
        self.assertEqual(status, 403, "BUG: spring no restringe por requested_scope")


if __name__ == "__main__":
    unittest.main(verbosity=2)