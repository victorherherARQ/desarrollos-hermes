# ciba-callagent

> **OpenID Connect CIBA — AI Agent acting on behalf of a user**

Un agente IA (Hermes) accede a recursos del usuario (calendario, email, perfil) **sin que el usuario esté presente**. El flujo CIBA permite que el agente solicite acceso y el usuario apruebe via push notification en su teléfono.

---

## Arquitectura — 3 servicios

```
┌──────────────┐   POST /authreq        ┌────────────────┐
│  Hermes      │ ─────────────────────→  │    Keycloak   │
│  (AI Agent)  │   ← auth_req_id ────  │    (IdP)       │
└──────┬───────┘   poll /token           │    :8180      │
       │  ① ──────────────────────────→ │               │
       │                                └──────┬────────┘
       │  ② push notification                    │
       │  ③ approval (authenticator app)          ▼
       │                                ┌────────────────┐
       │  GET /api/calendar  ④          │  Phone / Auth  │
       │  Authorization: Bearer ***     │  App (push)    │
       │                                └────────────────┘
       ▼
┌──────────────────────────────────────────────────────────────────┐
│                     Spring Boot                                 │
│                                                                  │
│  ┌─────────────────────────┐    ┌─────────────────────────────┐ │
│  │  CIBA OAuth2 Client     │    │  CIBA Resource Server        │ │
│  │  :8081                  │    │  :8082                      │ │
│  │                         │    │                             │ │
│  │  POST /agent/request    │    │  GET /api/calendar/events   │ │
│  │  GET  /agent/status/{id}│    │  GET /api/email/inbox       │ │
│  │  POST /agent/execute/{id}│    │  GET /api/user/profile      │ │
│  │                         │    │                             │ │
│  │  → Keycloak CIBA authreq│    │  → valida JWT + CTI replay │ │
│  │  → polls /token         │    │  → extrae user identity     │ │
│  └─────────────────────────┘    └─────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

## Servicios

| Servicio | Puerto | Rol |
|---|---|---|
| `keycloak` | 8180 | IdP con CIBA habilitado |
| `ciba-oauth2-client` | 8081 | Inicia authreq CIBA, polls Keycloak, expone API `/agent/**` |
| `ciba-resource-server` | 8082 | Valida JWT CIBA, sirve recursos protegidos |

---

## Quick Start

```bash
cd /home/vhdez/desarrollos-hermes/ciba-callagent
docker compose up --build

# Esperar ~30s a que Keycloak arranque
```

---

## El flujo completo

```
1. Hermes → ciba-oauth2-client:  POST /agent/request
   Body: { "userId": "testuser", "action": "read_calendar" }
   → 202 { requestId: "abc", authReqId: "AR-xxx", bindingMessage: "Read your calendar" }

2. ciba-oauth2-client → Keycloak:  POST /ext/ciba/auth/authreq
   → auth_req_id (válido 5 minutos)

3. Keycloak → Teléfono:  push notification
   "Read your calendar"

4. Hermes polls:  GET /agent/status/{requestId}
   → 200 { status: "PENDING" }  (mientras usuario decide)
   → 200 { status: "APPROVED", accessToken: "eyJ..." }  (cuando aprueba)

5. Hermes → ciba-resource-server:  GET /api/calendar/events
   Authorization: Bearer eyJ...

6. ciba-resource-server valida el token:
   - JWT signature vs Keycloak JWKS
   - cti claim → Caffeine cache (replay prevention)
   - scope contiene calendar.read
   → 200 { events: [...] }
```

---

## Endpoints

### ciba-oauth2-client — :8081

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/agent/request` | Inicia flujo CIBA |
| `GET` | `/agent/status/{id}` | Consulta estado (PENDING/APPROVED/DENIED) |
| `POST` | `/agent/execute/{id}` | Ejecuta acción con token CIBA |
| `POST` | `/ciba/auth-request` | CIBA directo (test) |
| `POST` | `/ciba/poll/{authReqId}` | Polling directo (test) |
| `GET` | `/health` | Health check |

### ciba-resource-server — :8082

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/api/calendar/events` | Eventos del calendario |
| `GET` | `/api/calendar/events/{id}` | Un evento |
| `GET` | `/api/calendar/calendars` | Lista de calendarios |
| `GET` | `/api/email/inbox` | Emails |
| `GET` | `/api/user/profile` | Perfil del usuario |
| `GET` | `/api/user/token-info` | Info del token CIBA |
| `GET` | `/health` | Health check |

---

## CIBA Token Validation (qué hace diferente el Resource Server)

Los tokens CIBA incluyen claims especiales:

| Claim | Propósito |
|---|---|
| `cti` | CIBA Token Identifier — unique, used for replay prevention |
| `auth_req_id` | ID del request de autenticación |
| `nonce` | Protección contra replay |

El `CibaTokenValidator` del Resource Server:
1. Decodifica JWT contra JWKS de Keycloak
2. **Verifica `cti`** → Caffeine cache marca como usado (replay = 401)
3. Confirma presencia de `auth_req_id`
4. Valida scope requerido (`calendar.read`, etc.)

---

## Credenciales de test

| | Usuario | Contraseña |
|---|---|---|
| Keycloak Admin | `admin` | `admin` |
| Test User | `testuser` | `testuser` |
| CIBA Client | `ciba-agent` | `ciba-agent-secret` |

---

## Ejemplo de uso

```bash
# 1. Iniciar flujo CIBA
curl -X POST http://localhost:8081/agent/request \
  -H "Content-Type: application/json" \
  -d '{"userId":"testuser","action":"read_calendar"}'

# 2. Poll hasta APPROVED (aprobar en la app de Keycloak Authenticator)
curl http://localhost:8081/agent/status/<requestId>

# 3. Cuando approved, ejecutar
curl -X POST http://localhost:8081/agent/execute/<requestId>

# 4. Con el token en el header, llamar directo al Resource Server
curl http://localhost:8082/api/calendar/events \
  -H "Authorization: Bearer <access_token>"
```

---

## Estructura del proyecto

```
ciba-callagent/
├── pom.xml                        # Parent POM (ciba-oauth2-client + ciba-resource-server)
├── docker-compose.yml
├── README.md
│
├── ciba-oauth2-client/            # ─── CIBA OAuth2 Client ───
│   ├── Dockerfile
│   ├── pom.xml
│   └── src/main/java/com/ciba/client/
│       ├── CibaClientApplication.java
│       ├── config/
│       │   ├── SecurityConfig.java
│       │   ├── CibaProperties.java
│       │   ├── AgentApiKeyFilter.java
│       │   └── WebClientConfig.java
│       ├── controller/
│       │   ├── CibaClientController.java  # /ciba/**
│       │   ├── AgentController.java       # /agent/**
│       │   └── PingCallbackController.java
│       ├── dto/
│       │   └── CibaClientDtos.java
│       └── service/
│           ├── CibaClientService.java    # WebClient → Keycloak CIBA
│           └── AgentOrchestrator.java     # state machine + RS calls
│
├── ciba-resource-server/          # ─── CIBA Resource Server ───
│   ├── Dockerfile
│   ├── pom.xml
│   └── src/main/java/com/ciba/resource/
│       ├── CibaResourceServerApplication.java
│       ├── config/
│       │   ├── SecurityConfig.java
│       │   ├── CtiReplayCache.java       # CTI replay prevention
│       │   └── CibaJwtAuthenticationConverter.java
│       ├── security/
│       │   ├── CibaTokenValidator.java   # CTI + scope validation
│       │   └── JwtClaimsExtractor.java
│       └── controller/
│           ├── CalendarController.java
│           ├── EmailController.java
│           ├── UserController.java
│           └── HealthController.java
│
├── keycloak/
│   ├── ciba-realm.json            # Realm export con CIBAenabled
│   └── import-realm.sh
└── docs/html/
    └── ciba-flow.html              # Visualizador HTML interactivo
```
