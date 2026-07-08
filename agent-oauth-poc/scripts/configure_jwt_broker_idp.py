"""
Configura el IdP broker jwt-authorization-grant con los campos correctos
descubiertos en el codigo fuente de KC 26.6.4:
  - services/src/main/java/org/keycloak/broker/jwtauthorizationgrant/JWTAuthorizationGrantConfig.java

Descubrimiento 2026-07-08: KC 26 requiere que el IdP broker tenga:
  - jwtAuthorizationGrantEnabled: "true"
  - jwtAuthorizationGrantAssertionSignatureAlg: "HS256" (o RS256)
  - publicKeySignatureVerifier: el client_secret (para HMAC) o un PEM (para RSA)
  - jwtAuthorizationGrantAllowedClockSkew: int (segundos)
"""
import json
import re
import urllib.request

KC = "http://localhost:8180"
REALM = "agent-poc"
ADMIN = "admin"
PWD = "admin"
IDP_ALIAS = "agent-poc-jwt-broker"


def get_secret_from_compose():
    """Lee el client_secret del cliente agente-ia del compose o de KC directo."""
    # Lo mas robusto: leerlo de KC Admin API directamente
    data = f"username={ADMIN}&password={PWD}&grant_type=password&client_id=admin-cli"
    req = urllib.request.Request(
        f"{KC}/realms/master/protocol/openid-connect/token",
        data=data.encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    tok = json.loads(urllib.request.urlopen(req).read())["access_token"]
    req = urllib.request.Request(
        f"{KC}/admin/realms/{REALM}/clients?clientId=agente-ia",
        headers={"Authorization": f"Bearer {tok}"},
    )
    agente = json.loads(urllib.request.urlopen(req).read())[0]
    return agente.get("secret"), tok


def main():
    secret, tok = get_secret_from_compose()
    print(f"Secret leido de KC: {len(secret)} bytes (empieza por '{secret[:3]}')")

    req = urllib.request.Request(
        f"{KC}/admin/realms/{REALM}/identity-provider/instances/{IDP_ALIAS}",
        headers={"Authorization": f"Bearer {tok}"},
    )
    idp = json.loads(urllib.request.urlopen(req).read())

    # Campos descubiertos en JWTAuthorizationGrantConfig.java
    idp["config"]["jwtAuthorizationGrantEnabled"]               = "true"
    idp["config"]["jwtAuthorizationGrantAssertionSignatureAlg"] = "HS256"
    idp["config"]["publicKeySignatureVerifier"]                = secret
    idp["config"]["jwtAuthorizationGrantAllowedClockSkew"]     = "30"

    # Limpiar campos que no aplican
    idp["config"].pop("signatureAlgorithm", None)

    req = urllib.request.Request(
        f"{KC}/admin/realms/{REALM}/identity-provider/instances/{IDP_ALIAS}",
        data=json.dumps(idp).encode(),
        method="PUT",
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
    )
    r = urllib.request.urlopen(req)
    print(f"PUT IdP OK status: {r.status}")
    print("Config final:")
    for k, v in idp["config"].items():
        if "publicKey" in k or "Verifier" in k:
            print(f"  {k}: <{len(v)} bytes>")
        else:
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()