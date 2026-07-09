"""KC Client Protocol Mapper: user attribute 'requested_scope' -> access_token claim.

Crea un mapper en el cliente 'agente-ia' que copia el user attribute
'requested_scope' al access_token como claim 'requested_scope'.

Esto completa el workaround del BUG KC 26.6.4 broker jwt-bearer (ignora scope).
El agente mete requested_scope en la assertion -> IdP mapper lo copia a user
attribute -> este client protocol mapper lo copia al access_token.

Spring Security filtra authorities por el claim 'requested_scope' del token.
"""
import json
import sys
import urllib.error
import urllib.request

KC_URL = "http://localhost:8180"
REALM = "agent-poc"
CLIENT_ID = "agente-ia"
MAPPER_NAME = "requested-scope-attr-to-access-token"


def admin_token():
    data = "username=admin&password=admin&grant_type=password&client_id=admin-cli".encode()
    req = urllib.request.Request(
        f"{KC_URL}/realms/master/protocol/openid-connect/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    return json.loads(urllib.request.urlopen(req).read())["access_token"]


def api(method, path, tok, data=None):
    url = f"{KC_URL}/admin/realms/{REALM}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", "Bearer " + tok)
    req.add_header("Accept", "application/json")
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        resp = urllib.request.urlopen(req)
        data = resp.read()
        if not data:
            return resp.status, []
        return resp.status, json.loads(data)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]


def find_client_internal_id(tok):
    status, clients = api("GET", "/clients", tok)
    if not isinstance(clients, list):
        print(f"ERROR listando clients: {clients}")
        sys.exit(1)
    for c in clients:
        if c.get("clientId") == CLIENT_ID:
            return c["id"]
    print(f"ERROR: client '{CLIENT_ID}' no encontrado")
    sys.exit(1)


def main():
    tok = admin_token()
    cid = find_client_internal_id(tok)
    print(f"client {CLIENT_ID} internalId = {cid[:8]}...")

    # Lista mappers actuales
    status, mappers = api("GET", f"/clients/{cid}/protocol-mappers/models", tok)
    if not isinstance(mappers, list):
        print(f"ERROR listando mappers: {mappers}")
        sys.exit(1)
    print(f"GET protocol-mappers -> {status} ({len(mappers)} actuales)")
    # Borra mappers con el mismo nombre (idempotente)
    for m in mappers:
        if not isinstance(m, dict):
            continue
        if m.get("name") == MAPPER_NAME:
            api("DELETE", f"/clients/{cid}/protocol-mappers/models/{m['id']}", tok)
            print(f"  - borrado mapper previo {m['id'][:8]}")

    # Crea mapper: user attribute 'requested_scope' -> access_token claim 'requested_scope'
    payload = {
        "name": MAPPER_NAME,
        "protocol": "openid-connect",
        "protocolMapper": "oidc-usermodel-attribute-mapper",
        "consentRequired": False,
        "config": {
            "user.attribute": "requested_scope",
            "claim.name": "requested_scope",
            "jsonType.label": "String",
            "id.token.claim": "false",
            "access.token.claim": "true",   # <-- SÍ al access_token
            "userinfo.token.claim": "false",
        },
    }
    status, body = api("POST", f"/clients/{cid}/protocol-mappers/models", tok, data=payload)
    print(f"POST protocol-mapper -> {status}: {body}")


if __name__ == "__main__":
    main()