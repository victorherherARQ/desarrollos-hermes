"""
Tests para config.py — verify_identity() y tabla de usuarios.

TDD: estos tests se escriben ANTES de modificar config.py.
"""
from __future__ import annotations

import pytest

from config import (
    USERS,
    get_user,
    verify_identity,
)


def test_users_tiene_campo_dni_hash():
    """Cada usuario registrado debe tener dni_hash (no DNI en plano)."""
    for user_id, user in USERS.items():
        assert "dni_hash" in user, f"Usuario {user_id} no tiene dni_hash"
        assert isinstance(user["dni_hash"], str)
        assert len(user["dni_hash"]) == 64, "SHA-256 hex debe tener 64 chars"


def test_users_tiene_campo_dob_hash():
    """Cada usuario registrado debe tener dob_hash."""
    for user_id, user in USERS.items():
        assert "dob_hash" in user, f"Usuario {user_id} no tiene dob_hash"
        assert isinstance(user["dob_hash"], str)
        assert len(user["dob_hash"]) == 64


def test_users_tiene_mobile_token():
    """Cada usuario debe tener un mobile_token para el push step-up."""
    for user_id, user in USERS.items():
        assert "mobile_token" in user, f"Usuario {user_id} no tiene mobile_token"
        assert isinstance(user["mobile_token"], str)
        assert len(user["mobile_token"]) > 0


def test_verify_identity_ana_correcto():
    """Ana con su DNI+fecha correctos debe verificar OK."""
    assert verify_identity("ana", "12345678Z", "1990-05-15") is True


def test_verify_identity_dni_incorrecto():
    """DNI equivocado debe fallar la verificación."""
    assert verify_identity("ana", "99999999X", "1990-05-15") is False


def test_verify_identity_dob_incorrecto():
    """Fecha de nacimiento equivocada debe fallar la verificación."""
    assert verify_identity("ana", "12345678Z", "1900-01-01") is False


def test_verify_identity_case_insensitive_dni():
    """DNI en minúsculas debe funcionar (DNI español no es case-sensitive
    para las letras, pero los números sí)."""
    # Asumimos que verify_identity normaliza el DNI
    assert verify_identity("ana", "12345678z", "1990-05-15") is True


def test_verify_identity_usuario_inexistente():
    """Usuario que no existe debe fallar (no explotar)."""
    assert verify_identity("no-existe", "12345678Z", "1990-05-15") is False


def test_verify_identity_luis():
    """Verificar que el segundo usuario también funciona."""
    assert verify_identity("luis", "87654321X", "1985-03-22") is True


def test_dni_hash_no_es_dni_en_plano():
    """El hash guardado NO debe contener el DNI en plano."""
    # hash SHA-256("12345678Z") NO contiene "12345678"
    assert "12345678" not in USERS["ana"]["dni_hash"]
    assert "Z" not in USERS["ana"]["dni_hash"]


def test_get_user_ana():
    """get_user devuelve los datos de Ana."""
    user = get_user("ana")
    assert user is not None
    assert user["name"] == "Ana García"


def test_get_user_inexistente_devuelve_none():
    """get_user con user_id inexistente devuelve None (no explota)."""
    assert get_user("no-existe") is None