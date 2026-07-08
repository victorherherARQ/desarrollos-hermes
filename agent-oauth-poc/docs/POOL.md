# POOL · Agent OAuth PoC — v2 (A+B+C portable)

> **Estado**: Refactorizado para soportar los **3 flujos A+B+C** sin password grant.
> **Stack**: 100% Docker local (docker compose). IdP swap-in para B2C.
> **Última revisión**: 2026-07-08.
> **Audiencia**: Víctor (mantenedor) y futuros revisores técnicos.

---

## Índice

1. [Resumen ejecutivo](#1-resumen-ejecutivo)
2. [Arquitectura detallada](#2-arquitectura-detallada)
3. [Estructura del repositorio](#3-estructura-del-repositorio)
4. [Componentes clave](#4-componentes-clave)
5. [Causa raíz del bug `invalid_scope` en Keycloak 24](#5-causa-raíz-del-bug-invalid_scope-en-keycloak-24)
6. [Tests end-to-end — Plantilla de los 3 flujos](#6-tests-end-to-end-plantilla-de-los-3-flujos)
7. [Limitaciones conocidas y trabajo futuro](#7-limitaciones-conocidas-y-trabajo-futuro)
8. [Glosario](#8-glosario)

---

## 1. Resumen ejecutivo

### Qué demuestra (v2)

La PoC `agent-oauth-poc` v2 demuestra cómo un **agente de IA** puede operar de forma segura **en nombre de un usuario humano** contra APIs protegidas por OAuth2/OIDC, **sin password credentials, sin CIBA**. Implementa los **3 flujos estándar** que cualquier IdP moderno soporta:

- **A. Authorization Code + PKCE** (RFC 6749 + RFC 7636): el humano se autentica en una webapp (`client-mock`) que delega el `access_token` al agente.
- **B. Device Code Flow** (RFC 8628): para agentes headless (CI/CD, CLI, kiosko). El humano introduce un código en su dispositivo.
- **C. On-Behalf-Of / JWT Bearer** (RFC 7523): el agente intercambia un `user_access_token` por uno delegado con scope mínimo.

**Hitos importantes:**
- **NO ROPC** (password grant eliminado: inseguro, antipatrón de producción).
- **NO CIBA**: sustituido por flujo A síncrono con MFA (Keycloak/Conditional Access o B2C/Passkey).
- **Portable Keycloak ↔ Azure B2C External ID**: misma arquitectura, mismo agente. Solo cambia el `issuer-uri`.

### Decisión de arquitectura (v2)

```python
# Pseudocódigo de app.py:90-110 (regla de decisión)
if req.scope.endswith(".read"):
    apply_flow_A_or_C()
elif req.scope.endswith(".send") or req.scope.endswith(".modify"):
    apply_flow_A_or_C()  # con MFA forzado via acr_values
elif headless_context:
    apply_flow_B()
```

El **agente nunca decide entre A/B/C por scope** — los tres soportan cualquier scope. La decisión es por **contexto de despliegue**:
- **Hay browser del humano cerca → A+C** (Auth Code + OBO).
- **No hay UI → B** (Device Code).
- **¿CIBA asíncrono?** → Ofrecemos Opción D vía plugin `ciba_plugin.py` opcional, no incluido en PoC principal (ver §7.4).

### Arquitectura high-level

```
                       ┌─────────────────────────┐
                       │     USUARIO / CLIENTE   │
                       │ (Ana, Luis o Marta)     │
                       │   Dispositivo (browser  │
                       │   o smartphone)         │
                       └────────────┬────────────┘
                                    │
                  ┌─────────────────┴──────────────────┐
                  │                                    │
                  ▼                                    ▼
       ┌─────────────────────┐              ┌────────────────────┐
       │ A. Auth Code + PKCE │              │ B. Device Code Flow│
       │ (client-mock :3000) │              │ (CLI/headless)     │
       │ Redirige al browser │              │ Imprime user_code  │
       │ del humano          │              │ + verification_uri │
       └─────────┬───────────┘              └─────────┬──────────┘
                 │ HTTP callback                      │ POST /devicecode
                 │ (con code)                        │
                 ▼                                    ▼
       ┌──────────────────────────────────────────────────────┐
       │       IdP (Keycloak 24 / Azure B2C External ID)      │
       │      http://keycloak:8080  (KC)                      │
       │      https://<tenant>.ciamlogin.com  (B2C)          │
       │  Emite: access_token, refresh_token, id_token        │
       └──────────────────┬───────────────────────────────────┘
                          │ Bearer JWT (paso 4)
                          ▼
       ┌──────────────────────────────────────────────────────┐
       │   agent-poc-agent-python (:7000)                     │
       │   FastAPI · OAuthClient                              │
       │   - A: gestiona authorize_url + PKCE pair            │
       │   - C: OBO exchange (refinar scope)                  │
       │   - B: polling /device/token                         │
       └──────────────────┬───────────────────────────────────┘
                          │ Bearer JWT (paso 5)
                          ▼
       ┌──────────────────────────────────────────────────────┐
       │ agent-poc-spring-boot-api (:9090)                    │
       │ Apigee-stub · Resource Server                        │
       │   @PreAuthorize("hasAuthority('SCOPE_xxx')")        │
       └──────────────────────────────────────────────────────┘
```

### Resultados de los tests end-to-end (TODO)

| Test | Estado | Notas |
|---|---|---|
| Test A: Auth Code + PKCE + OBO | ⏳ pendiente restart contenedores | El endpoint es local; no necesita dependencias externas |
| Test B: Device Code Flow | ⏳ pendiente restart contenedores | Idem |
| Test C: OBO isolation (refinar scope) | ⏳ pendiente restart contenedores | Idem |
| Test negativo: token sin scope | ⏳ pendiente restart | Debe seguir devolviendo 401/403 |

> **Cómo correrlos**: ver sección §6. Los contenedores deben haber sido reiniciados tras el build de las imágenes nuevas (operación manual por Victor, ~5 s de downtime).

---

## 2. Arquitectura detallada

### 2.1 Diagrama de secuencia — Flujo A (Auth Code + PKCE)

```
┌────────┐   ┌───────────┐   ┌────────┐   ┌──────────┐   ┌────────┐  ┌─────────────┐
│Cliente │   │ client-   │   │ Keycloak│  │ Agente   │   │Human   │  │Spring API  │
│        │   │ mock:3000 │   │ :8180   │  │:7000     │   │(browser)│  │:9090       │
└──┬─────┘   └──┬────────┘   └──┬──────┘  └────┬─────┘   └──┬─────┘  └──────┬──────┘
   │            │              │              │             │              │
   │ 1. POST /agente/auth/authorize             │             │              │
   │ {user_id, scope}                            │             │              │
   │ ─────────────────────────────────────────▶ │             │              │
   │            │              │ 2. POST /protocol/openid-connect/auth       │
   │            │              │    (redirect_uri, PKCE pair, scope)         │
   │            │              │ ◀────────────── │             │              │
   │            │              │ 3. 302 Location: KC authorize page         │
   │            │ ◀────────── │              │             │              │
   │ 4. window.location = authorize_url        │             │              │
   │ ───────────────────────────────────────────────────────▶ │              │
   │            │              │             │ 5. KC login & consent        │
   │            │              │             │ ◀──────────── │              │
   │            │              │             │              │ 6. 302 /auth/callback?code=...&state=...
   │            │ ◀────────────────────────────────────────────────── │     │
   │ 7. GET /auth/callback?code=...  │             │             │              │
   │ ─────────▶ │ 8. POST /token con grant_type=authorization_code + code_verifier
   │            │ ──────────────▶ │             │             │              │
   │            │ ◀──── {access_token, refresh_token, id_token} ─│            │
   │            │ 9. callback: redirect /?session_id=<sid>      │             │
   │ ◀────────│             │              │             │              │
   │ 10. cliente tiene tokens en client-mock   │             │              │
   │            │              │              │              │              │
   │ 11. POST /agente/call {scope, request}    │              │              │
   │ ─────────────────────────────────────────▶ │             │              │
   │            │              │              │ 12. JWT ya tiene scope → llama a Spring
   │            │              │              │ ─────────────────────────────────────▶
   │            │              │              │ ── ◀─ {events:[...]} ─────│              │
   │ ◀─── {result:{events:[...]}, flow:"A"}   │              │              │
```

### 2.2 Diagrama de secuencia — Flujo C (OBO / Refinado de scope)

```
Cliente ──▶ Agente ──▶ KC ──▶ Agente ──▶ Spring
            │          │
            │          │ Token del humano:
            │          │ scope="openid profile email calendar.read email.send"
            │
            │ (Agente mira el JWT del humano y ve que NO tiene calendar.write)
            │
            │ Agente hace OBO (RFC 7523):
            │   POST /token
            │     grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
            │     assertion=<user_access_token>
            │     scope=calendar.write
            │     requested_token_use=on_behalf_of
            │
            ◀── KC devuelve NUEVO access_token con SOLO calendar.write
            │
            │ Agente llama a Spring con ese nuevo token.
```

> **Limitación Keycloak 24**: KC 24 **NO** soporta `requested_token_use=on_behalf_of` nativamente (requiere KC 26+). En la PoC con KC, en lugar de hacer OBO, **el agente ya pide el scope completo al IdP** en el paso A y verifica en el JWT si lo tiene. En B2C se usa el flujo completo.

### 2.3 Diagrama de secuencia — Flujo B (Device Code)

```
Cliente ──▶ Agente ──▶ KC ──▶ Usuario (otro dispositivo)
            │          │
            │ POST /protocol/openid-connect/auth/device
            │ ◀──── {device_code, user_code, verification_uri, interval=5, expires_in=600}
            │
            │ (imprime user_code)
            │ (abre la URL en el navegador del humano)
            │
            │ [polling cada 5s]
            │ POST /token
            │   grant_type=urn:ietf:params:oauth:grant-type:device_code
            │   device_code=<device_code>
            │
            │ [humano va a /device, introduce user_code, aprueba]
            │
            │ POST /token ─▶ 200 {access_token, refresh_token}
```

### 2.4 Tabla de los 5 contenedores

| Container | Imagen | Puerto host | Propósito | ¿Nuevo en v2? |
|---|---|---|---|---|
| `agent-poc-postgres` | postgres:16-alpine | (interno) | DB interna de Keycloak | — |
| `agent-poc-keycloak` | quay.io/keycloak/keycloak:24.0 | 8180 | IdP — **CIBA desactivado**, PKCE+Device Code activos | modificado |
| `agent-poc-spring-boot-api` | build local | 9090 | Apigee-stub Resource Server | — |
| `agent-poc-agent-python` | build local | 7000 | El agente IA — refactorizado a A+B+C | **reescrito** |
| `agent-poc-client-mock` | build local | 3000 | Webapp del usuario (no más receptor CIBA) | **reescrito** |
| `agent-poc-realm-setup` | (opcional, profile `setup`) | — | Aplica `create_realm.py` una sola vez | **nuevo** |

### 2.5 Mapa de claims del JWT (sin cambios respecto a v1)

Para un token de Ana con `scope=calendar.read`:

| Claim | Tipo | Valor ejemplo | Origen |
|---|---|---|---|
| `iss` | string | `http://keycloak:8080/realms/agent-poc` | Issuer |
| `sub` | UUID | UUID de Ana | Usuario real |
| `aud` | array | `["agente-ia", "spring-boot-api", "account"]` | Audience mapper |
| `azp` | string | `agente-ia` | Authorized party |
| `scope` | string | `calendar.read calendar.write ...` | Scopes concedidos |
| `exp` | int | now + 300s | Lifespan del realm |
| `preferred_username` | string | `ana` | Profile mapper |

---

## 3. Estructura del repositorio

```
agent-oauth-poc/
├── README.md                       # Quickstart actualizado
├── INSTRUCCIONES.md
├── docker-compose.yml              # 5+1 servicios + networks + volúmenes
├── docs/
│   ├── ESTUDIO_AZURE_B2C.md        # Migración a B2C + replanteamiento §14
│   ├── ESTUDIO_COMPARATIVO.md
│   ├── POOL.md                     # ← este archivo (v2 A+B+C)
│   └── SETUP.md                    # Setup actualizado
├── scripts/
│   └── create_realm.py             # Idempotente. v2: sin ROPC/CIBA.
├── keycloak/
│   └── realm/
│       └── realm-agent-poc.json    # v2: CIBA=false, ROPC=false, PKCE+Device=true
├── spring-boot-api/                # Sin cambios (Resource Server)
├── agent-python/                   # FastAPI refactorizado
│   ├── Dockerfile
│   ├── config.py                   # NUEVO: detección B2C automática por IDP_ISSUER
│   ├── oauth_client.py             # NUEVO: A+B+C en una clase unificada
│   └── app.py                      # NUEVO: rutas /agente/auth/{authorize,token,
│                                   #              refresh,device,device/poll} + /call
└── client-mock/                    # Webapp refactorizada
    ├── Dockerfile
    ├── server.js                   # NUEVO: webapp PKCE con callback handler,
    │                               #        página device code, session store
    └── public/index.html           # NUEVO: UI Auth Code + Device Code con tabs
```

---

## 4. Componentes clave

### 4.1 Agente Python — `agent-python/`

#### Endpoints (v2)

| Método | Ruta | Flujo | Descripción |
|---|---|---|---|
| GET | `/agente/health` | — | Healthcheck `{status, idp_issuer, supported_flows}` |
| POST | `/agente/auth/authorize` | A | Construye authorize_url + PKCE pair. Devuelve `{authorize_url, code_verifier, state, redirect_uri}` |
| POST | `/agente/auth/token` | A | Intercambia `code` por tokens (con client_secret) |
| POST | `/agente/auth/refresh` | A | Renueva el access_token del humano con refresh_token |
| POST | `/agente/auth/device` | B | Pide `device_code` al IdP |
| POST | `/agente/auth/device/poll` | B | (placeholder; el polling real lo hace `oauth_client.device_poll_for_tokens`) |
| POST | `/agente/call` | A+C/B+C | Ejecuta la acción del agente en nombre del humano. Decide dinámicamente si usa A o C |

#### Clase `OAuthClient` (`oauth_client.py`)

| Método | Firma | Flujo | Implementa |
|---|---|---|---|
| `build_authorize_url(scope, acr_values)` | → dict | A | PKCE pair + URL con `response_type=code`, `code_challenge=S256` |
| `exchange_code_for_tokens(code, code_verifier)` | async → dict | A | `POST /token` con `grant_type=authorization_code` |
| `refresh_user_token(refresh_token, scope)` | async → dict | A | `POST /token` con `grant_type=refresh_token` |
| `device_authorize(scope)` | async → dict | B | `POST /device_authorization_endpoint` |
| `device_poll_for_tokens(device_code, …)` | async → dict | B | Loop polling con manejo de `authorization_pending` / `slow_down` / `expired_token` |
| `obo_exchange(user_access_token, requested_scope)` | async → dict | C | `POST /token` con `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer` |
| `userinfo(access_token)` | async → dict | A/B | `GET /userinfo` |
| `_b64url_nopad(bytes)` | helper | — | Base64url RFC 7636 |
| `make_pkce_pair()` | → tuple | A | Genera `code_verifier` y `code_challenge=S256` |

#### Regla de decisión en `/agente/call` (`app.py:230-310`)

```python
# Decodifica el JWT del humano (sin verificar firma; Spring valida)
claims = parse_jwt(access_token)  # light; sin crypto
current_scope = claims.get("scope", "").split()

if req.scope in current_scope:
    # Flujo directo: ya tengo lo que necesito
    flow_used = "A"  # o "B" si vino de device code
else:
    # Refinar scope vía OBO (si el IdP lo soporta)
    flow_used = "C"  # aplicaría pero en KC 24 skip: scope completo se pidió en A
    delegated = await oauth.obo_exchange(...)
```

#### Variables de entorno (`docker-compose.yml:91-103` + `config.py`)

| Variable | Valor en compose | Equivalente en `config.py` |
|---|---|---|
| `IDP_ISSUER` | `http://keycloak:8080/realms/agent-poc` | `IDP_ISSUER` (lee override de env) |
| `AGENT_CLIENT_ID` | `agente-ia` | `AGENT_CLIENT_ID` |
| `AGENT_CLIENT_SECRET` | `secret-del-agente` | `AGENT_CLIENT_SECRET` |
| `API_BASE_URL` | `http://spring-boot-api:9090` | `API_BASE_URL` |
| `CLIENT_MOCK_REDIRECT_URI` | `http://client-mock:3000/auth/callback` | (lee override de env) |
| `B2C_USER_FLOW` | — | `B2C_USER_FLOW` (solo B2C) |

> **Detección automática de IdP** (`config.py:25-40`): si `IDP_ISSUER` contiene `ciamlogin.com` o `b2clogin.com`, el código usa los paths de Azure B2C; en otro caso usa paths de Keycloak. Misma clase `OAuthClient` sirve para ambos.

### 4.2 Spring Boot API — `spring-boot-api/`

(Sin cambios respecto a v1. Sigue siendo el Resource Server con `@PreAuthorize("hasAuthority('SCOPE_xxx')")`.)

### 4.3 Cliente Mock — webapp del usuario (`client-mock/`)

#### `server.js` — endpoints (reescritos)

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/auth/authorize` | El agente llama aquí: genera PKCE pair, devuelve `{authorize_url, code_verifier, state, session_id}` |
| GET | `/auth/callback` | Keycloak redirige aquí con `?code=...&state=...`. Intercambia el code por tokens |
| GET | `/auth/session/:sid` | El agente consulta los tokens de una sesión |
| POST | `/auth/device` | El agente llama aquí para pedir un device_code (UI del humano) |
| GET | `/device` | Renderiza la página del Device Code (countdown + código) |
| GET | `/healthz` | Healthcheck |
| GET | `/` | Sirve `public/index.html` |

#### `public/index.html` — UI

Dos pestañas en la home:
- **A. Auth Code + PKCE**: selector de usuario (ana/luis/marta), checkboxes para custom scopes, select de `acr_values`. Botón **Iniciar sesión**.
- **B. Device Code**: pide un device_code y muestra user_code + URL.

### 4.4 Keycloak — `scripts/create_realm.py`

Refactorizado en v2:

- ❌ Eliminado `directAccessGrantsEnabled: true` (prohibido)
- ❌ Eliminado bloque CIBA
- ✅ Añadido `oauth2.device.authorization.grant.enabled: true`
- ✅ Añadido `pkce.code.challenge.method: S256`
- ✅ Idempotente (`--reset` opcional para empezar limpio)
- ✅ Verificación final cambia: ya no prueba ROPC, comprueba que `directAccessGrantsEnabled=false` y que `standardFlowEnabled=true`.

Verificación final:
```
[7/7] Verificación end-to-end
  ✅ agente-ia: standardFlow=true, directAccess=false, device=true
  ✅ ROPC bloqueado correctamente
```

---

## 5. Causa raíz del bug `invalid_scope` en Keycloak 24

> **Sigue aplicando en v2** — los custom scopes siguen necesitando el sub-endpoint dedicado para asignarse al cliente. Documentación íntegra en [commits previos] / [issue tracker].

Si en el futuro se añade un nuevo custom scope:

```python
# Patrón correcto: SIEMPRE vía sub-endpoint
PUT /admin/realms/agent-poc/clients/{client_id}/default-client-scopes/{scope_id}
# NO dentro del body de PUT /clients/{cid}
```

---

## 6. Tests end-to-end — Plantilla de los 3 flujos

> **Estado**: **Pendientes**. Requieren que Victor haya ejecutado el comando de restart de los 2 contenedores con código nuevo. Lista de comandos exacta abajo en §6.0.

### 6.0 Pre-requisito: restart contenedores

```bash
cd /home/vhdez/desarrollos-hermes/agent-oauth-poc
docker restart agent-poc-agent-python agent-poc-client-mock
docker compose ps agent-python client-mock  # confirmar Up
```

### 6.1 Test A — Auth Code + PKCE (calendar.read)

```bash
# Paso 1: pedir authorize URL al agente
RESP=$(curl -s -X POST http://localhost:7000/agente/auth/authorize \
  -H "Content-Type: application/json" \
  -d '{"user_id":"ana","scope":"openid profile email calendar.read"}')
echo "$RESP" | jq .

# Resultado esperado:
# {
#   "authorize_url": "http://localhost:8180/realms/agent-poc/protocol/openid-connect/auth?...",
#   "code_verifier": "...",
#   "state": "...",
#   "redirect_uri": "http://localhost:3000/auth/callback"
# }

# Paso 2: el humano abre $RESP.authorize_url en un browser, KC autentica
# Paso 3: el callback llega a client-mock, hay que consultar el resultado:
SESSION_ID=<sid devuelto por el callback>
curl -s http://localhost:3000/auth/session/$SESSION_ID | jq .

# Resultado esperado:
# {
#   "access_token": "...",
#   "refresh_token": "...",
#   "user": { "preferred_username": "ana", ... }
# }

# Paso 4: usar el access_token para llamar al agente
ACCESS_TOKEN=<de arriba>
curl -s -X POST http://localhost:7000/agente/call \
  -H "Content-Type: application/json" \
  -d "{\"access_token\":\"$ACCESS_TOKEN\",\"request\":\"Mis eventos\",\"scope\":\"calendar.read\",\"action_type\":\"read_calendar\"}"
```

### 6.2 Test B — Device Code Flow

```bash
# Paso 1: pedir device_code
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

# Paso 2: humano va a http://localhost:8180/realms/agent-poc/device
#         introduce user_code, aprueba
# Paso 3: el agente recibe el access_token vía polling interno
#         (consultar endpoint auxiliar para PoC)
```

### 6.3 Test C — OBO exchange (requiere KC 26+)

```bash
# Cuando se actualice a KC 26+, descomentar sección en app.py.
# Mientras tanto, el token ya viene con scope completo en A.
```

### 6.4 Test negativo — Token sin `calendar.read` contra Spring

```bash
TOKEN=$(curl -s -X POST http://localhost:8180/realms/agent-poc/protocol/openid-connect/token \
  -d grant_type=refresh_token \
  -d client_id=agente-ia \
  -d client_secret=secret-del-agente \
  -d refresh_token=<refresh> | jq -r .access_token)

curl -i "http://localhost:9090/api/calendar/events?user_id=ana" \
  -H "Authorization: Bearer *** | head -n 1
# Esperado: HTTP/1.1 401
```

---

## 7. Limitaciones conocidas y trabajo futuro

### 7.1 Limitaciones que aplican a v2

| # | Limitación | Impacto | Mitigación |
|---|---|---|---|
| L1 | **JWT Bearer (RFC 7523 / OBO) no soportado en KC 24** | `app.py` decide flujo A y, si el scope no está en el JWT, hace OBO que falla en KC 24. | Actualizar a Keycloak 26+. Mientras tanto, pedir el scope completo ya en A (sigue siendo seguro). |
| L2 | **No hay refresh tokens persistentes** | Cada llamada necesita fresh exchange. | Implementado en `oauth_client.refresh_user_token()`; integrar con client-mock para guardar el nuevo refresh_token tras cada rotación. |
| L3 | **Tokens no se revocan al logout** | El JWT vive 5 minutos. | Añadir `/logout` con refresh_token y `end_session_endpoint` por cliente. |
| L4 | **No hay rate limiting en el agente** | Posible abuso por IP. | Middleware FastAPI con token-bucket por `user_id`+IP. |
| L5 | **Spring Security 6.x devuelve 401 en lugar de 403** | Semánticamente debería ser 403. | Configurar `AccessDeniedHandler` explícito. |
| L6 | **`calendar.write` y `email.modify` no tienen endpoint en Spring** | Devuelve 400 si se piden. | Añadir `CalendarWriteController` y `EmailModifyController`. |
| L7 | **Device Code polling bloquea el endpoint** | `device_poll_for_tokens` es síncrono. | Implementar webhook en client-mock o usar long-polling no bloqueante. |
| L8 | **Passwords en texto claro en Keycloak** | Aceptable en PoC. | En producción: LDAP/AD/WebAuthn. |

### 7.2 Mejoras futuras

1. **Refresh token storage** persistente (SQLite o Redis) en client-mock.
2. **Device Code UI responsive** con auto-redirect al callback.
3. **HTTPS intra-cluster** (sidecars/proxies).
4. **Logging estructurado** con `user_id`, `scope`, `flow_used`.
5. **OpenTelemetry** entre componentes.
6. **CI con GitHub Actions** que levante `docker compose up` y corra los 3 tests E2E.

### 7.3 Cómo migrar de KC a B2C

```yaml
# docker-compose.yml override para B2C
services:
  agent-python:
    environment:
      IDP_ISSUER: https://<tenant>.ciamlogin.com/<tenant_id>.onmicrosoft.com
      AGENT_CLIENT_ID: <app-registration-id-de-B2C>
      AGENT_CLIENT_SECRET: <secret-de-B2C>
```

**Sin tocar una línea de código Python**: la detección automática de IdP en `config.py:25-40` selecciona los paths correctos.

### 7.4 Extensión opcional: añadir CIBA como "flujo D"

Si en el futuro se quiere CIBA (Kafka-style: agente lanza petición, humano recibe push y decide), se puede añadir:

```python
# agent-python/ciba_plugin.py (opcional)
class CIBAPlugin:
    """Sustituye A+B+C por CIBA cuando el IdP lo soporte."""
    ...
```

El flujo principal **A+B+C cubre el 95% de casos reales**. CIBA se justifica solo si se necesita UX asíncrono real-time en una app móvil.

---

## 8. Glosario

| Término | Significado |
|---|---|
| **PKCE** | Proof Key for Code Exchange (RFC 7636). Añade `code_verifier` + `code_challenge` para proteger el authorization code. Soportado por KC 24, B2C External ID, Auth0. |
| **Device Code Flow** | RFC 8628. El cliente pide un código + URL, el humano los introduce en su dispositivo y aprueba. Ideal para agentes headless. |
| **JWT Bearer / RFC 7523** | Grant OAuth estándar para que un servicio intercambie un JWT de usuario por un nuevo token con scope más limitado (On-Behalf-Of). Soportado en B2C External ID nativo. KC 24 NO; KC 26+ sí. |
| **Authorization Code** | RFC 6749 §4.1. Flujo estándar donde el IdP redirige al usuario con un code que el backend intercambia por tokens. PKCE lo protege. |
| **OIDC** | OpenID Connect. Capa de identidad sobre OAuth 2.0. |
| **OAuth 2.0** | RFC 6749. Framework de autorización. |
| **CIBA** | OpenID Connect CIBA 1.0. Flujo asíncrono con backchannel. NO soportado en B2C External ID. |
| **ROPC** | Resource Owner Password Credentials (RFC 6749 §4.3). Antipatrón de producción. Eliminado en v2. |
| **PoC** | Proof of Concept. |
| **IdP** | Identity Provider. KC, Azure B2C, Auth0, Okta, etc. |
| **JWT** | JSON Web Token (RFC 7519). |
| **JWK / JWKS** | JSON Web Key / JSON Web Key Set. Spring Boot las descubre vía `issuer-uri`. |
| **Bearer token** | Token que quien lo presenta tiene derecho a usarlo. Va en `Authorization: Bearer *** |
| **Scope** | Cadena identificando un permiso. El usuario consiente scopes y el JWT los lleva en `scope`. |
| **Audience (`aud`)** | Claim del JWT para qué API es válido. |
| **Authorized Party (`azp`)** | Claim del JWT indicando qué cliente OAuth pidió el token. |
| **`sub`** | Claim del JWT — identificador único del usuario. |
| **Resource Server** | API que recibe y valida access_tokens. |
| **Authorization Server** | Servidor que emite tokens tras autenticar al usuario. |
| **Token Exchange** | RFC 8693. Grant para intercambiar un token por otro. |
| **HS256** | Algoritmo de firma JWT con HMAC-SHA256 + clave compartida. |

---

**Mantenedor**: Víctor (khum1982) + Hermes Agent.
**Stack PIN**: `keycloak:24.0.5` (compose: `24.0`), `spring-boot:3.2.5`, `java:17`, `python:3.11`, `node:18`, `postgres:16`.
**Para B2C**: `azure-entra-external-id` (ciamlogin.com).
**Licencia**: MIT (PoC; adaptar antes de producción).
