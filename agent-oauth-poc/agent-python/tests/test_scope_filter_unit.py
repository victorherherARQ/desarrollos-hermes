"""Unit tests: la lógica de filtrado de authorities en Spring.

Estos tests no ejecutan Spring — validan el CONCEPTO de filtrado
verificando que un JWT con `requested_scope` correctamente intersectado
contra `scope` produce las authorities esperadas.

Si Spring aplica ScopeAuthoritiesConverter con el mismo algoritmo,
los authorities de Spring coincidirán con estos tests.
"""
import base64
import json
import pytest


def _decode_payload(token):
    p = token.split(".")[1]
    p += "=" * (-len(p) % 4)
    return json.loads(base64.urlsafe_b64decode(p))


def _filter_authorities(scope_claim, requested_scope_claim):
    """Replica la lógica de ScopeAuthoritiesConverter.convert() en Java."""
    # 1) Parse scope claim (space-separated)
    if scope_claim:
        scopes = set(scope_claim.split())
    else:
        scopes = set()

    # 2) Filter by requested_scope
    if requested_scope_claim:
        requested = set(requested_scope_claim.split())
        scopes = scopes & requested

    # 3) Convert to SCOPE_ prefixed authorities
    return sorted(f"SCOPE_{s}" for s in scopes)


def test_filter_no_requested_scope_returns_all():
    """Sin requested_scope: todas las authorities (sin filtro)."""
    scope = "email.send calendar.read profile"
    result = _filter_authorities(scope, None)
    assert result == ["SCOPE_calendar.read", "SCOPE_email.send", "SCOPE_profile"]


def test_filter_requested_scope_intersects():
    """Con requested_scope: solo las authorities que están en ambos."""
    scope = "email.send calendar.read profile"
    requested = "calendar.read"
    result = _filter_authorities(scope, requested)
    assert result == ["SCOPE_calendar.read"]


def test_filter_no_matching_requested_scope_returns_empty():
    """Si requested_scope no matchea con scope -> authorities vacías."""
    scope = "email.send calendar.read"
    requested = "admin.super"
    result = _filter_authorities(scope, requested)
    assert result == []


def test_filter_multiple_requested_scopes():
    """Múltiples scopes en requested_scope."""
    scope = "email.send calendar.read calendar.write profile"
    requested = "calendar.read calendar.write"
    result = _filter_authorities(scope, requested)
    assert result == ["SCOPE_calendar.read", "SCOPE_calendar.write"]


def test_filter_blank_requested_scope_ignored():
    """requested_scope vacío/blanco: no filtra."""
    scope = "email.send calendar.read"
    result = _filter_authorities(scope, "")
    assert "SCOPE_calendar.read" in result
    assert "SCOPE_email.send" in result


if __name__ == "__main__":
    test_filter_no_requested_scope_returns_all()
    test_filter_requested_scope_intersects()
    test_filter_no_matching_requested_scope_returns_empty()
    test_filter_multiple_requested_scopes()
    test_filter_blank_requested_scope_ignored()
    print("5/5 unit tests OK")