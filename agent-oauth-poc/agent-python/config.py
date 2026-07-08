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

# ─── Clave privada RSA para firmar identity-assertion (RS256, KC 26+) ──────
# AGENT_SIGNING_KEY_PATH: ruta al PEM de la clave privada del agente.
# Si no existe, load_signing_key() genera un keypair nuevo y lo persiste.
# En Docker, se monta como volumen para que sobreviva a `docker rm`.
import hashlib
import logging as _logging
from pathlib import Path as _Path

from cryptography.hazmat.primitives import serialization as _serialization
from cryptography.hazmat.primitives.asymmetric import rsa as _rsa

_logger = _logging.getLogger(__name__)

AGENT_SIGNING_KEY_PATH = os.getenv(
    "AGENT_SIGNING_KEY_PATH",
    "/home/vhdez/.hermes/state/agent-signing-rsa.pem",
)

AGENT_SIGNING_KID = os.getenv(
    "AGENT_SIGNING_KID",
    hashlib.sha256(AGENT_CLIENT_ID.encode()).hexdigest()[:16],
)


def _generate_rsa_keypair(key_size: int = 2048):
    """Genera un keypair RSA-2048 y lo (pem_priv, pem_pub)."""
    key = _rsa.generate_private_key(public_exponent=65537, key_size=key_size)
    priv = key.private_bytes(
        encoding=_serialization.Encoding.PEM,
        format=_serialization.PrivateFormat.PKCS8,
        encryption_algorithm=_serialization.NoEncryption(),
    )
    pub = key.public_key().public_bytes(
        encoding=_serialization.Encoding.PEM,
        format=_serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv, pub


def load_signing_key(private_key_path: str | None = None) -> dict:
    """
    Carga (o genera y persiste) el keypair RSA del agente.

    Returns:
        dict con:
          - 'private' (bytes PEM)  para firmar JWTs
          - 'public'  (bytes PEM)  para subir a KC como publicKeySignatureVerifier
          - 'kid'     (str)        identificador publico de la clave

    Raises:
        ValueError: si el PEM existe pero no se puede parsear.
    """
    path = _Path(private_key_path or AGENT_SIGNING_KEY_PATH)
    if path.exists():
        priv_bytes = path.read_bytes()
        try:
            key = _serialization.load_pem_private_key(priv_bytes, password=None)
        except Exception as exc:
            raise ValueError(
                f"No se pudo parsear la private key en {path}: {exc}"
            ) from exc
        pub_bytes = key.public_key().public_bytes(
            encoding=_serialization.Encoding.PEM,
            format=_serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        _logger.info(
            "Loaded signing key (existing) kid=%s path=%s",
            AGENT_SIGNING_KID, path,
        )
        return {"private": priv_bytes, "public": pub_bytes, "kid": AGENT_SIGNING_KID}

    # No existe -> generar y persistir
    priv, pub = _generate_rsa_keypair()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(priv)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    _logger.warning(
        "Generated NEW RSA keypair (PoC) kid=%s path=%s — "
        "registra la clave publica en KC con scripts/configure_jwt_broker_idp.py",
        AGENT_SIGNING_KID, path,
    )
    return {"private": priv, "public": pub, "kid": AGENT_SIGNING_KID}


# Carga/crea el keypair al importar el modulo (lazy=False: cualquier error se ve
# al arrancar, no en mitad de una request).
_AGENT_SIGNING = load_signing_key()
AGENT_SIGNING_PRIVATE_PEM = _AGENT_SIGNING["private"]
AGENT_SIGNING_PUBLIC_PEM = _AGENT_SIGNING["public"].decode("utf-8")
AGENT_SIGNING_KEY: dict = _AGENT_SIGNING


# ─── Usuarios "registrados" en el PoC ──────────────────────────────────────
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
