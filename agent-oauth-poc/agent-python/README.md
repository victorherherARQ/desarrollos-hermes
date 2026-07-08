# Agent Python -- OAuth/OIDC PoC (JWT Bearer + CIBA)

Agente IA escrito en Python + FastAPI que actúa **en nombre de usuarios**
del PoC. Obtiene tokens de Keycloak por delegación y llama a la API de
negocio (Spring Boot) con esos tokens.

Forma parte del PoC [`agent-oauth-poc`](../) que incluye:

```
┌──────────┐      ┌───────────┐      ┌─────────────┐      ┌──────────────┐
│ Persona  │─────▶│ Agente IA │─────▶│  Keycloak   │─────▶│ Cliente CIBA │
│ (curl)   │ HTTP │ (FastAPI) │      │  (IdP/OIDC) │      │   (mock)     │
└──────────┘      └─────┬─────┘      └──────┬──────┘      └──────┬───────┘
                        │                  │ ▲                   │
                        │ Bearer token     │ │ access_token      │
                        ▼                  ▼ │ (backchannel)     │
                  ┌─────────────┐           │ │                   │
                  │ Spring API  │◀──────────┘ │                   │
                  │ (negocio)   │ Bearer      │                   │
                  └─────────────┘             │                   │
                                             │  "approve?"        │
                                             └───────────────────┘
```

---

## 1. Componentes y responsabilidades

| Componente        | Rol                                                       |
| ----------------- | --------------------------------------------------------- |
| `app.py`          | FastAPI con `POST /agente/call` y `GET /agente/health`. Decide flujo y mapea scope → endpoint de la API. |
| `oauth_client.py` | `OAuthClient` con los dos flujos: `jwt_bearer_flow()` y `ciba_flow()`. |
| `config.py`       | Constantes: URLs de Keycloak, credenciales del agente (`agente-ia` / `secret-del-agente`), API base y usuarios. |
| `Dockerfile`      | Imagen `python:3.11-slim` con uvicorn.                    |

El agente es un **cliente OAuth confidential**: se autentica con
`client_id` + `client_secret` y firma las assertions con HS256 usando
ese mismo secret (perfil *client_secret JWT* de OIDC Core §9).

---

## 2. Flujos soportados

El endpoint `/agente/call` recibe:

```json
{
  "user_id": "ana",
  "request": "Envía un correo a Ana confirmando la reunión",
  "action_type": "Confirmación de reunión",
  "scope": "email.send"
}
```

Y la regla de decisión es **la terminación del scope**:

| Sufijo del scope | Sensibilidad | Flujo OAuth                          |
| ---------------- | ------------ | ------------------------------------ |
| `*.read`         | Rutinaria    | **JWT Bearer** (RFC 7523)            |
| `*.send`         | Sensible     | **CIBA** (OIDC Client Initiated Backchannel Authentication) |

### 2.1. JWT Bearer (rutinario, p.ej. `calendar.read`)

Pensado para acciones que el usuario ya **pre-aprobó** (consentimientos
almacenados en Keycloak para el agente sobre ese scope). El agente no
molesta al usuario.

```
Agente                                           Keycloak
  │                                                 │
  │  1. crea user_assertion (JWT HS256):            │
  │     {sub: "ana", iss: "agente-ia",              │
  │      aud: ".../token", exp: now+300}            │
  │ ──── POST /token ─────────────────────────────▶ │
  │      grant_type=urn:ietf:params:oauth:          │
  │              grant-type:jwt-bearer              │
  │      assertion=<user_assertion>                 │
  │      requested_scope=calendar.read              │
  │      client_id=agente-ia                        │
  │      client_secret=secret-del-agente            │
  │                                                 │
  │ ◀──── 200 OK ──────────────────────────────────  │
  │      { access_token, refresh_token, expires_in }│
  │                                                 │
```

### 2.2. CIBA (sensible, p.ej. `email.send`)

Para acciones que requieren **aprobación explícita y reciente** del
usuario fuera de banda. El agente "pide permiso" a través de Keycloak,
que notifica al cliente CIBA del usuario; mientras el usuario no
responda, el agente recibe `authorization_pending`.

```
Agente                  Keycloak                  Cliente CIBA (usuario)
  │                         │                            │
  │ 1. POST /ext/ciba/auth  │                            │
  │    login_hint_token,    │                            │
  │    scope, bind_token,   │                            │
  │    acr_values=2         │                            │
  │ ───────────────────────▶│                            │
  │                         │── backchannel: ───────────▶│
  │                         │   "¿aprobar email.send?"  │
  │ ◀── auth_req_id ────────│                            │
  │                         │                            │
  │ 2. poll /token          │                            │
  │    grant_type=ciba      │                            │
  │    auth_req_id=...      │                            │
  │ ───────────────────────▶│                            │
  │ ◀── authorization_pending ── (repetir cada N s)     │
  │                         │                            │
  │                         │       (usuario aprueba)    │
  │                         │◀───────────────────────────│
  │ ───────────────────────▶│                            │
  │ ◀── 200 access_token ───│                            │
```

### 2.3. Llamada a la API de negocio

Una vez con `access_token`, el agente llama a la API de Spring Boot
con `Authorization: Bearer <access_token>`:

| Scope          | Método | Endpoint                                 | Body                                                |
| -------------- | ------ | ---------------------------------------- | --------------------------------------------------- |
| `calendar.read` | GET   | `/api/calendar/events?user_id={user_id}` | --                                                  |
| `email.send`    | POST  | `/api/email/send`                        | `{to, subject, body}` (to = email del `user_id`)    |

---

## 3. Cómo levantarlo

### Standalone (sin Docker)

```bash
cd agent-python
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
LOG_LEVEL=DEBUG uvicorn app:app --host 0.0.0.0 --port 8000
```

### Con Docker (recomendado en el PoC)

Este agente está pensado para correr en la misma red compose que
Keycloak y la API Spring Boot:

```yaml
# docker-compose.yml (resumen)
services:
  agente-python:
    build: ./agent-python
    ports: ["8000:8000"]
    environment:
      LOG_LEVEL: INFO
    # comparte red con keycloak y spring-boot-api
```

```bash
docker compose up --build agente-python
```

### Probar

Healthcheck:

```bash
curl -s http://localhost:8000/agente/health
# {"status":"UP"}
```

Acción rutinaria (JWT Bearer -- no requiere interacción del usuario):

```bash
curl -s -X POST http://localhost:8000/agente/call \
  -H 'Content-Type: application/json' \
  -d '{
        "user_id":"ana",
        "request":"qué tengo hoy",
        "action_type":"read_calendar",
        "scope":"calendar.read"
      }'
```

Acción sensible (CIBA -- requiere que el usuario apruebe en el cliente
mock de CIBA):

```bash
curl -s -X POST http://localhost:8000/agente/call \
  -H 'Content-Type: application/json' \
  -d '{
        "user_id":"ana",
        "request":"manda recordatorio a Ana de la reunión",
        "action_type":"Recordatorio reunión",
        "scope":"email.send"
      }'
```

El endpoint quedará bloqueado en el polling hasta que el cliente CIBA
mock apruebe (o expire el `expires_in`).

---

## 4. Logs

Con `LOG_LEVEL=DEBUG` se ve el detalle de cada paso:

* `user_assertion creada: sub=ana iss=agente-ia aud=... exp=...`
* `[JWT-BEARER] POST .../token -> HTTP 200`
* `[CIBA] Paso 1/2: POST .../ciba/auth`
* `[CIBA] auth_req_id=... expires_in=120 interval=5`
* `[CIBA] poll t+5s -> POST /token`
* `[CIBA] ¡Aprobado! access_token obtenido`
* `[API] GET .../api/calendar/events?user_id=ana`

Con `LOG_LEVEL=INFO` se ven los hitos principales (inicio/fin de
flujo, decisión de scope, resultado de la llamada API).

---

## 5. Decisiones de diseño

* **Sin secretos en disco**: el `client_secret` se inyecta por env
  variable en producción; aquí está en `config.py` por ser PoC.
* **HS256 con client_secret** como perfil "client_secret JWT": es el
  perfil más simple de `private_key_jwt` y suficiente para un cliente
  confidential propio.
* **Polling CIBA con respeto al `interval`**: el cliente CIBA/Keycloak
  puede subir el `interval` si recibe demasiadas llamadas; el código lo
  respeta y, además, aborta si supera `expires_in`.
* **`bind_token == login_hint_token`**: simplificación del PoC (1
  cliente CIBA por usuario). En producción el `bind_token` lo emite el
  dispositivo del usuario tras un handshake.
* **Mapeo scope→endpoint en `app.py`**: se mantiene una sola tabla
  explícita (`calendar.read`, `email.send`) para que sea trivial añadir
  nuevos pares scope/endpoint.