"""
Configuración del agente IA.

Apunta a los servicios del PoC:
  - Keycloak   (http://keycloak:8080)          -- IdP / emisor de tokens
  - Spring API (http://spring-boot-api:9090)   -- API protegida que el agente invoca en nombre del usuario

Las URLs usan nombres de servicio Docker (no localhost) porque el agente vive
en la misma red compose que los demás componentes del PoC.
"""

# --- Keycloak ---------------------------------------------------------------
KEYCLOAK_URL = "http://keycloak:8080"
REALM = "agent-poc"
KEYCLOAK_TOKEN_ENDPOINT = (
    f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token"
)
KEYCLOAK_CIBA_AUTH_ENDPOINT = (
    f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/ext/ciba/auth"
)
KEYCLOAK_ISSUER = f"{KEYCLOAK_URL}/realms/{REALM}"

# --- Agente (cliente OAuth confidential) -----------------------------------
AGENT_CLIENT_ID = "agente-ia"
AGENT_CLIENT_SECRET = "secret-del-agente"

# --- API de negocio invocada por el agente ---------------------------------
API_BASE_URL = "http://spring-boot-api:9090"

# --- Usuarios "registrados" en el PoC --------------------------------------
# En un sistema real esto vendría de un IdP / base de usuarios. Aquí basta
# con un mapa mínimo para que el agente sepa a quién representa cada user_id.
USERS = {
    "ana": {
        "name": "Ana García",
        "email": "ana@example.com",
        "username": "ana",
        "password": "demo1234",
    },
    "luis": {
        "name": "Luis Pérez",
        "email": "luis@example.com",
        "username": "luis",
        "password": "demo1234",
    },
    "marta": {
        "name": "Marta López",
        "email": "marta@example.com",
        "username": "marta",
        "password": "demo1234",
    },
}


def get_user(user_id: str) -> dict | None:
    return USERS.get(user_id)