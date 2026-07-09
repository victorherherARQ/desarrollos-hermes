"""Quita publicKeySignatureVerifierKeyId del IdP broker.

KC 26.6.4 JWTAuthorizationGrantIdentityProviderConfig NO implementa
getPublicKeySignatureVerifierKeyId() correctamente. Si está configurado,
KC busca por ese kid via reflection y falla. Si NO está configurado,
KC usa el kid del header del JWT directamente.

Como nuestra PEM ya matchea con kid del header (ambos abbffe9170c7fe6e),
no necesitamos el keyId en el IdP.

Usage: python3 configure_kc_idp_no_keyid.py"""
import json
import sys
import urllib.parse
import urllib.request

KC_BASE = "http://localhost:8180"
KC_REALM = "agent-poc"
KC_IDP_ALIAS = "agent-poc-jwt-broker"
ADMIN_USER = "admin"
ADMIN_PASSWORD = "admin"


def admin_token() -> str:
    data = "username=" + ADMIN_USER + "&password=" + ADMIN_PASSWORD + \
        "&grant_type=password&client_id=admin-cli"
    data = data.encode()
    req = urllib.request.Request(
        KC_BASE + "/realms/master/protocol/openid-connect/token",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["access_token"]


def get_idp(token: str) -> dict:
    req = urllib.request.Request(
        f"{KC_BASE}/admin/realms/{KC_REALM}/identity-provider/instances/{KC_IDP_ALIAS}",
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def put_idp(token: str, body: dict) -> tuple[int, str]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{KC_BASE}/admin/realms/{KC_REALM}/identity-provider/instances/{KC_IDP_ALIAS}",
        data=data,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
        },
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def main() -> int:
    token = admin_token()
    current = get_idp(token)
    config = current.get("config", {})
    print(f"current publicKeySignatureVerifierKeyId = {config.get('publicKeySignatureVerifierKeyId')!r}")

    # Drop publicKeySignatureVerifierKeyId entirely
    if "publicKeySignatureVerifierKeyId" in config:
        del config["publicKeySignatureVerifierKeyId"]
        body = {
            "alias": current["alias"],
            "providerId": current["providerId"],
            "config": config,
            "enabled": current.get("enabled", True),
        }
        status, response = put_idp(token, body)
        print(f"PUT IdP (remove keyId) -> {status}: {response[:200]}")
    else:
        print("publicKeySignatureVerifierKeyId not set, nothing to do")
        status = 200
        response = ""

    if status == 204 or status == 200:
        # verify
        current = get_idp(token)
        config = current.get("config", {})
        print(f"now publicKeySignatureVerifierKeyId = {config.get('publicKeySignatureVerifierKeyId')!r}")
        print(f"publicKeySignatureVerifier len = {len(config.get('publicKeySignatureVerifier', ''))}")
        return 0
    print(f"ERROR: {status}: {response}")
    return 1


if __name__ == "__main__":
    sys.exit(main())