"""
Configuración del agente IA — Versión A+B+C portable.

Apunta a los servicios del PoC:
  - Keycloak / Azure B2C / Auth0 / cualquier IdP OIDC estándar
  - Spring API (http://spring-boot-api:9090) -- API protegida que el agente
    invoca en nombre del usuario

Las URLs usan nombres de servicio Docker (no localhost) cuando el agente vive
en la misma red compose que los demás componentes. Para Azure B2C, las URLs
se leen de variables de entorno.

Variables de entorno reconocidas:
  IDP_ISSUER                  (default: http://keycloak:8080/realms/agent-poc)
  CLIENT_MOCK_REDIRECT_URI    (default: http://localhost:3000/callback)
"""

import os

# ─── IdP (Keycloak por defecto; override por env para B2C) ─────────────────
IDP_ISSUER = os.getenv(
    "IDP_ISSUER",
    "http://keycloak:8080/realms/agent-poc",
)

# Detección de tipo de IdP: si el issuer contiene "ciamlogin.com" o
# "b2clogin.com" usamos paths de Azure B2C; en otro caso Keycloak paths.
_ISSUER_LC = IDP_ISSUER.lower()
_IS_B2C = "ciamlogin.com" in _ISSUER_LC or "b2clogin.com" in _ISSUER_LC

if _IS_B2C:
    # Azure B2C External ID / B2C legacy
    # En B2C el user flow es parte del path: /<tenant-subdomain>/<user-flow-name>
    # Para esta PoC asumimos un solo user flow "signup_signin_v1"
    _B2C_USER_FLOW = os.getenv("B2C_USER_FLOW", "signup_signin_v1")
    IDP_AUTHORIZE_ENDPOINT = (
        f"{IDP_ISSUER.rstrip('/')}/oauth2/v2.0/authorize"
        f"?p={_B2C_USER_FLOW}"
    )
    IDP_TOKEN_ENDPOINT = f"{IDP_ISSUER.rstrip('/')}/oauth2/v2.0/token"
    DEVICE_AUTHORIZATION_ENDPOINT = (
        f"{IDP_ISSUER.rstrip('/')}/oauth2/v2.0/devicecode"
    )
    IDP_USERINFO_ENDPOINT = "https://graph.microsoft.com/oidc/userinfo"
else:
    # Keycloak (default)
    IDP_AUTHORIZE_ENDPOINT = (
        f"{IDP_ISSUER.rstrip('/')}/protocol/openid-connect/auth"
    )
    IDP_TOKEN_ENDPOINT = (
        f"{IDP_ISSUER.rstrip('/')}/protocol/openid-connect/token"
    )
    DEVICE_AUTHORIZATION_ENDPOINT = (
        f"{IDP_ISSUER.rstrip('/')}/protocol/openid-connect/auth/device"
    )
    IDP_USERINFO_ENDPOINT = (
        f"{IDP_ISSUER.rstrip('/')}/protocol/openid-connect/userinfo"
    )

# ─── Agente (cliente OAuth confidential) ────────────────────────────────────
AGENT_CLIENT_ID = os.getenv("AGENT_CLIENT_ID", "agente-ia")
AGENT_CLIENT_SECRET = os.getenv("AGENT_CLIENT_SECRET", "secret-del-agente")

# ─── API de negocio invocada por el agente ──────────────────────────────────
API_BASE_URL = os.getenv("API_BASE_URL", "http://spring-boot-api:9090")

# ─── Redirect URI de client-mock ────────────────────────────────────────────
# client-mock usa esta URL como destino del Auth Code redirect.
# Por defecto es el client-mock del docker-compose (puerto 3000).
CLIENT_MOCK_REDIRECT_URI = os.getenv(
    "CLIENT_MOCK_REDIRECT_URI",
    "http://localhost:3000/callback",
)

# ─── Usuarios "registrados" en el PoC ──────────────────────────────────────
# En un sistema real esto vendría de un IdP / base de usuarios. Aquí basta
# con un mapa mínimo para que el agente sepa a quién representa cada user_id
# (nombre, email para los emails que envíe el agente, etc.).
# IMPORTANTE: ya NO contiene password — el humano nunca comparte su password
# con el agente.
#
# Para el flujo C "identidad con datos identificativos" (en lugar de voz):
# almacenamos DNI + fecha de nacimiento HASHEADOS (SHA-256). En producción
# esto sería una llamada a un servicio de verificación de identidad real
# (AEAT, SEP, Veriff, Onfido, etc.).
import hashlib


def _hash_identifier(value: str) -> str:
    """SHA-256 hex digest. Normaliza a minúsculas y strip."""
    return hashlib.sha256(value.lower().strip().encode("utf-8")).hexdigest()


USERS = {
    "ana": {
        "name": "Ana García",
        "email": "ana@example.com",
        "preferred_username": "ana",
        "dni_hash": _hash_identifier("12345678Z"),
        "dob_hash": _hash_identifier("1990-05-15"),
        "mobile_token": "device-ana-001",
    },
    "luis": {
        "name": "Luis Pérez",
        "email": "luis@example.com",
        "preferred_username": "luis",
        "dni_hash": _hash_identifier("87654321X"),
        "dob_hash": _hash_identifier("1985-03-22"),
        "mobile_token": "device-luis-001",
    },
    "marta": {
        "name": "Marta López",
        "email": "marta@example.com",
        "preferred_username": "marta",
        "dni_hash": _hash_identifier("11223344Y"),
        "dob_hash": _hash_identifier("1992-11-30"),
        "mobile_token": "device-marta-001",
    },
}


def get_user(user_id: str) -> dict | None:
    return USERS.get(user_id)


def verify_identity(user_id: str, dni: str, dob: str) -> bool:
    """
    Verifica DNI + fecha de nacimiento contra la tabla interna (PoC).

    Args:
        user_id: ID del usuario registrado (ana, luis, marta).
        dni:      DNI/NIF español (8 dígitos + letra).
        dob:      Fecha de nacimiento ISO-8601 (YYYY-MM-DD).

    Returns:
        True si ambos datos coinciden con los registrados.
        False si el usuario no existe o los datos no coinciden.

    En producción: llamar a un servicio de verificación de identidad
    (AEAT, SEP, Veriff). Aquí: comparación local de hashes.
    """
    user = USERS.get(user_id)
    if user is None:
        return False
    return (
        user["dni_hash"] == _hash_identifier(dni)
        and user["dob_hash"] == _hash_identifier(dob)
    )
