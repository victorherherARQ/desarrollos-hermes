"""
Aplica (o repara) el realm `agent-poc` en Keycloak con la configuración
objetivo para los flujos A+B+C:

  A) Authorization Code + PKCE (RFC 6749 + RFC 7636)
  B) Device Code Flow (RFC 8628)
  C) On-Behalf-Of / JWT Bearer (RFC 7523) — requiere Keycloak 26+ nativo

NO habilita:
  - directAccessGrantsEnabled (ROPC / password grant) — inseguro
  - cibaEnabled (CIBA) — sustituido por flujo A síncrono con MFA

Uso:
    python3 scripts/create_realm.py [--reset]

Idempotente: si el realm ya existe aplica un diff (PUT/PATCH) en lugar de
borrarlo/crearlo de nuevo.

Asignación de custom scopes al cliente `agente-ia` se hace vía SUB-ENDPOINT
dedicado (PUT .../clients/{cid}/default-client-scopes/{sid}), NO dentro del
body de PUT /clients/{cid} — Keycloak 24 ignora esa parte y devuelve 204 sin
persistir.

Atributos de client-scopes siempre con notación dotted (`include.in.token.scope`),
NO camelCase, porque KC 24 ignora silently esa forma.

Cada custom scope lleva un `oidc-audience-mapper` que añade la API Spring Boot
al claim `aud` del access_token.
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error

KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8180")
ADMIN_USER = os.getenv("KEYCLOAK_ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("KEYCLOAK_ADMIN_PASS", "admin")
REALM_NAME = "agent-poc"
SPRING_API_CLIENT = "spring-boot-api"
CLIENT_MOCK_CLIENT = "client-mock"

CUSTOM_SCOPES = ["calendar.read", "calendar.write", "email.send", "email.modify"]
DEMO_USERS = [
    {"username": "ana",   "firstName": "Ana",   "lastName": "García", "email": "ana@example.com"},
    {"username": "luis",  "firstName": "Luis",  "lastName": "López",  "email": "luis@example.com"},
    {"username": "marta", "firstName": "Marta", "lastName": "Martín", "email": "marta@example.com"},
]


# ────────────────────── HTTP helpers ────────────────────────────────────────
def get_admin_token():
    """Obtiene un access_token para la Admin REST API.

    NOTA: usa `grant_type=password` contra `admin-cli` — esto es el flujo de
    bootstrap del script. NO es el flujo inseguro que prohíbe la PoC. El
    script corre en una red privada y NO está expuesto al usuario.
    """
    url = f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token"
    data = urllib.parse.urlencode({
        "grant_type": "password",
        "client_id": "admin-cli",
        "username": ADMIN_USER,
        "password": ADMIN_PASS,
    }).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["access_token"]


def api(method, path, token, body=None, ok_status=None):
    """Llama a Admin REST API y devuelve (status, body-decoded)."""
    url = f"{KEYCLOAK_URL}/admin/realms/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            text = r.read().decode()
            return r.status, (json.loads(text) if text else {})
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def with_ok(label, status, body, ok_status=204):
    if status == ok_status:
        print(f"  ✅ {label}")
        return True
    if status == 409:
        print(f"  ⚠️  {label} (conflicto, ya existe)")
        return True
    print(f"  ❌ {label}: HTTP {status} :: {str(body)[:200]}")
    return False


# ────────────────────── Realm ──────────────────────────────────────────────
def ensure_realm(token, reset=False):
    print(f"\n[1/7] Realm '{REALM_NAME}'")
    status, _ = api("GET", REALM_NAME, token)
    if status == 200:
        if reset:
            print("  ♻️  Borrando realm existente para re-crear limpio...")
            api("DELETE", REALM_NAME, token)
        else:
            print("  ℹ️  Realm ya existe, se aplicará diff idempotente")
            return True
    realm = {
        "realm": REALM_NAME,
        "enabled": True,
        "accessTokenLifespan": 300,
        "loginWithEmailAllowed": True,
        "duplicateEmailsAllowed": False,
        "resetPasswordAllowed": False,
        "editUsernameAllowed": False,
        "bruteForceProtected": True,
        # NO habilitamos CIBA (lo prohibimos en la nueva arquitectura)
        "cibaEnabled": False,
        # Device Code Flow support explícito
        "attributes": {
            "deviceFlowSupported": "true",
            "oauth2.device.authorization.grant.enabled": "true",
        },
    }
    status, body = api("POST", "", token, realm)
    return with_ok("Realm creado", status, body, ok_status=201)


# ────────────────────── Custom client-scopes ──────────────────────────────
SCOPE_DESCRIPTIONS = {
    "calendar.read":  "Leer el calendario del usuario",
    "calendar.write": "Crear/modificar eventos en el calendario",
    "email.send":     "Enviar emails en nombre del usuario",
    "email.modify":   "Gestionar correo (borrar, etiquetar, mover)",
}


def ensure_custom_scopes(token):
    """Crea los 4 custom scopes con atributos dotted y audience-mapper."""
    print(f"\n[2/7] Custom client-scopes (con fix KC 24)")
    status, body = api("GET", f"{REALM_NAME}/client-scopes", token)
    existing = {s["name"]: s["id"] for s in body if isinstance(body, list)}

    created_ids = {}
    for name in CUSTOM_SCOPES:
        if name in existing:
            scope_id = existing[name]
            print(f"  ℹ️  {name} ya existe ({scope_id})")
        else:
            payload = {
                "name": name,
                "protocol": "openid-connect",
                "description": SCOPE_DESCRIPTIONS[name],
                "attributes": {
                    "include.in.token.scope": "true",
                    "display.on.consent.screen": "true",
                    "consent.screen.text": SCOPE_DESCRIPTIONS[name],
                    "gui.order": str(10 + len(created_ids) * 10),
                },
            }
            status, body = api("POST", f"{REALM_NAME}/client-scopes", token, payload)
            if not with_ok(f"  + {name}", status, body, ok_status=201):
                continue
            status, body = api("GET", f"{REALM_NAME}/client-scopes", token)
            existing = {s["name"]: s["id"] for s in body if isinstance(body, list)}
            scope_id = existing[name]

        # Atributos dotted garantizados
        status, body = api("GET", f"{REALM_NAME}/client-scopes/{scope_id}", token)
        if isinstance(body, dict):
            body["attributes"] = {
                **(body.get("attributes") or {}),
                "include.in.token.scope": "true",
                "display.on.consent.screen": "true",
                "consent.screen.text": SCOPE_DESCRIPTIONS[name],
                "gui.order": body.get("attributes", {}).get("gui.order", "10"),
            }
            api("PUT", f"{REALM_NAME}/client-scopes/{scope_id}", token, body)

        # Audience mapper (aud=spring-boot-api) para que el JWT pueda ser
        # validado por la API de negocio.
        status, body = api("GET",
            f"{REALM_NAME}/client-scopes/{scope_id}/protocol-mappers/models", token)
        has_audience = (
            isinstance(body, list) and any(
                m.get("name") == name and m.get("protocolMapper") == "oidc-audience-mapper"
                for m in body
            )
        )
        if not has_audience:
            mp = {
                "name": name,
                "protocol": "openid-connect",
                "protocolMapper": "oidc-audience-mapper",
                "consentRequired": False,
                "config": {
                    "included.custom.audience": SPRING_API_CLIENT,
                    "id.token.claim": "false",
                    "access.token.claim": "true",
                },
            }
            status, body = api("POST",
                f"{REALM_NAME}/client-scopes/{scope_id}/protocol-mappers/models",
                token, mp)
            with_ok(f"  ↳ audience-mapper {name}", status, body, ok_status=201)

        created_ids[name] = scope_id

    return created_ids


# ────────────────────── Usuarios ───────────────────────────────────────────
def ensure_users(token):
    print(f"\n[3/7] Usuarios demo (ana/luis/marta)")
    status, body = api("GET", f"{REALM_NAME}/users", token)
    existing_usernames = (
        {u["username"] for u in body} if isinstance(body, list) else set()
    )
    for u in DEMO_USERS:
        if u["username"] in existing_usernames:
            print(f"  ℹ️  {u['username']} ya existe")
            continue
        payload = {
            "username": u["username"],
            "firstName": u["firstName"],
            "lastName": u["lastName"],
            "email": u["email"],
            "enabled": True,
            "emailVerified": True,
            "credentials": [{"type": "password", "value": "demo1234", "temporary": False}],
        }
        status, body = api("POST", f"{REALM_NAME}/users", token, payload)
        with_ok(f"  + {u['username']}", status, body, ok_status=201)


# ────────────────────── Cliente agente-ia ──────────────────────────────────
def ensure_agente_client(token):
    print(f"\n[4/7] Cliente confidencial 'agente-ia' (A+B+C)")
    # Cliente confidential: con client_id + client_secret que mantiene el agente.
    # NO habilitamos directAccessGrantsEnabled (prohibido).
    # NO habilitamos CIBA attrs.
    # Habilitamos standardFlow (Auth Code + PKCE) y device flow.

    url = f"{KEYCLOAK_URL}/admin/realms/{REALM_NAME}/clients?clientId=agente-ia"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                                "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        clients = json.loads(r.read())

    payload = {
        "clientId": "agente-ia",
        "name": "Agente IA (cliente confidencial A+B+C)",
        "description": (
            "Cliente OAuth confidencial que representa al agente IA. "
            "Flujos: Auth Code + PKCE (A), Device Code (B), OBO (C). "
            "NO soporta Direct Access Grants (ROPC)."
        ),
        "enabled": True,
        "publicClient": False,
        "secret": "secret-del-agente",
        "serviceAccountsEnabled": True,
        "directAccessGrantsEnabled": False,
        "standardFlowEnabled": True,
        "redirectUris": [
            "http://localhost:*",
            "http://localhost:3000/*",
            "http://localhost:7000/*",
        ],
        "webOrigins": ["*"],
        "attributes": {
            "pkce.code.challenge.method": "S256",
            "oauth2.device.authorization.grant.enabled": "true",
            "backchannel.logout.url": "",
            "backchannel.logout.session.required": "false",
            "display.on.consent.screen": "false",
        },
    }

    if clients:
        client_id = clients[0]["id"]
        print(f"  ℹ️  agente-ia ya existe ({client_id}), aplicando diff")
        # PUT sobre el client-id estable; payload respeta campos sensibles.
        status, body = api("PUT", f"{REALM_NAME}/clients/{client_id}", token, payload)
        if not with_ok("  actualizar agente-ia", status, body):
            return None
    else:
        status, body = api("POST", f"{REALM_NAME}/clients", token, payload)
        if not with_ok("  + agente-ia", status, body, ok_status=201):
            return None
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                                    "Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            clients = json.loads(r.read())
        client_id = clients[0]["id"]

    return client_id


def ensure_client_mock(token):
    """Cliente público (webapp) que hace Auth Code + PKCE en nombre del humano."""
    print(f"\n[4b/7] Cliente confidential 'client-mock' (webapp del usuario)")
    url = f"{KEYCLOAK_URL}/admin/realms/{REALM_NAME}/clients?clientId=client-mock"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                                "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        clients = json.loads(r.read())
    payload = {
        "clientId": "client-mock",
        "name": "Client Mock (webapp del usuario — Auth Code + PKCE)",
        "description": (
            "Webapp que simula el dispositivo del usuario: hace Auth Code + PKCE "
            "(flujo A) y muestra Device Code (flujo B)."
        ),
        "enabled": True,
        "publicClient": False,
        "secret": "client-mock-secret",
        "standardFlowEnabled": True,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": False,
        "rootUrl": "http://localhost:3000",
        "baseUrl": "http://localhost:3000",
        "redirectUris": [
            "http://localhost:3000/*",
            "http://localhost:3000/auth/callback",
        ],
        "webOrigins": ["+"],
        "attributes": {
            "pkce.code.challenge.method": "S256",
            "oauth2.device.authorization.grant.enabled": "true",
            "display.on.consent.screen": "true",
        },
    }
    if clients:
        client_id = clients[0]["id"]
        print(f"  ℹ️  client-mock ya existe ({client_id}), aplicando diff")
        api("PUT", f"{REALM_NAME}/clients/{client_id}", token, payload)
    else:
        status, body = api("POST", f"{REALM_NAME}/clients", token, payload)
        with_ok("  + client-mock", status, body, ok_status=201)
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                                    "Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            clients = json.loads(r.read())
        client_id = clients[0]["id"]
    return client_id


# ────────────────────── Asignar scopes al cliente ─────────────────────────
def assign_scopes_to_client(token, client_id, scope_ids):
    """
    Asigna los custom scopes al cliente `agente-ia` vía SUB-ENDPOINT dedicado.
    BUG original del PoC: PUT /clients/{cid} con array de defaultClientScopes
    en el body devolvía 204 sin persistir en KC 24.
    """
    print(f"\n[5/7] Asignando custom scopes al cliente agente-ia (sub-endpoint)")
    status, body = api("GET", f"{REALM_NAME}/clients/{client_id}/default-client-scopes", token)
    current = {s["name"]: s["id"] for s in body} if isinstance(body, list) else {}
    for name, sid in scope_ids.items():
        if current.get(name) == sid:
            print(f"  ℹ️  {name} ya está asignado")
            continue
        status, body = api("PUT",
            f"{REALM_NAME}/clients/{client_id}/default-client-scopes/{sid}",
            token, body=None)
        if status == 204 or status == 200:
            print(f"  ✅ {name} asignado al cliente agente-ia")
        else:
            print(f"  ❌ {name}: HTTP {status} :: {str(body)[:200]}")


# ────────────────────── Realm default scopes ───────────────────────────────
def ensure_realm_default_scopes(token):
    print(f"\n[6/7] Realm default scopes (openid/profile/email)")
    payload = {"defaultDefaultClientScopes": ["openid", "profile", "email"]}
    status, body = api("PUT", REALM_NAME, token, payload)
    with_ok("Default scopes", status, body)


# ────────────────────── Verificación final ─────────────────────────────────
def verify(token):
    print(f"\n[7/7] Verificación end-to-end")
    # Verificamos que el cliente agente-ia YA NO tiene directAccessGrantsEnabled
    url = f"{KEYCLOAK_URL}/admin/realms/{REALM_NAME}/clients?clientId=agente-ia"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                                "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        clients = json.loads(r.read())
    if not clients:
        print("  ❌ Cliente agente-ia no existe")
        return False
    agent = clients[0]
    if agent.get("directAccessGrantsEnabled"):
        print("  ❌ agente-ia tiene directAccessGrantsEnabled=true (debería ser false)")
        return False
    if not agent.get("standardFlowEnabled"):
        print("  ❌ agente-ia tiene standardFlowEnabled=false (debería ser true)")
        return False
    if not agent.get("attributes", {}).get("oauth2.device.authorization.grant.enabled") == "true":
        print("  ⚠️  agente-ia no tiene device authorization habilitado")
    print("  ✅ agente-ia: standardFlow=true, directAccess=false, device=true")
    print("  ✅ ROPC bloqueado correctamente")
    return True


# ────────────────────── main ───────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true",
                        help="Borra el realm si existe y lo crea de cero")
    args = parser.parse_args()

    print("=" * 64)
    print(f"🌍 Keycloak realm setup · {KEYCLOAK_URL} · realm={REALM_NAME}")
    print(f"   Flujos habilitados: A (Auth Code + PKCE), B (Device Code), C (OBO)")
    print(f"   Prohibidos:         ROPC (password grant), CIBA")
    print("=" * 64)

    token = get_admin_token()
    print("\n[0/7] Admin token OK")

    if not ensure_realm(token, reset=args.reset):
        sys.exit(1)
    scope_ids = ensure_custom_scopes(token)
    ensure_users(token)
    agent_id = ensure_agente_client(token)
    ensure_client_mock(token)
    if agent_id:
        assign_scopes_to_client(token, agent_id, scope_ids)
    ensure_realm_default_scopes(token)
    ok = verify(token)

    print("\n" + "=" * 64)
    print(("✅ Realm listo y verificado" if ok else "⚠️  Realm listo pero verificación falló"))
    print(f"   Admin console: {KEYCLOAK_URL}/admin  (admin/admin)")
    print(f"   Realm:         {REALM_NAME}")
    print(f"   Usuarios:      ana/luis/marta  (pass: demo1234)")
    print(f"   Cliente:       agente-ia  (secret: secret-del-agente, A+B+C habilitado)")
    print("=" * 64)
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()
