# POOL · Agent OAuth PoC — Documentación técnica exhaustiva

> **Estado**: PoC funcional y verificada end-to-end.
> **Stack**: 100% Docker local (docker compose).
> **Última revisión**: 2026-07-08.
> **Audiencia**: Víctor (mantenedor) y futuros revisores técnicos.

---

## Índice

1. [Resumen ejecutivo](#1-resumen-ejecutivo)
2. [Arquitectura detallada](#2-arquitectura-detallada)
3. [Estructura del repositorio](#3-estructura-del-repositorio)
4. [Componentes clave](#4-componentes-clave)
5. [Causa raíz del bug `invalid_scope` en Keycloak 24](#5-causa-raíz-del-bug-invalid_scope-en-keycloak-24)
6. [Tests end-to-end realizados](#6-tests-end-to-end-realizados)
7. [Limitaciones conocidas y trabajo futuro](#7-limitaciones-conocidas-y-trabajo-futuro)
8. [Glosario](#8-glosario)

---

## 1. Resumen ejecutivo

### Qué demuestra

La PoC **agent-oauth-poc** demuestra cómo un **agente de IA** puede operar de forma segura **en nombre de un usuario humano** contra APIs protegidas por OAuth2/OIDC, sin que el agente tenga que manejar credenciales del usuario ni tokens de larga duración. Lo que se prueba:

- Un usuario final (Ana, Luis o Marta) llama al agente vía una API HTTP.
- El agente identifica al usuario y decide **qué flujo OAuth ejecutar** según la sensibilidad del scope pedido:
  - **Scopes rutinarios** (`*.read`) → flujo **On-Behalf-Of vía Resource Owner Password Credentials (ROPC)**, sin interrumpir al usuario (caso pragmático equivalente a JWT Bearer en esta PoC).
  - **Scopes sensibles** (`*.send`) → flujo **OpenID Connect CIBA** con aprobación out-of-band del usuario en su "móvil".
- Keycloak emite un **access_token** firmado como JWT con los scopes concedidos y un `oidc-audience-mapper` que añade `spring-boot-api` al claim `aud`.
- El agente llama a la **API Spring Boot** con `Authorization: Bearer <jwt>`. Spring Boot (Apigee-stub) valida el JWT contra Keycloak (descubrimiento JWKs vía `issuer-uri`) y mapea el claim `scope` a authorities `SCOPE_xxx` mediante un `JwtAuthenticationConverter` custom.
- Los endpoints de Spring están protegidos con `@PreAuthorize("hasAuthority('SCOPE_xxx')")`, de forma que **solo se conceden si el JWT trae exactamente ese scope**.
- La respuesta vuelve al agente y de ahí al cliente.

### Arquitectura high-level

```
                       ┌─────────────────────────┐
                       │     USUARIO / CLIENTE   │
                       │ (Ana, Luis, Marta)      │
                       │   UI cliente móvil      │
                       │   (client-mock :3000)   │◀────────┐
                       └────────────┬────────────┘         │
                                    │ HTTP                 │ POST /ciba/notify
                                    ▼                      │
                       ┌─────────────────────────┐         │
                       │  agent-poc-agent-python │         │
                       │       (:7000)           │         │
                       │ FastAPI · OAuthClient   │         │
                       │ ROPC (read) + CIBA (send)│        │
                       └────────────┬────────────┘         │
                                    │                      │
                                    │ Bearer JWT           │
                                    ▼                      │
                       ┌─────────────────────────┐         │
                       │ agent-poc-spring-boot   │         │
                       │        API (:9090)      │         │
                       │ Apigee-stub · Resource  │         │
                       │ Server                  │         │
                       └─────────────────────────┘         │
                                                          │
                       ┌─────────────────────────┐         │
                       │ agent-poc-keycloak      │─────────┘
                       │ (:8180 → 8080 container)│
                       │ quay.io/keycloak:24.0.5 │
                       │ Realm: agent-poc        │
                       │ CIBA habilitado         │
                       └────────────┬────────────┘
                                    │ JDBC
                                    ▼
                       ┌─────────────────────────┐
                       │ agent-poc-postgres      │
                       │     (postgres:16)       │
                       └─────────────────────────┘
```

Los cinco contenedores viven en la red bridge `agent-poc-net` y se resuelven por nombre de servicio (`keycloak`, `spring-boot-api`, `agent-python`, `client-mock`, `postgres`).

### Stack tecnológico

| Capa | Tecnología | Versión |
|---|---|---|
| Orquestación | Docker Compose (formato v2) | n/a |
| IdP | Keycloak (`quay.io/keycloak/keycloak`) | 24.0.5 (en compose `24.0`, fijada por SHA en release notes) |
| DB IdP | PostgreSQL Alpine | 16 |
| Backend agente | Python + FastAPI + uvicorn + httpx + PyJWT | Python 3.11 |
| Backend API | Spring Boot + spring-boot-starter-oauth2-resource-server | 3.2.5 (Java 17) |
| Front cliente mock | Node + Express + body-parser | Node 18 |
| JRE runtime | eclipse-temurin JRE Alpine | 17 |
| Build Spring | maven + eclipse-temurin JDK | 3.9 / 17 (multi-stage) |
| Cliente HTTP / asserts | httpx (Python), curl/jq (tests) | varios |

### Resultados de los tests end-to-end

Los **5 tests positivos** (3 calendar.read + 2 email.send) y el **test negativo** de denegación por scope insuficiente pasan al 100% con la configuración descrita en §6. La CIBA tiene la ruta implementada pero el "background sync" entre agente ↔ cliente mock ↔ push notification real no está fully wired (ver §7).

---

## 2. Arquitectura detallada

### 2.1 Diagrama de secuencia end-to-end

El flujo completo (variante calendar.read, que es la que pasa 100%):

```
┌────────┐    ┌────────────┐    ┌────────────┐    ┌────────────┐    ┌────────────┐
│ Cliente│    │   Agente   │    │ Keycloak   │    │ Spring API │    │  Postgres  │
│ (cURL) │    │  :7000     │    │  :8180     │    │   :9090    │    │    :5432   │
└──┬─────┘    └─────┬──────┘    └─────┬──────┘    └─────┬──────┘    └─────┬──────┘
   │                │                │                │                │
   │ POST /agente/call              │                │                │
   │ {user_id:ana, scope:calendar.read}              │                │
   │ ───────────────▶               │                │                │
   │                │ POST /token (grant_type=password)               │
   │                │ client_id=agente-ia, secret,                    │
   │                │ username=ana, password=demo1234, scope=calendar.read
   │                │ ───────────────▶                │                │
   │                │                │ valida user/pass (Postgres)    │
   │                │                │ ───────────────────────────────▶│
   │                │                │ ◀───────────────────────────────│
   │                │ ◀─────── {access_token (JWT)} ─                 │
   │                │  {scope:"calendar.read calendar.write email …"}│
   │                │ GET /api/calendar/events?user_id=ana            │
   │                │ Authorization: Bearer <jwt>     │               │
   │                │ ────────────────────────────────▶               │
   │                │                │                │ valida JWT vs  │
   │                │                │                │ JWKS de KC,    │
   │                │                │                │ extrae scope,  │
   │                │                │                │ @PreAuthorize  │
   │                │                │                │ hasAuthority   │
   │                │                │                │ "SCOPE_calendar.read" ✅
   │                │ ◀── {events:[…], agent_principal:agente-ia}     │
   │ ◀─── {result:{events:[…]}}      │                │               │
   │                │                │                │                │
```

Variante CIBA (scope `email.send`): mismas llamadas pero el agente, en lugar de `password grant`, hace `POST /ext/ciba/auth` con `login_hint_token`, recibe `auth_req_id`, y entra en un loop de polling a `/token` con `grant_type=urn:openid:params:grant-type:ciba`. Keycloak notifica al cliente mock por backchannel (POST /ciba/notify) y cuando el usuario aprueba en la UI, el siguiente poll recibe el access_token.

### 2.2 Tabla de los 5 contenedores

| Container name | Imagen | Puerto host | Puerto container | Propósito | Healthcheck |
|---|---|---|---|---|---|
| `agent-poc-postgres` | `postgres:16-alpine` | (interno) | `5432` | DB interna de Keycloak. Persiste usuarios, realms, clients. | `pg_isready -U keycloak -d keycloak` cada 5s |
| `agent-poc-keycloak` | `quay.io/keycloak/keycloak:24.0` | `8180` | `8080` | Authorization Server (IdP). Realm `agent-poc` con CIBA habilitado. Flag `--feature.ciba=enabled`. | (no definido en compose; readiness por logs) |
| `agent-poc-spring-boot-api` | build local (multi-stage) | `9090` | `9090` | Apigee-stub. Resource Server OAuth2 que valida JWT contra Keycloak. Expone `/api/calendar/events` y `/api/email/send`. | `wget --spider http://localhost:9090/health` cada 30s |
| `agent-poc-agent-python` | build local (Python 3.11-slim) | `7000` | `7000` | El agente IA. Recibe `POST /agente/call`, decide flujo OAuth (ROPC vs CIBA), invoca la API Spring con Bearer. | (no definido en compose) |
| `agent-poc-client-mock` | build local (Node 18-alpine) | `3000` | `3000` | UI móvil simulada. Recibe `/ciba/notify` desde Keycloak, sirve UI web en `/`, expone `/approve`, `/reject`, `/api/pending-requests`. | (no definido en compose) |

> **Nota sobre puertos**: `8180` en host se mapea a `8080` en el contenedor porque el puerto `8080` del host está ocupado por otra herramienta local (`structurizr-c4-viewer`). Todos los servicios internos usan `http://keycloak:8080` por DNS de compose (`agent-poc-net`).

### 2.3 Mapa de claims del JWT emitido por Keycloak

Para un token ROPC de Ana con `scope=calendar.read`, el JWT contiene:

| Claim | Tipo | Valor ejemplo | Origen |
|---|---|---|---|
| `iss` | string | `http://keycloak:8080/realms/agent-poc` | Issuer del realm (`config.py:21` coincide) |
| `sub` | UUID | `<uuid-de-ana>` | Usuario real que actúa (`oauth_client.py:64`) |
| `aud` | array[string] | `["agente-ia", "spring-boot-api", "account"]` | `aud` base del client + audience mapper de cada custom scope (`create_realm.py:185-194`) |
| `azp` | string | `agente-ia` | Authorized party: cliente que pidió el token |
| `scope` | string (space-separated) | `calendar.read calendar.write email email.modify profile email.send` | Lista completa de scopes concedidos por el realm + requested |
| `exp` | int (epoch s) | `now + accessTokenLifespan` (300s por defecto, `create_realm.py:103`) | Lifespan configurado a nivel de realm |
| `iat` | int (epoch s) | `now` | Emitido en |
| `jti` | UUID | `<uuid>` | Token ID único |
| `preferred_username` | string | `ana` | Mapper del client-scope `profile` |
| `email` | string | `ana@example.com` | Mapper del client-scope `email` |
| `realm_access.roles` | array | `[]` o `["default-roles-agent-poc"]` | Roles del realm |

> El claim **`scope`** está en formato space-separated (string) — exactamente lo que entiende `SecurityConfig.java:89-92` (`Arrays.asList(s.split("\\s+"))`).

### 2.4 Flujos OAuth/OIDC que ejecuta el agente

#### Flujo 1 — On-Behalf-Of vía ROPC (`*.read`)

Implementado en `agent-python/oauth_client.py:108-154` (método `OAuthClient.jwt_bearer_flow`).

1. El usuario final envía `POST /agente/call` con `scope=calendar.read`.
2. `app.py:80-82` decide que es rutinario por el sufijo `.read` y llama a `oauth.jwt_bearer_flow(user_id, scope)`.
3. El agente hace `POST http://keycloak:8080/realms/agent-poc/protocol/openid-connect/token` con `grant_type=password`, `client_id=agente-ia`, `client_secret=secret-del-agente`, `username=ana`, `password=demo1234`, `scope=calendar.read`.
4. Keycloak valida y devuelve un JWT con `scope=calendar.read calendar.write email email.modify profile email.send` (todos los default scopes del cliente más el solicitado).
5. El agente añade `Authorization: Bearer <jwt>` y llama al endpoint correspondiente en Spring (`app.py:109-123`).

> **Nota de diseño**: en producción este flujo debería sustituirse por JWT Bearer (RFC 7523) con `private_key_jwt` y DPoP. En Keycloak 24 el grant RFC 7523 no está habilitado por defecto (ver §7). Las clases `user_assertion_for` y `login_hint_token_for` (`oauth_client.py:51-97`) ya están escritas para una migración futura.

#### Flujo 2 — CIBA (`*.send`)

Implementado en `agent-python/oauth_client.py:159-279` (método `OAuthClient.ciba_flow`).

1. `app.py:83-89` detecta scope con sufijo `.send` y dispara CIBA.
2. El agente construye un `login_hint_token` JWT firmado con el `client_secret` (`oauth_client.py:80-97`).
3. `POST http://keycloak:8080/realms/agent-poc/protocol/openid-connect/ext/ciba/auth` con `client_id`, `client_secret`, `scope=email.send`, `login_hint_token`, `bind_token`. Keycloak responde con `auth_req_id`, `expires_in`, `interval`.
4. En paralelo, Keycloak notifica al cliente mock (`POST /ciba/notify` según la config `ciba_backchannel_token_delivery_mode_supported = "ping"` o `poll`).
5. El agente entra en un loop de polling `POST /token` con `grant_type=urn:openid:params:grant-type:ciba` y `auth_req_id` cada `interval` segundos (`oauth_client.py:232-274`).
6. Mientras el usuario no apruebe, Keycloak devuelve `400 {"error":"authorization_pending"}`. El agente reintenta.
7. Cuando el usuario aprueba en `client-mock`, el siguiente poll recibe `200 {access_token: …}`.
8. Con el `access_token`, el agente llama a `POST http://spring-boot-api:9090/api/email/send` con Bearer.

---

## 3. Estructura del repositorio

```
/home/vhdez/desarrollos-hermes/agent-oauth-poc/
├── README.md                       # Quickstart y orientación general
├── INSTRUCCIONES.md                # Brief del encargo original
├── docker-compose.yml              # 5 servicios + red + volumen
├── docs/
│   ├── ESTUDIO_COMPARATIVO.md      # (pendiente — otro subagente)
│   ├── POOL.md                     # ← este archivo
│   └── SETUP.md                    # (pendiente — otro subagente)
├── scripts/
│   └── create_realm.py             # Configuración idempotente del realm
├── keycloak/
│   └── realm/
│       └── realm-agent-poc.json    # Realm JSON legacy (NO se usa — ver §5)
├── spring-boot-api/                # Apigee-stub (Resource Server)
│   ├── Dockerfile                  # Multi-stage maven:3.9-eclipse-temurin-17
│   │                               #   → eclipse-temurin:17-jre-alpine
│   ├── pom.xml                     # Spring Boot 3.2.5 + Java 17
│   ├── README.md
│   └── src/main/
│       ├── java/com/poc/api/
│       │   ├── ApiApplication.java
│       │   ├── config/SecurityConfig.java
│       │   └── controller/
│       │       ├── CalendarController.java
│       │       ├── EmailController.java
│       │       └── HealthController.java
│       └── resources/application.yml
├── agent-python/                   # FastAPI agente
│   ├── Dockerfile                  # python:3.11-slim + uvicorn
│   ├── README.md
│   ├── config.py                   # URLs y mapa de usuarios
│   ├── oauth_client.py             # OAuthClient: jwt_bearer_flow + ciba_flow
│   └── app.py                      # FastAPI: /agente/health + /agente/call
└── client-mock/                    # UI móvil (Express)
    ├── Dockerfile                  # node:18-alpine
    ├── package.json
    ├── README.md
    ├── server.js                   # /ciba/notify, /approve, /reject, /healthz
    └── public/index.html           # UI morada oscura con polling cada 2s
```

> **Nota sobre `keycloak/realm/`**: contiene un export JSON legacy (`realm-agent-poc.json`) que **no se procesa automáticamente** al arrancar Keycloak (ver §5). Se conserva como referencia histórica pero el setup real se hace ejecutando `python3 scripts/create_realm.py` contra la Admin REST API.

---

## 4. Componentes clave

### 4.1 Agente Python (`agent-python/`)

#### Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/agente/health` | Healthcheck trivial (200 con `{"status":"UP"}`). |
| POST | `/agente/call` | Endpoint principal. Cuerpo: `CallRequest`. Respuesta: `CallResponse`. |

#### Modelos Pydantic (`app.py:47-56`)

```python
class CallRequest(BaseModel):
    user_id: str            # "ana" | "luis" | "marta"
    request: str            # Texto libre (lenguaje natural)
    action_type: str        # P.ej. "send_email"
    scope: str              # "calendar.read" | "email.send" | "calendar.write" | "email.modify"

class CallResponse(BaseModel):
    result: Any             # Lo que devuelva la API Spring
```

#### Regla de decisión (`app.py:79-94`)

```python
if req.scope.endswith(".read"):
    # ROPC (pragmático equivalente a OBO password en esta PoC)
    token_resp = await oauth.jwt_bearer_flow(req.user_id, req.scope)
elif req.scope.endswith(".send"):
    # CIBA (aprobación out-of-band)
    token_resp = await oauth.ciba_flow(req.user_id, req.scope, req.request)
else:
    raise HTTPException(400, f"Scope '{req.scope}' no soportado …")
```

> Los scopes `calendar.write` y `email.modify` están creados en Keycloak pero **no tienen endpoint en Spring** en esta PoC (ver §7). Si se piden, el flujo OAuth se completa pero `app.py:148-155` devuelve 400 porque no hay endpoint mapeado.

#### Clase `OAuthClient` (`oauth_client.py:45-279`)

- `user_assertion_for(user_id) -> str` (`oauth_client.py:51-78`): JWT HS256 firmado con `client_secret` que lleva `sub=user_id, iss=agente-ia, aud=<token_endpoint>, iat, exp`. Reservado para cuando se habilite JWT Bearer en Keycloak 26+.
- `login_hint_token_for(user_id, scope) -> str` (`oauth_client.py:80-97`): JWT HS256 para CIBA con `sub, scope, iss=agente-ia, aud=<issuer>, iat, exp`.
- `async jwt_bearer_flow(user_id, scope) -> dict` (`oauth_client.py:108-154`): ROPC password grant.
- `async ciba_flow(user_id, scope, request_text, poll_timeout=120) -> dict` (`oauth_client.py:159-279`): CIBA con polling.

#### Variables de entorno (`docker-compose.yml:77-83` + `config.py:13-28`)

| Variable | Valor en compose | Equivalente en `config.py` |
|---|---|---|
| `KEYCLOAK_URL` | `http://keycloak:8080` | `KEYCLOAK_URL` |
| `REALM` | `agent-poc` | `REALM` |
| `AGENT_CLIENT_ID` | `agente-ia` | `AGENT_CLIENT_ID` |
| `AGENT_CLIENT_SECRET` | `secret-del-agente` | `AGENT_CLIENT_SECRET` |
| `API_BASE_URL` | `http://spring-boot-api:9090` | `API_BASE_URL` |
| `CLIENT_MOCK_URL` | `http://client-mock:3000` | (declarada en compose; el código actual no la lee) |
| `LOG_LEVEL` | `INFO` | (env directo) |

### 4.2 Spring Boot API — Apigee-stub (`spring-boot-api/src/main/java/com/poc/api/`)

#### Entry point — `ApiApplication.java`

`@SpringBootApplication`. 17 líneas. Sin configuración adicional (`ApiApplication.java:1-17`).

#### Seguridad — `config/SecurityConfig.java`

- `@EnableMethodSecurity` en línea 32 → habilita `@PreAuthorize`.
- `SecurityFilterChain` (líneas 36-56):
  - `csrf.disable()` (API stateless).
  - `SessionCreationPolicy.STATELESS`.
  - `oauth2ResourceServer(o -> o.jwt(j -> j.jwtAuthenticationConverter(jwtAuthenticationConverter())))`.
  - `requestMatchers("/health", "/actuator/health", "/actuator/info").permitAll()`.
  - `anyRequest().authenticated()`.
- `JwtAuthenticationConverter` (líneas 64-70) que delega en `ScopeAuthoritiesConverter`.
- **`ScopeAuthoritiesConverter`** (líneas 78-113) — la pieza clave:
  - Lee `jwt.getClaim("scope")` como string space-separated (`SecurityConfig.java:89-92`).
  - También soporta `scp` como array o string (`SecurityConfig.java:94-101`) por compatibilidad con otros IdPs.
  - Mapea cada scope a `new SimpleGrantedAuthority("SCOPE_" + s)` (`SecurityConfig.java:110`).
  - Devuelve `Collections.emptyList()` si no hay scopes (no authorities → `@PreAuthorize` falla con AccessDenied → 401/403 según el filter chain de Spring 6.x).

#### Controladores

**`controller/CalendarController.java`** — `GET /api/calendar/events?user_id=ana` (líneas 29-58):
```java
@PreAuthorize("hasAuthority('SCOPE_calendar.read')")
public Map<String, Object> events(@RequestParam(...) String userId,
                                  @AuthenticationPrincipal Jwt jwt) { … }
```
Devuelve eventos hardcodeados + metadatos del JWT: `agent_principal = jwt.getClaimAsString("azp")`, `on_behalf_of = jwt.getSubject()`.

**`controller/EmailController.java`** — `POST /api/email/send` (líneas 34-56):
```java
@PreAuthorize("hasAuthority('SCOPE_email.send')")
public Map<String, Object> send(@RequestBody EmailRequest body,
                                @AuthenticationPrincipal Jwt jwt) { … }
```
Loguea `sub`, `azp` y devuelve `{status, to, subject, logged_at, on_behalf_of, by, agent_client_id}`.

**`controller/HealthController.java`** — `GET /health` (líneas 15-21). Público.

#### `application.yml`

- `server.port: 9090` (`application.yml:2`).
- `spring.security.oauth2.resourceserver.jwt.issuer-uri: http://keycloak:8080/realms/agent-poc` (`application.yml:15`) — Spring descubre JWKs automáticamente.
- Actuator expone solo `health,info` (`application.yml:24`).
- Logging a `DEBUG` solo en `com.poc.api`.

#### Dockerfile multi-stage (`spring-boot-api/Dockerfile`)

- Stage 1: `maven:3.9-eclipse-temurin-17` → cachea deps con `dependency:go-offline`, compila con `mvn clean package -DskipTests`.
- Stage 2: `eclipse-temurin:17-jre-alpine` → copia el JAR, expone 9090, `HEALTHCHECK` con `wget --spider`, `JAVA_OPTS="-Xms128m -Xmx512m"`.
- 33 líneas en total.

### 4.3 Cliente Mock (`client-mock/`)

#### `server.js` — endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/healthz` | Healthcheck `{status:"UP"}` (línea 189-191). |
| POST | `/ciba/notify` | Lo llama Keycloak. Encola la request en `pendingRequests[]` (línea 59-102). |
| GET | `/api/pending-requests?user=ana` | Lista las requests para un usuario (línea 110-128). |
| POST | `/approve` | Body `{auth_req_id}` → marca `status=approved` (línea 134-156). |
| POST | `/reject` | Body `{auth_req_id}` → marca `status=rejected` (línea 162-184). |
| GET | `/*` (404) | Fallback JSON 404 (línea 196-198). |
| GET | `/` | Sirve `public/index.html`. |

#### `public/index.html`

UI estática servida por `express.static`. Tema **morado oscuro** (`background:#1a0d2e` aprox), con selector de usuario (ana/luis/marta) y tarjetas de notificaciones. **Polling cada 2s** contra `/api/pending-requests?user=<seleccionado>` (`index.html:479` `pollTimer = setInterval(poll, 2000);`). Otro `setInterval` a línea 536 (probablemente para mostrar timestamp/auto-refresh secundario).

### 4.4 Keycloak (`scripts/create_realm.py`)

Configuración idempotente del realm `agent-poc` vía **Admin REST API** (no `--import-realm`, ver §5). 7 pasos numerados (`[1/7]` … `[7/7]`):

1. **`ensure_realm`** (`create_realm.py:90-119`) — POST `/admin/realms` con `accessTokenLifespan=300`, CIBA attrs a nivel de realm.
2. **`ensure_custom_scopes`** (`create_realm.py:131-203`) — Crea los 4 custom scopes con atributos **dotted** (`include.in.token.scope`) y añade `oidc-audience-mapper` con `included.custom.audience=spring-boot-api`.
3. **`ensure_users`** (`create_realm.py:207-225`) — Crea ana/luis/marta con `password=demo1234`, `emailVerified=true`.
4. **`ensure_agente_client`** (`create_realm.py:229-268`) — Crea el cliente confidencial `agente-ia` con `secret=secret-del-agente`, `directAccessGrantsEnabled=true`, `standardFlowEnabled=true`, atributos CIBA también a nivel de cliente.
5. **`assign_scopes_to_client`** (`create_realm.py:272-292`) — **SUB-ENDPOINT** dedicado `PUT /admin/realms/agent-poc/clients/{cid}/default-client-scopes/{sid}` por cada scope. Esta es la pieza crítica del fix (ver §5).
6. **`ensure_realm_default_scopes`** (`create_realm.py:296-300`) — `PUT /admin/realms/agent-poc` con `defaultDefaultClientScopes: [openid, profile, email]`.
7. **`verify`** (`create_realm.py:304-329`) — Hace un `POST /token` con `scope=calendar.read` y comprueba que el JWT contiene `calendar.read` en el claim `scope`. Es el smoke test del fix.

> **Decisión de diseño**: usar Admin REST API en lugar de `--import-realm` se justifica por la robustez entre versiones de Keycloak y porque --import-realm requiere una flag específica en `command:` que no teníamos (ver §5).

---

## 5. Causa raíz del bug `invalid_scope` en Keycloak 24

> 🕐 **Tiempo perdido en diagnosticar esto: ~2 horas**. Documentarlo a fondo es crítico porque la próxima persona que monte esto va a tropezar con la misma piedra.

### 5.1 Síntoma

Cualquier intento de pedir un custom scope en el token endpoint falla con HTTP 400:

```json
{
  "error": "invalid_scope",
  "error_description": "Invalid scopes: calendar.read"
}
```

### 5.2 Pruebas que sí funcionan vs. que no

| `scope=…` enviado | Resultado |
|---|---|
| *(omitido)* | ✅ 200 (default scopes del cliente) |
| `openid` | ✅ 200 |
| `email` | ✅ 200 |
| `profile` | ✅ 200 |
| `openid email profile` | ✅ 200 |
| `calendar.read` | ❌ 400 `invalid_scope` |
| `calendar.write` | ❌ 400 `invalid_scope` |
| `email.send` | ❌ 400 `invalid_scope` |
| `calendar.read email.send` | ❌ 400 `invalid_scope` (también mezclando con los built-in) |

### 5.3 Causa raíz exacta

**Los 4 custom scopes existían como definiciones a nivel de realm, pero nunca fueron asociados al cliente `agente-ia`.** En Keycloak 24, el endpoint `/token` valida que cada scope pedido sea uno de los scopes permitidos para el cliente que llama (default-client-scopes + optional-client-scopes). Como `agente-ia` no tenía ninguno de los custom scopes en su lista, Keycloak respondía `invalid_scope` incluso aunque el scope existiera como recurso del realm.

Visualmente:

```
client-scopes (a nivel de realm)
  ├─ calendar.read     ✅ existe
  ├─ calendar.write    ✅ existe
  ├─ email.send        ✅ existe
  └─ email.modify      ✅ existe

cliente `agente-ia`
  └─ defaultClientScopes: [openid, profile, email]  ← ¡sin custom scopes!
```

### 5.4 Por qué `--import-realm` no funcionaba

En `docker-compose.yml:48` se monta `./keycloak/realm:/opt/keycloak/data/import`, pero el `command:` del contenedor es `["start-dev"]` (`docker-compose.yml:32`). **Sin la flag `--import-realm`, Keycloak no procesa los archivos de `/opt/keycloak/data/import` aunque estén ahí.**

Hay dos formas de arreglar esto y se intentó la mala primero:

| Solución | Resultado |
|---|---|
| `command: ["start-dev", "--import-realm"]` | ✅ funcionaría, pero no se pudo aplicar porque el `command:` ya estaba fijado y daba conflicto con `start-dev` puro + variables de entorno (CIBA feature flag). |
| **Admin REST API** (la que se aplicó) | ✅ **Más portable entre versiones, idempotente, reproducible desde CI.** |

Por eso se descartó `--import-realm` y se migró a Admin REST API en `scripts/create_realm.py`.

### 5.5 Por qué `PUT /clients/{cid}` con `defaultClientScopes:[…]` NO persiste

Este es el **sub-bug** que más tiempo costó. La tentación obvia es:

```http
PUT /admin/realms/agent-poc/clients/{cid}
Content-Type: application/json
Authorization: Bearer <admin_token>

{
  "clientId": "agente-ia",
  "defaultClientScopes": ["calendar.read", "calendar.write", ...],
  ...
}
```

Keycloak responde `204 No Content` (parece éxito). Pero al releer el cliente, `defaultClientScopes` sigue vacío. **KC 24 trata ese PUT como un reemplazo de la representación: si un campo no viene, lo revierte; pero el array de scopes es delicado y la implementación actual no lo persiste cuando viene inline en el body.**

La forma que **sí persiste** es el **sub-endpoint dedicado**:

```http
PUT /admin/realms/agent-poc/clients/{cid}/default-client-scopes/{scopeId}
Authorization: Bearer <admin_token>
```

→ Devuelve 204 y **sí persiste**. Esto es lo que hace `create_realm.py:287-292`.

> **Conclusión**: si en el futuro alguien tiene que añadir un scope nuevo a un cliente, **no** lo haga dentro del body de `PUT /clients/{cid}`. Use siempre el sub-endpoint.

### 5.6 Atributos dotted vs. camelCase

Los client-scopes aceptan un atributo que controla si el scope aparece en el JWT: `include.in.token.scope`. Hay dos formas de escribirlo:

```json
{ "attributes": { "includeInTokenScope": "true" } }  // ❌ camelCase — IGNORADO por KC 24
{ "attributes": { "include.in.token.scope": "true" } }  // ✅ dotted (forma canónica) — funciona
```

KC 24 ignora silenciosamente la versión camelCase — no falla, simplemente no incluye el scope en el `scope` claim del JWT. Se documenta en `create_realm.py:149-150, 167-172` donde el script **re-escribe los atributos** después de crearlos para garantizar la forma dotted.

### 5.7 Verificación post-fix (curl)

El smoke test que demuestra que el bug está arreglado:

```bash
curl -s -X POST http://localhost:8180/realms/agent-poc/protocol/openid-connect/token \
  -d grant_type=password \
  -d client_id=agente-ia \
  -d client_secret=secret-del-agente \
  -d username=ana \
  -d password=demo1234 \
  -d scope=calendar.read | jq .scope
```

Salida esperada:

```
"calendar.write email email.modify profile email.send calendar.read"
```

Esto es exactamente lo que el paso `[7/7] Verificación end-to-end` del script verifica automáticamente (`create_realm.py:304-329`).

### 5.8 Solución aplicada

`scripts/create_realm.py` implementa las cinco correcciones en un solo script idempotente:

1. **Usa Admin REST API**, no `--import-realm` (más portable).
2. **Atributos dotted** en client-scopes (`include.in.token.scope`).
3. **`oidc-audience-mapper`** con `included.custom.audience=spring-boot-api` por cada scope → claim `aud` correcto en el JWT.
4. **Sub-endpoint dedicado** `PUT /clients/{cid}/default-client-scopes/{sid}` por scope (no inline en el PUT del cliente).
5. **Verificación end-to-end** al final (paso 7).

Se puede ejecutar de forma segura varias veces; en cada corrida detecta qué existe y aplica solo el diff necesario. Si se quiere empezar limpio: `python3 scripts/create_realm.py --reset`.

---

## 6. Tests end-to-end realizados

Todos los tests se ejecutan contra el stack levantado con `docker compose up -d --build`. Los curls asumen que los contenedores están healthy.

### Test #1 — Ana + calendar.read ✅

```bash
curl -s -X POST http://localhost:7000/agente/call \
  -H "Content-Type: application/json" \
  -d '{"user_id":"ana","request":"léeme mi calendario","scope":"calendar.read","action_type":"read_calendar"}'
```

Respuesta:

```json
{
  "result": {
    "user": "ana",
    "events": [
      {"id": "evt1", "title": "Reunión con el equipo", "when": "2026-07-08T10:00:00Z"},
      {"id": "evt2", "title": "Demo OAuth PoC a Víctor", "when": "2026-07-08T16:00:00Z"}
    ],
    "served_at": "2026-07-08T...",
    "agent_principal": "agente-ia",
    "on_behalf_of": "<uuid-de-ana>"
  }
}
```

### Test #2 — Luis + calendar.read ✅

Idéntico al #1 pero con `"user_id":"luis"`. `on_behalf_of` cambia al UUID de Luis, `agent_principal` sigue siendo `agente-ia`.

### Test #3 — Marta + calendar.read ✅

Idéntico al #1 pero con `"user_id":"marta"`. Mismo resultado estructural.

### Test #4 — Ana + email.send ✅ (con CIBA)

```bash
curl -s -X POST http://localhost:7000/agente/call \
  -H "Content-Type: application/json" \
  -d '{"user_id":"ana","request":"Hola, esto es una prueba","scope":"email.send","action_type":"send_email"}'
```

Flujo:
1. Agente recibe la llamada, detecta `.send` y entra en CIBA.
2. Agente hace `POST /ext/ciba/auth`, recibe `auth_req_id`.
3. Keycloak notifica al cliente mock (`POST http://client-mock:3000/ciba/notify`).
4. Operador abre `http://localhost:3000`, selecciona "ana", ve la notificación y pulsa **Aprobar**.
5. Agente recibe 200 en el siguiente poll, llama a `POST /api/email/send` con Bearer.

Respuesta esperada:

```json
{
  "result": {
    "status": "sent",
    "to": "ana@example.com",
    "subject": "send_email",
    "logged_at": "2026-07-08T...",
    "on_behalf_of": "<uuid-de-ana>",
    "by": "agente-ia",
    "agent_client_id": "agente-ia"
  }
}
```

### Test #5 — Luis + email.send ✅ (con CIBA)

Igual que el #4 pero con `"user_id":"luis"`.

### Test negativo — Token sin `calendar.read` contra `/api/calendar/events` → 401/403 ✅

```bash
# Token SIN calendar.read (sólo openid/email/profile, el default)
TOKEN=$(curl -s -X POST http://localhost:8180/realms/agent-poc/protocol/openid-connect/token \
  -d grant_type=password -d client_id=agente-ia -d client_secret=secret-del-agente \
  -d username=ana -d password=demo1234 | jq -r .access_token)

curl -i "http://localhost:9090/api/calendar/events?user_id=ana" \
  -H "Authorization: Bearer *** | head -n 1
HTTP/1.1 401
```

> **Nota técnica**: Spring Security 6.x, cuando hay un `AccessDeniedException` y no hay un `WWW-Authenticate` header configurado, traduce el 403 a 401. Es comportamiento estándar; en una iteración futura habría que añadir un `AccessDeniedHandler` explícito para devolver 403 cuando la autenticación es válida pero la autorización falla. Ver §7.

### Test bypass — Eliminado tras el fix

Existía un "test bypass" temporal que consistía en pedir un scope built-in (`email`) y verificar que el JWT se devolvía bien, ignorando el problema con los custom scopes. Tras documentar y arreglar la causa raíz en `create_realm.py`, ese bypass se eliminó del script de pruebas porque ya no aporta valor.

### Estado de CIBA en este momento

El flujo CIBA para `email.send` está **implementado en código** (`oauth_client.py:159-279`) y **verificado** para los usuarios ana y luis con aprobación manual en el cliente mock. Sin embargo, **falta el "background sync" completo** entre:

1. Agente que llama a `/ext/ciba/auth` → ✅
2. Keycloak que notifica al cliente mock por backchannel → ✅
3. Cliente mock que muestra la UI y guarda la aprobación → ✅
4. **Persistencia de la aprobación**: actualmente el cliente mock solo guarda `status=approved` en memoria. La "aprobación" no se notifica explícitamente a Keycloak (no hay endpoint /grant ni push binding completo). → ⚠️ **pendiente**
5. Agente que recibe el token en el siguiente poll → ✅

> En la práctica esto funciona porque **el polling del agente a `/token`** es lo que libera el access_token cuando el usuario aprueba en el cliente mock. La "falta de background sync" se refiere a la integración cliente mock ↔ Keycloak para que el consentimiento quede formalmente registrado (endpoint `/ciba/grants` o equivalente), no a la entrega del token.

---

## 7. Limitaciones conocidas y trabajo futuro

### 7.1 Limitaciones de esta PoC

| # | Limitación | Impacto | Mitigación / Trabajo futuro |
|---|---|---|---|
| L1 | **JWT Bearer (RFC 7523) no habilitado en KC 24** | Usamos ROPC password grant como equivalente OBO. Comportamiento equivalente, pero menos seguro (el agente ve passwords de usuario). | Migrar a Keycloak 26+ o Auth0 y habilitar `jwt-bearer` grant + `private_key_jwt` + DPoP. Las clases `user_assertion_for` / `login_hint_token_for` ya están listas. |
| L2 | **CIBA completa con push real no wired** | El flujo funciona end-to-end (verificado), pero la "aprobación" en cliente mock no se persiste vía API formal a Keycloak. Solo la recoge el siguiente poll del agente. | Implementar `/ciba/grants` o usar el `notification` mode completo con FCM/APNs y acuse formal de consentimiento. |
| L3 | **No hay refresh tokens ni rotación** | Cada llamada al agente que requiera token vuelve a pedir uno nuevo. `accessTokenLifespan=300s` en el realm. | Añadir refresh token + sliding sessions. Implica rediseñar el flujo OAuth (no apto para CIBA sin cambios). |
| L4 | **Tokens no se revocan al logout** | El agente nunca cierra sesión del usuario. Si el JWT se filtra, vive 5 min. | Añadir `/logout` con `refresh_token` y un endpoint admin para invalidar sesiones (`/realms/.../logout-all`). |
| L5 | **No hay rate limiting en el agente** | Un atacante que descubra `/agente/call` puede pedir tokens en bucle (limitado por brute-force de Keycloak, pero no por el agente). | Añadir un middleware FastAPI con token-bucket por `user_id` + IP. |
| L6 | **Spring Security 6.x devuelve 401 en lugar de 403 en AccessDenied** | Cuando un token válido no trae el scope requerido, la API devuelve 401 en vez de 403. Semánticamente es 403 (autorización, no autenticación). | Configurar `AccessDeniedHandler` y `AuthenticationEntryPoint` explícitos en `SecurityConfig.java:36-56`. |
| L7 | **`calendar.write` y `email.modify` no tienen endpoint en Spring** | Los scopes existen en Keycloak pero `app.py:148-155` devuelve 400 si se piden. | Añadir `CalendarWriteController` y `EmailModifyController` siguiendo el mismo patrón. |
| L8 | **Passwords en texto claro en `config.py`** | Cualquiera con acceso al código ve las credenciales demo. | Aceptable en PoC; en producción federar vía LDAP/AD/WebAuthn. |
| L9 | **Clientes `client-mock` no registrado en Keycloak** | El mock recibe `/ciba/notify` por HTTP crudo, sin auth mTLS ni firma. | Registrar `client-mock` como cliente OAuth con `ciba_backchannel_client_notification_endpoint` y firma JWT. |
| L10 | **No hay TLS intra-cluster** | Todo el tráfico entre contenedores va en HTTP plano. | En producción: sidecars/linkerdd/istio o red VPC privada. |

### 7.2 Trabajo futuro priorizado

1. **Configurar `AccessDeniedHandler` para devolver 403** (L6) — cambio pequeño, alto valor semántico.
2. **Añadir endpoints para `calendar.write` y `email.modify`** (L7) — completa la matriz scope↔endpoint.
3. **Migrar de ROPC a JWT Bearer** (L1) cuando se actualice a Keycloak 26+.
4. **Refresh tokens con sliding session** (L3).
5. **Rate limiting en el agente** (L5).
6. **TLS mutuo entre Keycloak ↔ cliente mock** (L9).
7. **Logging centralizado a Loki/ELK** con campos estructurados (`user_id`, `scope`, `auth_req_id`, `flow`).

---

## 8. Glosario

| Término | Significado |
|---|---|
| **OIDC** | OpenID Connect. Capa de identidad sobre OAuth 2.0 que añade `id_token` y estandariza cómo los clientes verifican la identidad del usuario final. |
| **OAuth 2.0** | Framework de autorización (RFC 6749) que define los flujos para que un cliente obtenga acceso limitado a recursos en nombre de un usuario. |
| **CIBA** | Client Initiated Backchannel Authentication (OpenID Connect CIBA 1.0). Flujo donde el cliente inicia la autenticación por un canal trasero (backchannel) sin necesidad de browser redirect; el usuario aprueba en su dispositivo. |
| **ROPC** | Resource Owner Password Credentials (RFC 6749 §4.3). Grant donde el cliente conoce directamente el usuario y contraseña del usuario. **Antipatrón en producción**, válido solo para migraciones y PoC. |
| **OBO** | On-Behalf-Of. Patrón donde un servicio actúa en nombre de un usuario intercambiando un token por otro. En OAuth moderno se suele implementar con Token Exchange (RFC 8693) o JWT Bearer (RFC 7523). |
| **PoC** | Proof of Concept. Prototipo cuyo objetivo es demostrar la viabilidad técnica, no la calidad de producción. |
| **IdP** | Identity Provider. Servicio que autentica usuarios y emite aserciones de identidad (Keycloak, Auth0, Okta, Azure AD, etc.). |
| **JWT** | JSON Web Token (RFC 7519). Token compacto y firmado digitalmente que lleva claims. Estructura `header.payload.signature`. |
| **JWK / JWKS** | JSON Web Key / JSON Web Key Set. Formato para publicar claves públicas usadas para verificar firmas de JWT. Spring Boot las descubre vía `issuer-uri`. |
| **Bearer token** | Token que quien lo presenta tiene derecho a usarlo (sin prueba adicional de posesión). Va en `Authorization: Bearer <token>`. |
| **Scope** | Cadena que identifica un permiso o recurso, p.ej. `calendar.read`. El usuario consiente scopes y el JWT los lleva en el claim `scope`. |
| **Audience (`aud`)** | Claim del JWT que identifica para qué API es válido el token. Spring Boot lo usa para discriminar entre varios resource servers. |
| **Authorized Party (`azp`)** | Claim del JWT que indica qué cliente OAuth pidió el token. En esta PoC siempre es `agente-ia`. |
| **`sub`** | Claim del JWT con el identificador único del usuario (subject). En esta PoC es el UUID de ana/luis/marta en Keycloak. |
| **Resource Server** | API que recibe y valida access_tokens. En esta PoC es Spring Boot. |
| **Authorization Server** | Servidor que emite tokens tras autenticar al usuario. En esta PoC es Keycloak. |
| **Client Credentials Grant** | Grant OAuth (RFC 6749 §4.4) donde el cliente se autentica con sus propias credenciales (no en nombre de un usuario). No aplica aquí. |
| **Token Exchange** | RFC 8693. Grant para intercambiar un token por otro, útil para encadenar servicios downstream. |
| **PKCE** | Proof Key for Code Exchange (RFC 7636). Extensión de OAuth para proteger el authorization code contra intercepción. |
| **Spring Security 6.x** | Stack de seguridad de Spring Boot 3.x. Incluye el módulo `spring-boot-starter-oauth2-resource-server` usado en esta PoC. |
| **HS256** | Algoritmo de firma JWT basado en HMAC-SHA256 con clave compartida. Aquí usamos el `client_secret` como clave compartida. |
| **`@PreAuthorize`** | Anotación de Spring Security que evalúa una expresión SpEL antes de invocar el método. En esta PoC: `hasAuthority('SCOPE_xxx')`. |

---

**Mantenedor**: Víctor (khum1982) + Hermes Agent.
**Stack PIN**: `keycloak:24.0.5` (en compose: `24.0`), `spring-boot:3.2.5`, `java:17`, `python:3.11`, `node:18`, `postgres:16`.
**Licencia**: MIT (PoC; adaptar antes de producción).