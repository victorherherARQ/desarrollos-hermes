"""KC IdentityProvider Mapper: requested_scope claim -> user attribute.

Workaround BUG KC 26.6.4 broker jwt-bearer (ignora param 'scope' del grant):
el agente añade un claim custom 'requested_scope' a la identity_assertion.
KC, via este IdentityProvider Mapper, lo copia a un user attribute
'requested_scope'. Despues un Client Protocol Mapper lo copia al access_token.

Espera input: identity_assertion JWT (RS256) firmado por el agente con kid.
El mapper busca el claim 'requested_scope' y lo guarda como user attribute.
"""
import json
import sys
import urllib.error
import urllib.request

KC_URL = "http://localhost:8180"
REALM = "agent-poc"
IDP_ALIAS = "agent-poc-jwt-broker"
MAPPER_NAME = "requested-scope-claim-to-attribute"


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


def main():
    tok = admin_token()
    # Lista IdP mappers actuales
    status, mappers = api("GET", f"/identity-provider/instances/{IDP_ALIAS}/mappers", tok)
    if not isinstance(mappers, list):
        print(f"ERROR listando mappers: {mappers}")
        sys.exit(1)
    print(f"GET IdP mappers -> {status} ({len(mappers)} actuales)")
    # Borra mappers con el mismo nombre si existen (idempotente)
    for m in mappers:
        if not isinstance(m, dict):
            continue
        if m.get("name") == MAPPER_NAME:
            api("DELETE", f"/identity-provider/instances/{IDP_ALIAS}/mappers/{m['id']}", tok)
            print(f"  - borrado mapper previo {m['id'][:8]}")
    # Crea mapper: claim 'requested_scope' -> user attribute 'requested_scope'
    payload = {
        "name": MAPPER_NAME,
        "identityProviderAlias": IDP_ALIAS,
        "identityProviderMapper": "oidc-user-attribute-idp-mapper",
        "config": {
            "claim": "requested_scope",
            "user.attribute": "requested_scope",
        },
    }
    status, body = api("POST", f"/identity-provider/instances/{IDP_ALIAS}/mappers", tok, data=payload)
    print(f"POST IdP mapper -> {status}: {body}")


if __name__ == "__main__":
    main()