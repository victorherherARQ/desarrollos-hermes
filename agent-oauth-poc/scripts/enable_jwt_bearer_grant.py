"""
Script de admin: habilita el grant_type 'urn:ietf:params:oauth:grant-type:jwt-bearer'
en el cliente 'agente-ia' del realm 'agent-poc' de Keycloak.

Uso:  python3 scripts/enable_jwt_bearer_grant.py
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

KEYCLOAK_URL = "http://localhost:8180"
ADMIN_USER = "admin"
ADMIN_PASS = "admin"
REALM = "agent-poc"
TARGET_CLIENT_ID = "agente-ia"
GRANT_TYPE = "urn:ietf:params:oauth:grant-type:jwt-bearer"


def http(method: str, url: str, *, headers: dict | None = None, data: bytes | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


# 1. Obtener admin token
status, body = http(
    "POST",
    f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token",
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    data=urllib.parse.urlencode({
        "username":    ADMIN_USER,
        "password":    ADMIN_PASS,
        "grant_type":  "password",
        "client_id":   "admin-cli",
    }).encode(),
)
if status != 200:
    print(f"FAIL: admin token: {status} {body[:200]}")
    sys.exit(1)
admin_token = json.loads(body)["access_token"]
print(f"[1/4] Admin token OK ({len(admin_token)} bytes)")

# 2. Buscar internal_id del cliente agente-ia
status, body = http(
    "GET",
    f"{KEYCLOAK_URL}/admin/realms/{REALM}/clients",
    headers={"Authorization": f"Bearer {admin_token}"},
)
clients = json.loads(body)
target = [c for c in clients if c["clientId"] == TARGET_CLIENT_ID]
if not target:
    print(f"FAIL: cliente '{TARGET_CLIENT_ID}' no encontrado en realm '{REALM}'")
    sys.exit(1)
cid = target[0]["id"]
print(f"[2/4] Cliente encontrado: {TARGET_CLIENT_ID} (id={cid[:8]}...)")

# 3. Leer config actual
status, body = http(
    "GET",
    f"{KEYCLOAK_URL}/admin/realms/{REALM}/clients/{cid}",
    headers={"Authorization": f"Bearer {admin_token}"},
)
client = json.loads(body)
attrs = client.setdefault("attributes", {})
current_grants = attrs.get("oauth2.grant.type", "")
print(f"[3/4] Grants actuales: {current_grants!r}")

# 4. Añadir el grant_type si no está
attrs = client.setdefault("attributes", {})

# KC 24 tiene dos formatos válidos para oauth2.grant.type:
#   a) String comma-separated: "authorization_code,password,..."
#   b) JSON array:             ["authorization_code","password",...]
# Ambos formatos son aceptados por la Admin API. Ponemos AMBOS para máxima
# compatibilidad con el client authenticator interno.
grants_list = [g.strip() for g in attrs.get("oauth2.grant.type", "").split(",") if g.strip()]
if GRANT_TYPE not in grants_list:
    grants_list.append(GRANT_TYPE)

attrs["oauth2.grant.type"] = ",".join(grants_list)  # formato a (string)
# Algunos realm setups también necesitan un duplicado como array:
attrs["oauth2.grant.type[]"] = grants_list          # formato b (array)

# PUT para guardar
status, body = http(
    "PUT",
    f"{KEYCLOAK_URL}/admin/realms/{REALM}/clients/{cid}",
    headers={
        "Authorization": f"Bearer {admin_token}",
        "Content-Type":  "application/json",
    },
    data=json.dumps(client).encode(),
)
if status not in (204, 200):
    print(f"FAIL: PUT cliente: {status} {body[:300]}")
    sys.exit(1)
print(f"[4/4] Grants actualizados: {attrs['oauth2.grant.type']!r}")
print(f"     (también como array: {attrs['oauth2.grant.type[]']!r})")

print()
print("OK: cliente 'agente-ia' ahora acepta el grant_type JWT bearer.")
