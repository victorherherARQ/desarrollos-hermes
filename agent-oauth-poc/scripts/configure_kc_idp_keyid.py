"""KC 26.6.4 verification path:

KC loads the PEM from publicKeySignatureVerifier with kid from
publicKeySignatureVerifierKeyId (if set) or from JWT header.
Then it compares that kid with the kid in JWT header.
If they don't match, returns 'Invalid signature'.

Two valid configurations:
  A) IdP has publicKeySignatureVerifierKeyId=K. JWT header kid=K. (must match)
  B) IdP has no keyId. JWT header has no kid.

We use option A (kid=abbffe9170c7fe6e in both).
"""
import json
import sys
import urllib.error
import urllib.request

KC_URL = "http://localhost:8180"
REALM = "agent-poc"
IDP_ALIAS = "agent-poc-jwt-broker"
KID = "abbffe9170c7fe6e"   # kid del agente (matchea el PEM publico)


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
        text = resp.read()
        if not text:
            return resp.status, {}
        return resp.status, json.loads(text)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]


def main():
    tok = admin_token()
    status, current = api("GET", f"/identity-provider/instances/{IDP_ALIAS}", tok)
    if status != 200:
        print(f"ERROR get IdP -> {status}: {current}")
        sys.exit(1)
    if not isinstance(current, dict):
        print(f"ERROR: current is not a dict: {current}")
        sys.exit(1)
    config = current.get("config", {})
    print(f"current publicKeySignatureVerifierKeyId = {config.get('publicKeySignatureVerifierKeyId', '<not set>')!r}")

    # Configura el kid
    config["publicKeySignatureVerifierKeyId"] = KID
    payload = {
        "alias": current["alias"],
        "providerId": current["providerId"],
        "config": config,
        # Reuse other fields to avoid losing config
        "displayName": current.get("displayName"),
        "enabled": current.get("enabled", True),
        "trustEmail": current.get("trustEmail", False),
        "linkOnly": current.get("linkOnly", False),
        "firstBrokerLoginFlowAlias": current.get("firstBrokerLoginFlowAlias"),
        "postBrokerLoginFlowAlias": current.get("postBrokerLoginFlowAlias"),
    }
    # Clean None values
    payload = {k: v for k, v in payload.items() if v is not None}
    status, body = api("PUT", f"/identity-provider/instances/{IDP_ALIAS}", tok, data=payload)
    print(f"PUT IdP -> {status}: {body}")


if __name__ == "__main__":
    main()