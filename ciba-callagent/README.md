# ciba-callagent

> **AI Agent acting on behalf of a user via OpenID Connect CIBA**

Un agente IA (Hermes) accede a recursos del usuario (calendario, email, perfil) **sin que el usuario esté presente en una browser/app**. El flujo CIBA permite que el agente solicite acceso y el usuario apruebe desde su teléfono via push notification.

---

## Arquitectura

```
┌──────────┐   POST /authreq     ┌──────────────────┐
│  Agent   │ ──────────────────→  │    Keycloak      │
│  (Hermes)│  ← auth_req_id ────  │  (IdP + CIBA)   │
│  :7000   │                      │     :8180        │
└────┬─────┘                      └────────┬─────────┘
     │  poll /token                         │
     │ ──────────────────────────────────→ │
     │  ← access_token (tras approve) ──── │
     │                                      │
     │ GET /api/calendar/events             │
     │ Authorization: Bearer <token>        │
     │                                      │
     ▼                                      ▼
┌──────────────────┐               ┌─────────────────┐
│  Spring Boot     │               │  Phone / Auth    │
│  Resource Server │               │  App (push)      │
│  :8080           │               │                  │
└──────────────────┘               └──────────────────┘
```

## Componentes

| Servicio | Puerto | Descripción |
|---|---|---|
| `keycloak` | 8180 | IdP con CIBA habilitado |
| `spring-boot-api` | 8080 | CIBA Client + Resource Server |
| `agent-python` | 7000 | Agente IA FastAPI |

---

## Quick Start

```bash
# 1. Clonar y arrancar
docker compose up --build

# 2. Esperar a que Keycloak esté listo (~30s)
# Verificar: http://localhost:8180/admin

# 3. Probar el flujo CIBA
curl -X POST http://localhost:7000/auth/ciba-request \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "testuser",
    "action": "read_calendar",
    "params": {}
  }'
# → { "auth_req_id": "AR-xxx", "binding_message": "Read your calendar", ... }

# 4. Aprobar en la app de Keycloak Authenticator (o en el admin de Keycloak)
# Polling automático del agente devuelve el token

# 5. Ejecutar la acción con el token
curl -X POST http://localhost:7000/agent/execute/<request_id>
# → { "success": true, "data": { "events": [...] } }
```

---

## Endpoints

### Agent Python (puerto 7000)

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/auth/ciba-request` | Inicia flujo CIBA |
| `GET` | `/auth/status/{request_id}` | Consulta estado (pending/approved/denied) |
| `POST` | `/agent/execute/{request_id}` | Ejecuta acción con token CIBA |
| `GET` | `/health` | Health check |

### Spring Boot API (puerto 8080)

**CIBA Client (inicia auth):**

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/ciba/auth-request` | Envía authreq a Keycloak |
| `GET` | `/ciba/status/{auth_req_id}` | Estado del request |
| `POST` | `/ciba/poll/{auth_req_id}` | Poll manual |
| `POST` | `/ciba/ping-callback` | Callback para modo ping |

**Resource Server (protege recursos):**

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/calendar/events` | Eventos del calendario |
| `GET` | `/api/calendar/events/{id}` | Un evento |
| `GET` | `/api/calendar/calendars` | Lista de calendarios |
| `GET` | `/api/email/messages` | Emails |
| `GET` | `/api/email/folders` | Carpetas de email |
| `GET` | `/health` | Health check |

---

## El flujo CIBA paso a paso

```
1. AGENTE → KEYCLOAK  POST /protocol/openid-connect/ext/ciba/auth/authreq
   Body: { login_hint, binding_message, requested_scope }
   → auth_req_id (válido 5 minutos)

2. KEYCLOAK → TELÉFONO  Push notification
   "Confirm agent: Read your calendar"

3. AGENTE polls  KEYCLOAK  POST /ext/ciba/auth/token
   grant_type=urn:openid:params:grant-type:ciba&auth_req_id=AR-xxx
   → 400 { error: "authorization_pending" }  (mientras usuario decide)
   → 200 { access_token, id_token, expires_in }  (cuando aprueba)

4. AGENTE → SPRING BOOT  GET /api/calendar/events
   Authorization: Bearer <access_token>

5. SPRING BOOT valida el token:
   - JWT signature vs Keycloak JWKS
   - cti claim presente y único (replay prevention)
   - audiencia incluye calendar-api
   - scope contiene calendar.read

6. SPRING BOOT → AGENTE  200 { events: [...] }
```

---

## Validación CIBA (qué hace diferente)

Los tokens CIBA de Keycloak incluyen claims especiales que el Resource Server **debe** validar:

```
cti          — CIBA Token Identifier (replay prevention)
auth_req_id  — ID del request de autenticación
nonce        — Protección contra replay
```

El `CibaTokenValidator` de Spring Boot:
1. Decodifica el JWT contra JWKS de Keycloak
2. Verifica expiry, issuer, audience
3. **Impide reuse del cti** (Caffeine cache con TTL 24h)
4. Confirma presencia de `auth_req_id` y `cti`

---

## Modos CIBA

| Modo | Cómo funciona | Configuración |
|---|---|---|
| **poll** (default) | El agente pregunta cada N segundos | `keycloak.ciba-client.mode=poll` |
| **ping** | Keycloak llama a un callback URL cuando el usuario aprueba | `keycloak.ciba-client.mode=ping` + `backchannel-client-uri` |

---

## Credenciales de test

| Servicio | Usuario | Contraseña |
|---|---|---|
| Keycloak Admin | `admin` | `admin` |
| Test User | `testuser` | `testuser` |
| CIBA Client | `ciba-agent` | `ciba-agent-secret` |

---

## Desarrollo local (sin Docker)

```bash
# Terminal 1: Keycloak
docker run -p 8180:8080 \
  -e KEYCLOAK_ADMIN=admin -e KEYCLOAK_ADMIN_PASSWORD=admin \
  quay.io/keycloak/keycloak:26.0 start-dev --import-realm

# Terminal 2: Spring Boot
cd spring-boot-api && ./mvnw spring-boot:run

# Terminal 3: Agent Python
cd agent-python && pip install -r requirements.txt && python app.py
```

---

## Configuración

Variables de entorno (o `.env`):

```bash
KEYCLOAK_BASE_URL=http://localhost:8180
KEYCLOAK_REALM=ciba-realm
CIBA_CLIENT_ID=ciba-agent
CIBA_CLIENT_SECRET=ciba-agent-secret
CIBA_MODE=poll
SPRING_BOOT_API_URL=http://localhost:8080
```
