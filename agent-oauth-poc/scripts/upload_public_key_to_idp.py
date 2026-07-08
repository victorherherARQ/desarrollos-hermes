"""
Sube la clave publica del agente al IdP broker jwt-authorization-grant
de KC 26+.

KC 26.6.4 verifica la firma de la identity-assertion (firmada con RS256)
usando esta PEM. Sin ella, KC devuelve "Invalid signature" aunque el
algoritmo sea correcto.

Uso:
  python3 scripts/upload_public_key_to_idp.py

Lee la clave publica de:
  1. Variable de entorno AGENT_SIGNING_PUBLIC_PEM (si esta definida)
  2. Fichero PEM en AGENT_SIGNING_KEY_PATH (el .pem contiene solo la privada,
     asi que hay que derivar la publica de la privada)
  3. Fichero AGENT_SIGNING_PUBLIC_PEM_PATH (si esta definido)

La clave se sube como config.publicKeySignatureVerifier del IdP broker
`agent-poc-jwt-broker` (alias por defecto).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request


KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8180")
REALM        = os.getenv("REALM",        "agent-poc")
ADMIN_USER    = os.getenv("ADMIN_USER",    "admin")
ADMIN_PASS    = os.getenv("ADMIN_PASS",    "admin")
IDP_ALIAS     = os.getenv("IDP_ALIAS",     "agent-poc-jwt-broker")
CLI_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_DIR     = os.path.join(CLI_DIR, "agent-python")


def get_admin_token() -> str:
    data = f"username={ADMIN_USER}&password={ADMIN_PASS}&grant_type=password&client_id=admin-cli"
    req = urllib.request.Request(
        f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token",
        data=data.encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    return json.loads(urllib.request.urlopen(req).read())["access_token"]


def load_public_pem_from_agent() -> str:
    """
    Extrae la clave publica llamando al agente Python.
    Forma mas robusta: el propio agente expone AGENT_SIGNING_PUBLIC_PEM.
    """
    # Opcion 1: variable de entorno
    pub = os.getenv("AGENT_SIGNING_PUBLIC_PEM")
    if pub:
        return pub

    # Opcion 2: ejecutar el agente en un subprocess y leer la pem.
    # Hack PoC: el agente imprime su pub en formato PEM si se le pasa
    # el flag --export-public-key.
    code = (
        "import sys; sys.path.insert(0, %r); "
        "from config import AGENT_SIGNING_PUBLIC_PEM; "
        "print(AGENT_SIGNING_PUBLIC_PEM)"
    ) % AGENT_DIR
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def get_idp(tok: str) -> dict:
    req = urllib.request.Request(
        f"{KEYCLOAK_URL}/admin/realms/{REALM}/identity-provider/instances/{IDP_ALIAS}",
        headers={"Authorization": f"Bearer {tok}"},
    )
    return json.loads(urllib.request.urlopen(req).read())


def put_idp(tok: str, idp: dict) -> None:
    req = urllib.request.Request(
        f"{KEYCLOAK_URL}/admin/realms/{REALM}/identity-provider/instances/{IDP_ALIAS}",
        data=json.dumps(idp).encode(),
        method="PUT",
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
    )
    urllib.request.urlopen(req).read()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="Muestra cambios sin aplicarlos")
    args = p.parse_args()

    print(f"[1/4] Obteniendo token admin de {KEYCLOAK_URL} ...")
    tok = get_admin_token()
    print(f"      OK token length={len(tok)}")

    print(f"[2/4] Cargando clave publica del agente (RS256) ...")
    pub_pem = load_public_pem_from_agent()
    if not pub_pem.startswith("-----BEGIN PUBLIC KEY-----"):
        print(f"      FAIL: la clave no parece un PEM valido:")
        print(f"      >>>{pub_pem[:120]}<<<")
        return 1
    print(f"      OK {len(pub_pem)} bytes PEM, empieza por {pub_pem[:31]}")

    print(f"[3/4] GET IdP broker '{IDP_ALIAS}' ...")
    idp = get_idp(tok)
    print(f"      alias={idp.get('alias')} providerId={idp.get('providerId')}")
    print(f"      config.actual.publicKeySignatureVerifier = "
          f"<{len(idp['config'].get('publicKeySignatureVerifier', ''))} bytes>")

    new_pem_normalized = pub_pem.strip() + "\n"
    old_pem = idp["config"].get("publicKeySignatureVerifier", "")
    if old_pem.strip() == new_pem_normalized.strip():
        print("      OK la clave publica ya esta registrada, sin cambios")
        return 0

    idp["config"]["publicKeySignatureVerifier"] = new_pem_normalized
    # Asegurar que la feature JWT_AUTH_GRANT esta activa en el IdP
    idp["config"].setdefault("jwtAuthorizationGrantEnabled",               "true")
    idp["config"].setdefault("jwtAuthorizationGrantAssertionSignatureAlg", "RS256")
    idp["config"].setdefault("jwtAuthorizationGrantAllowedClockSkew",      "30")
    # Quitar setting de algoritmo previo si lo habia (HS256/HS384/HS512 no funcionan)
    for wrong_alg in ("HS256", "HS384", "HS512"):
        if idp["config"].get("jwtAuthorizationGrantAssertionSignatureAlg") == wrong_alg:
            print(f"      WARN: removiendo algoritmo invalido {wrong_alg}")
            idp["config"]["jwtAuthorizationGrantAssertionSignatureAlg"] = "RS256"
            break

    if args.dry_run:
        print("[4/4] DRY RUN — no se ha puesto nada en KC.")
        print(f"      Nueva publicKeySignatureVerifier: {len(new_pem_normalized)} bytes PEM")
        return 0

    print(f"[4/4] PUT IdP broker con nueva publicKeySignatureVerifier ...")
    put_idp(tok, idp)
    print(f"      OK {REALM}/{IDP_ALIAS} actualizado.")
    print()
    print("KC cachea los IdP en memoria. Si el agente ya ha hecho alguna")
    print("peticion, reinicia el contenedor KC para que tome la nueva clave:")
    print()
    print("   docker restart agent-poc-keycloak")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
