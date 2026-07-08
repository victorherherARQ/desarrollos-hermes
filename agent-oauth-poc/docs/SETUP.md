# SETUP · agent-oauth-poc — v2 (A+B+C)

> Guía paso-a-paso reproducible para levantar la PoC **`agent-oauth-poc`** v2 desde cero en una máquina nueva (WSL2 / Linux / macOS) y ejecutar los **3 flujos** A+B+C contra Keycloak 24 (o contra Azure B2C External ID).
>
> **Cambios clave v2**:
> - ❌ Eliminado password credentials grant (ROPC) — inseguro
> - ❌ Eliminado CIBA — sustituido por Auth Code + PKCE con MFA síncrono
> - ✅ Añadidos 3 flujos estándar: A (Auth Code + PKCE), B (Device Code), C (OBO)
> - ✅ Portable KC ↔ B2C: misma arquitectura, solo cambia `IDP_ISSUER`
>
> Tiempo total estimado: **~10 min** (de los cuales ~3 min son build de Spring Boot la primera vez).

---

## 1. TL;DR (60 segundos)

```bash
# 1) Clonar el repo
git clone https://github.com/victorherherARQ/desarrollos-hermes.git
cd desarrollos-hermes/agent-oauth-poc

# 2) Arrancar los 5 contenedores
docker compose up -d --build

# 3) Esperar a que Keycloak termine de arrancar
until curl -sf http://localhost:8180/realms/master/.well-known/openid-configuration > /dev/null; do
  sleep 3; echo "esperando Keycloak..."; done && echo "Keycloak ready"

# 4) Provisionar el realm "agent-poc" (sin password grant, con PKCE + Device Code)
KEYCLOAK_URL=http://localhost:8180 python3 scripts/create_realm.py --reset

# 5) Probar el flujo A — Auth Code + PKCE
curl -s -X POST http://localhost:7000/agente/auth/authorize \
  -H "Content-Type: application/json" \
  -d '{"user_id":"ana","scope":"openid profile email calendar.read"}' | jq .
# → recibe authorize_url + code_verifier + state

# 6) Health-check rápido
curl -s http://localhost:7000/agente/health | jq .
# → {"status":"UP","idp_issuer":"...","supported_flows":["A:auth_code+pkce","B:device_code","C:obo"]}
```

Si los 6 pasos anteriores pasan, **la PoC v2 está funcionando**.

---

## 2. Arquitectura en 30 segundos

```
┌──────────────────────────────────────────────┐
│                USUARIO (Humano)                │
│     (browser / smartphone — login en IdP)     │
└──────────────┬───────────────────────────────┘
               │ A: Auth Code + PKCE (browser)
               │    o B: Device Code (CLI sin UI)
               │
┌──────────────▼───────────────────────────────┐
│  client-mock (webapp del usuario)              │
│  :3000 (Node 18)                              │
│  - Recibe /auth/authorize del agente           │
│  - Redirige al browser del humano al IdP      │
│  - Gestiona el callback con PKCE              │
│  - Muestra Device Code si aplica              │
└──────────────┬───────────────────────────────┘
               │ (code, refresh_token)
               ▼
┌──────────────────────────────────────────────┐
│  agent-poc-agent-python (el agente IA)        │
│  :7000 (FastAPI)                              │
│  - Auth Code + PKCE handler                   │
│  - Device Code handler                        │
│  - OBO exchange (refinar scope)               │
│  - Llama a Spring API con Bearer              │
└──────┬──────────────────────┬────────────────┘
       │ JWT                  │ JWT
       │ (paso 1)             │ (paso 2)
┌──────▼─────────┐    ┌───────▼──────────────────────────────────┐
│  Keycloak 24    │    │  spring-boot-api (Resource Server)       │
│  :8180          │    │  :9090 (Java 17)                          │
│  (IdP, sin CIBA,│    │  - @PreAuthorize("hasAuthority('SCOPE_x)") │
│   PKCE+Device   │    └──────────────────────────────────────────┘
│   habilitados)  │
└──────┬──────────┘
       │ JDBC
┌──────▼──────────┐
│  PostgreSQL 16   │
│  (interno)       │
└──────────────────┘
```

### Mapeo de puertos host → servicio

| Puerto host | Servicio | Propósito | URL |
|---|---|---|---|
| **3000** | `client-mock` | Webapp Auth Code + PKCE + Device Code UI | http://localhost:3000 |
| **7000** | `agent-python` | API del agente IA | http://localhost:7000 |
| **8180** | `keycloak` | IdP — Admin + endpoints OIDC | http://localhost:8180/admin |
| **9090** | `spring-boot-api` | Resource Server protegido | http://localhost:9090/api/calendar/events, /api/email/send |
| **5432** | _no expuesto_ | Postgres vive dentro del cluster | — |

---

## 3. Requisitos previos

| Requisito | Versión mínima | Cómo verificar |
|---|---|---|
| WSL2 / Linux / macOS | Ubuntu 22.04 o similar | `uname -a` |
| Docker Engine | 24.0+ con `compose` v2 | `docker --version && docker compose version` |
| Python (host) | 3.11+ | `python3 --version` |
| `curl` | cualquier | `curl --version` |
| `jq` | cualquier | `jq --version` |
| RAM libre | 8 GB | `free -h` |
| Disco libre | 10 GB | `df -h ~` |

### Verificar puertos libres

```bash
for p in 3000 7000 8180 9090; do
  (echo > /dev/tcp/127.0.0.1/$p) 2>/dev/null \
    && echo "⚠️  Puerto $p OCUPADO" \
    || echo "✅  Puerto $p libre"
done
```

Si algún puerto está ocupado, edita `docker-compose.yml` y cambia el mapeo `"HOST_EXTERNO:PUERTO_INTERNO"`.

### Instalar `jq`

```bash
# Ubuntu / Debian (incluido WSL2)
sudo apt-get update && sudo apt-get install -y jq

# macOS
brew install jq
```

---

## 4. Instalación paso a paso

### Paso 1 · Clonar el repositorio

```bash
git clone https://github.com/victorherherARQ/desarrollos-hermes.git
cd desarrollos-hermes/agent-oauth-poc
```

Comprobar que estás en la raíz del proyecto:

```bash
ls -F
# debe verse:  agent-python/  client-mock/  docker-compose.yml  docs/  INSTRUCCIONES.md
#               keycloak/  README.md  scripts/  spring-boot-api/
```

### Paso 2 · Arrancar los contenedores

```bash
docker compose up -d --build
```

- **Primera ejecución**: ~3 min (descarga imágenes + compilación Maven de Spring Boot).
- **Siguientes ejecuciones**: ~15-25 s (reutiliza caché de capas y volumen de Postgres).

Verificar:

```bash
docker compose ps
```

Salida esperada (5 servicios, columna `State` todos `running` o `Up`):

```
NAME                          STATUS
agent-poc-postgres            Up (healthy)
agent-poc-keycloak            Up
agent-poc-spring-boot-api     Up
agent-poc-agent-python        Up
agent-poc-client-mock         Up
```

### Paso 3 · Esperar a que Keycloak arranque

```bash
until curl -sf http://localhost:8180/realms/master/.well-known/openid-configuration > /dev/null; do
  printf '.'; sleep 3
done
echo
echo "✅ Keycloak ready"
```

Si se eterniza (>2 min), mira los logs:

```bash
docker logs agent-poc-keycloak --tail 30
```

### Paso 4 · Crear el realm y todo lo necesario (v2 spec)

**Importante**: en v2, el script NO habilita `directAccessGrantsEnabled` (ROPC) ni CIBA. Habilita PKCE + Device Code.

```bash
KEYCLOAK_URL=http://localhost:8180 python3 scripts/create_realm.py --reset
```

El `--reset` borra el realm `agent-poc` si existía y lo recrea desde cero. **Es seguro ejecutarlo varias veces**.

Output esperado:
```
[1/7] Realm 'agent-poc'
  ...
[2/7] Custom client-scopes (con fix KC 24)
[3/7] Usuarios demo (ana/luis/marta)
[4/7] Cliente confidencial 'agente-ia' (A+B+C)
[4b/7] Cliente confidential 'client-mock' (webapp del usuario)
[5/7] Asignando custom scopes al cliente agente-ia (sub-endpoint)
[6/7] Realm default scopes (openid/profile/email)
[7/7] Verificación end-to-end
  ✅ agente-ia: standardFlow=true, directAccess=false, device=true
  ✅ ROPC bloqueado correctamente
```

### Paso 5 · Reiniciar contenedores con el código nuevo

> ⏸ **Operación manual requerida**
> Después del primer build y de cualquier cambio de código en `agent-python/` o `client-mock/`, los contenedores deben restart:
>
> ```bash
> docker restart agent-poc-agent-python agent-poc-client-mock
> ```
>
> Esto es necesario para que carguen el código Python/Node nuevo. KC, postgres y Spring Boot NO necesitan restart (sus imágenes están fijadas).

### Paso 6 · Verificación rápida

```bash
# Health del agente (debería listar los 3 flujos)
curl -s http://localhost:7000/agente/health | jq .
# → {
#     "status": "UP",
#     "idp_issuer": "http://keycloak:8080/realms/agent-poc",
#     "agent_client_id": "agente-ia",
#     "supported_flows": ["A:auth_code+pkce", "B:device_code", "C:obo"]
#   }

# Health del client-mock
curl -s http://localhost:3000/healthz | jq .
# → { "status": "UP", "idp": "...", "is_b2c": false }

# Health de Spring Boot
curl -s http://localhost:9090/health | jq .

# Health de Keycloak
curl -s http://localhost:8180/health/ready | jq .

# Catálogo OIDC del realm recién creado
curl -s http://localhost:8180/realms/agent-poc/.well-known/openid-configuration | \
  jq '.issuer, .grant_types_supported, .authorization_endpoint, .device_authorization_endpoint'
```

---

## 5. Tests end-to-end — Los 3 flujos

### Test A · Auth Code + PKCE (`scope: calendar.read`)

Este test **requiere un browser humano real** (o un flow automatizado tipo Playwright/Puppeteer). En PoC lo más simple es usar la UI web:

```bash
# Paso 1: el cliente pide al agente una authorize URL
RESP=$(curl -s -X POST http://localhost:7000/agente/auth/authorize \
  -H "Content-Type: application/json" \
  -d '{"user_id":"ana","scope":"openid profile email calendar.read"}')
echo "$RESP" | jq .
# {
#   "authorize_url": "http://localhost:8180/realms/agent-poc/protocol/openid-connect/auth?...",
#   "code_verifier": "...",
#   "state": "...",
#   "redirect_uri": "http://localhost:3000/auth/callback"
# }

# Paso 2: el HUMANO abre authorize_url en su browser.
#         KC le presenta la pantalla de login.
#         Ana mete su usuario + password.
#         KC redirige a client-mock/callback?code=...&state=...
#         client-mock intercambia el code por tokens, los guarda.

# Paso 3: una vez completado el flujo, el cliente-mock devuelve
#         los tokens via /auth/session/<sid>
```

**Cómo automatizar completamente** (sin browser del humano, modo headless):

```bash
# Solo viable si ya tienes un user logged-in de una sesión KC previa.
# Para demo en vivo, usa la UI.
```

### Test B · Device Code Flow (headless)

```bash
# Paso 1: pedir device_code al agente
RESP=$(curl -s -X POST http://localhost:7000/agente/auth/device \
  -H "Content-Type: application/json" \
  -d '{"user_id":"ana","scope":"openid profile email calendar.read"}')
echo "$RESP" | jq .
# {
#   "user_code": "ABCD-1234",
#   "device_code": "...",
#   "verification_uri": "http://localhost:8180/realms/agent-poc/device",
#   "verification_uri_complete": "...",
#   "expires_in": 600,
#   "interval": 5
# }

# Paso 2: HUMANO va a http://localhost:8180/realms/agent-poc/device
#         (o abre la página dedicada /device?user_code=...)
#         Introduce user_code y aprueba.

# Paso 3: el agente, internamente, recibirá los tokens vía polling.
#         Para validar, puedes pedir al cliente-mock los tokens
#         usando /auth/session/<sid> (no aplica en Device Code,
#         que es por canal backchannel).
```

### Test C · OBO exchange (refinar scope)

> ⚠️ **Limitación KC 24**: Keycloak 24 NO soporta `requested_token_use=on_behalf_of` nativamente. Requiere KC 26+. Mientras tanto, en `app.py:230-310` el agente pide el scope completo en el paso A y verifica si el JWT lo tiene — si no, **en lugar de** hacer OBO (que fallaría), devuelve 400 explicando que el scope no está disponible.
>
> En Azure B2C External ID esto funciona nativo.

### Test negativo · Token sin scope → 401/403

```bash
# Conseguir un token SIN scope calendar.read (sólo openid/email/profile)
TOKEN=$(curl -s -X POST http://localhost:8180/realms/agent-poc/protocol/openid-connect/token \
  -d 'grant_type=password' \
  -d 'client_id=agente-ia' \
  -d 'client_secret=secret-del-agente' \
  -d 'username=ana' \
  -d 'password=demo1234' \
  -d 'scope=openid' | jq -r .access_token)

# Llamar a /api/calendar/events con ese token → debe fallar
curl -i "http://localhost:9090/api/calendar/events?user_id=ana" \
     -H "Authorization: Bearer *** | head -n 1
# Esperado: HTTP/1.1 401 (o 403 según config de Spring Security)
```

> **Nota**: este test usa ROPC password grant solo para **validar la API de Spring**, no como flujo del agente. Es legítimo en un test negativo, porque el agente real NUNCA usa ROPC.

---

## 6. Cómo ver logs y debug

### Logs por servicio

```bash
docker logs agent-poc-keycloak          # Keycloak 24 (Quarkus)
docker logs agent-poc-spring-boot-api    # API Spring Boot
docker logs agent-poc-agent-python       # Agente IA (FastAPI)
docker logs agent-poc-client-mock        # Webapp (Node 18)
docker logs agent-poc-postgres           # Postgres 16
```

### Todos los logs en una sola vista

```bash
docker compose logs -f --tail 50
```

Streaming por servicio:

```bash
docker compose logs -f agent-python
docker compose logs -f client-mock
```

### Entrar en un contenedor

```bash
docker exec -it agent-poc-keycloak /bin/bash
docker exec -it agent-poc-spring-boot-api /bin/sh
docker exec -it agent-poc-agent-python /bin/sh
docker exec -it agent-poc-postgres psql -U keycloak -d keycloak
```

### Filtros útiles

```bash
# Solo requests HTTP del agente
docker logs agent-poc-agent-python 2>&1 | grep -E "POST|GET"

# Solo los flujos OAuth por letra
docker logs agent-poc-agent-python 2>&1 | grep -E "\[A\]|\[B\]|\[C\]"

# Errores en cualquier servicio
docker compose logs 2>&1 | grep -iE "error|warn|exception"
```

---

## 7. Operaciones frecuentes (cheatsheet)

### Parar todo (conservando datos)

```bash
docker compose down
```

### Parar y borrar TODO (incluye DB de Keycloak)

```bash
docker compose down -v
```

> Usar cuando el realm está corrupto o los `CUSTOM_SCOPES` cambiaron.

### Reconstruir un solo servicio

```bash
docker compose build spring-boot-api
docker compose up -d spring-boot-api
```

Misma forma con `agent-python`, `keycloak`, `client-mock`.

### Restart tras cambio de código

```bash
# Después de modificar agent-python/ o client-mock/
docker restart agent-poc-agent-python agent-poc-client-mock
```

### Reiniciar Keycloak sin perder datos

```bash
docker restart agent-poc-keycloak
# Esperar a que esté ready:
until curl -sf http://localhost:8180/realms/master/.well-known/openid-configuration > /dev/null; do sleep 3; done
echo "ready"
# Re-aplicar spec del realm (idempotente):
KEYCLOAK_URL=http://localhost:8180 python3 scripts/create_realm.py
```

### Borrar y recrear solo el realm (sin tocar contenedores)

```bash
KEYCLOAK_URL=http://localhost:8180 python3 scripts/create_realm.py --reset
```

---

## 8. Troubleshooting (problemas comunes y soluciones)

### El agente devuelve `invalid_scope`

Síntoma: pedir `calendar.read` o `email.send` da `400 invalid_scope`.

Causa: los custom scopes no están asignados al cliente `agente-ia`.

Solución:

```bash
KEYCLOAK_URL=http://localhost:8180 python3 scripts/create_realm.py
```

El script re-asigna automáticamente vía sub-endpoint dedicado.

Ver detalle en [POOL.md §5](../../docs/POOL.md).

### 401/403 inesperados en Spring Boot

Causa: el `scope` en el JWT no coincide con el del `@PreAuthorize`.

Diagnóstico: decodificar el JWT en [jwt.io](https://jwt.io).

### Cliente-mock no recibe el callback

Causa: navegador bloquea el redirect por CORS / third-party cookies.

Solución: usar la UI en `http://localhost:3000/` (mismo origen) o deshabilitar bloqueador.

### Device Code no llega al `verification_uri`

Causa: el navegador del humano va a `http://localhost:8180/realms/agent-poc/device` que SOLO existe si KC está arrancado. Usar la UI dedicada `/device?user_code=...` que sí es accesible.

---

## 9. Cómo migrar de Keycloak a Azure B2C

```yaml
# override de docker-compose (o vía .env)
services:
  agent-python:
    environment:
      IDP_ISSUER: https://<tenant>.ciamlogin.com/<tenant_id>.onmicrosoft.com
      AGENT_CLIENT_ID: <app-registration-id-de-B2C>
      AGENT_CLIENT_SECRET: <secret-de-B2C>
  client-mock:
    environment:
      IDP_ISSUER: https://<tenant>.ciamlogin.com/<tenant_id>.onmicrosoft.com
      AGENT_CLIENT_ID: <app-registration-id-de-B2C>
      AGENT_CLIENT_SECRET: <secret-de-B2C>
      B2C_USER_FLOW: signup_signin_v1
```

**Sin tocar código**: `agent-python/config.py:25-40` detecta B2C automáticamente.

Para el `KEYCLOAK_URL` (en el script de bootstrap del realm), en B2C se reemplaza por lógica diferente — ver `ESTUDIO_AZURE_B2C.md §6` y `§7`.

---

**Mantenedor**: Víctor (khum1982) + Hermes Agent.
**Stack PIN**: `keycloak:24.0.5`, `spring-boot:3.2.5`, `java:17`, `python:3.11`, `node:18`, `postgres:16`.
**Para B2C**: `azure-entra-external-id` (ciamlogin.com).
