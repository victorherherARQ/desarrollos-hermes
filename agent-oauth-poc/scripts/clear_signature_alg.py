"""
Quita jwtAuthorizationGrantAssertionSignatureAlg del IdP broker.
Si es null, KC acepta cualquier algoritmo (deja el path abierto).
"""
import json
import urllib.request

KC = "http://localhost:8180"
REALM = "agent-poc"
ADMIN = "admin"
PWD = "admin"
IDP_ALIAS = "agent-poc-jwt-broker"

def get_token():
    data = f"username={ADMIN}&password={PWD}&grant_type=password&client_id=admin-cli"
    req = urllib.request.Request(
        f"{KC}/realms/master/protocol/openid-connect/token",
        data=data.encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    return json.loads(urllib.request.urlopen(req).read())["access_token"]


def main():
    tok = get_token()
    req = urllib.request.Request(
        f"{KC}/admin/realms/{REALM}/identity-provider/instances/{IDP_ALIAS}",
        headers={"Authorization": f"Bearer {tok}"},
    )
    idp = json.loads(urllib.request.urlopen(req).read())
    print(f"jwtAuthorizationGrantAssertionSignatureAlg actual: {idp['config'].get('jwtAuthorizationGrantAssertionSignatureAlg')!r}")
    # Borrarla
    idp["config"].pop("jwtAuthorizationGrantAssertionSignatureAlg", None)
    req = urllib.request.Request(
        f"{KC}/admin/realms/{REALM}/identity-provider/instances/{IDP_ALIAS}",
        data=json.dumps(idp).encode(),
        method="PUT",
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
    )
    r = urllib.request.urlopen(req)
    print(f"PUT OK status: {r.status}")
    print(f"jwtAuthorizationGrantAssertionSignatureAlg ahora: {idp['config'].get('jwtAuthorizationGrantAssertionSignatureAlg')!r}")


if __name__ == "__main__":
    main()