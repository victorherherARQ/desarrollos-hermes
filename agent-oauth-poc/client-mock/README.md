# 📱 Client Mock — Mobile UI para CIBA Push Notifications

Simula el **móvil del usuario** recibiendo notificaciones push de
[Keycloak CIBA](https://www.keycloak.org/docs/latest/server_admin/index.html#_ciba)
(Client Initiated Backchannel Authentication) cuando un agente IA
solicita tokens con scopes sensibles.

> **⚠ PoC — solo UI.** La autenticación real del usuario (biometría,
> PIN, push del SO) sería responsabilidad de la app móvil real. Aquí
> simplemente seleccionas tu identidad (`ana`, `luis`, `marta`) en el
> dropdown y ves las notificaciones.

---

## 🎯 Cómo funciona

```
┌──────────────┐  1. POST /ciba/notify   ┌──────────────┐
│   Keycloak   │ ───────────────────────▶│  client-mock │
│   (CIBA)     │                         │   (este UI)  │
└──────────────┘                         └──────┬───────┘
                                                │ 2. polling cada 2s
                                                ▼
                                         ┌──────────────┐
                                         │  Navegador   │
                                         │  del user    │
                                         │  (ana/luis/  │
                                         │   marta)     │
                                         └──────────────┘
```

1. **El agente** pide a Keycloak un token CIBA para scopes sensibles
   (ej. `calendar.read`, `email.send`).
2. **Keycloak** envía una *backchannel notification* a este servicio
   vía `POST /ciba/notify` con `{ auth_req_id, user, scope, agent, ... }`.
3. **Este servicio** guarda la petición en memoria.
4. **El navegador del usuario** (abriendo `http://localhost:3000`)
   hace polling cada 2s a `/api/pending-requests?user=X`.
5. **El usuario** ve una notificación tipo push y pulsa **Aprobar**
   o **Rechazar**.
6. El servidor marca la request como `approved` / `rejected`.
7. El **agente**, al consultar el token endpoint de Keycloak, recibe
   el `access_token` (si aprobado) o un error (si rechazado/expirado).

---

## 🚀 Cómo se accede

### Opción A — Docker Compose (recomendado, junto al resto del PoC)

El `docker-compose.yml` raíz ya incluye este servicio:

```yaml
client-mock:
  build: ./client-mock
  ports:
    - "3000:3000"
  environment:
    AGENT_URL: http://agent-python:7000
```

```bash
cd /home/vhdez/desarrollos-hermes/agent-oauth-poc
docker compose up -d client-mock
```

Abrir en el navegador:

```
http://localhost:3000
```

### Opción B — local con Node 18+

```bash
cd /home/vhdez/desarrollos-hermes/agent-oauth-poc/client-mock
npm install
npm start
```

Abrir `http://localhost:3000`.

---

## 🔌 Endpoints

| Método | Ruta                          | Descripción                                             |
|--------|-------------------------------|---------------------------------------------------------|
| `POST` | `/ciba/notify`                | Keycloak notifica una nueva petición CIBA               |
| `GET`  | `/api/pending-requests?user=` | Lista notificaciones de un usuario                      |
| `POST` | `/approve`                    | Aprueba una notificación (`{ auth_req_id }`)            |
| `POST` | `/reject`                     | Rechaza una notificación (`{ auth_req_id }`)            |
| `GET`  | `/healthz`                    | Healthcheck (`{ status: "UP" }`)                        |
| `GET`  | `/`                           | UI móvil (`public/index.html`)                          |

### Ejemplos con curl

**Simular una notificación CIBA** (lo que haría Keycloak):

```bash
curl -X POST http://localhost:3000/ciba/notify \
  -H "Content-Type: application/json" \
  -d '{
    "auth_req_id": "req-abc-123",
    "user": "ana",
    "scope": "calendar.read email.send",
    "agent": "agente-ia",
    "request_text": "Quiere leer tu calendario y enviar un email a jose@example.com",
    "expires_at": 1735689600
  }'
```

**Listar pendientes de `ana`:**

```bash
curl http://localhost:3000/api/pending-requests?user=ana
```

**Aprobar / rechazar:**

```bash
curl -X POST http://localhost:3000/approve \
  -H "Content-Type: application/json" \
  -d '{"auth_req_id":"req-abc-123"}'

curl -X POST http://localhost:3000/reject \
  -H "Content-Type: application/json" \
  -d '{"auth_req_id":"req-abc-123"}'
```

---

## 🧱 Estructura

```
client-mock/
├── package.json          # deps: express, body-parser
├── server.js             # Express app + endpoints
├── Dockerfile            # node:18-alpine, expone 3000
├── README.md             # este archivo
└── public/
    └── index.html        # UI móvil (selector + cards + polling)
```

---

## 🔐 Configurar Keycloak para que apunte aquí

En la **CIBA policy** del realm `agent-poc`, el *Client Notification
Mechanism* debe apuntar a este servicio:

- **CIBA Backchannel Token Delivery Mode**: `poll` o `ping`
- **Client Notification Endpoint**:
  `http://client-mock:3000/ciba/notify` *(dentro de la red docker)*
  o `http://host.docker.internal:3000/ciba/notify` *(Mac/Windows)*

> En esta PoC el flujo CIBA real lo dispara el `agent-python`
> automáticamente; este mock solo necesita estar arriba y accesible
> en la red `agent-poc-net`.

---

## ⚠ Limitaciones (es PoC)

- Estado **en memoria**: si reinicias el contenedor se pierden las
  notificaciones pendientes. Para producción → Redis/Postgres.
- **Sin auth**: cualquiera con acceso a `:3000` ve todas las
  identidades. En producción → JWT + binding al device.
- **Sin notificación push real** (FCM/APNs): se sustituye por
  polling cada 2s en la UI.

---

## 🧪 Smoke test rápido

```bash
# 1. health
curl http://localhost:3000/healthz
# → {"status":"UP"}

# 2. inyectar notificación
curl -X POST http://localhost:3000/ciba/notify \
  -H "Content-Type: application/json" \
  -d '{"auth_req_id":"test-1","user":"ana","scope":"calendar.read",
       "agent":"agente-ia","request_text":"Leer tu calendario"}'

# 3. abrir http://localhost:3000 → seleccionar "ana" → ver la card
```