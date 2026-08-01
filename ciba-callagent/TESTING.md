# ciba-callagent — Guía de Pruebas

## Requisitos
- Docker + Docker Compose
- `curl` o cualquier cliente HTTP (Postman, httpie)

## 1. Arrancar

```bash
cd /home/vhdez/desarrollos-hermes/ciba-callagent
docker compose up --build -d

# Esperar ~60s a que Keycloak esté listo
sleep 60
```

Verificar que todo está arriba:

```bash
curl -s http://localhost:8081/health | python3 -m json.tool
curl -s http://localhost:8082/health | python3 -m json.tool
```

Deberían devolver `"status":"UP"` en ambos.

---

## 2. Credenciales de test

| | Valor |
|---|---|
| Keycloak Admin UI | http://localhost:8181/admin |
| Admin usuario | `admin` / `admin` |
| Test user | `testuser` / `testuser` |
| CIBA client | `ciba-agent` / `ciba-agent-secret` |

---

## 3. El flujo completo paso a paso

### Paso 1 — Solicitar autorización CIBA (el agente pide acceso)

```bash
curl -X POST http://localhost:8081/agent/request \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "testuser",
    "action": "calendar_list"
  }'
```

**Respuesta esperada (202 Accepted):**

```json
{
  "requestId": "a1b2c3d4",
  "authReqId": "<auth_req_id de Keycloak>",
  "bindingMessage": "Read your calendar",
  "mode": "poll",
  "statusUrl": "/agent/status/a1b2c3d4",
  "expiresIn": 300,
  "createdAt": "2026-08-01T..."
}
```

Guarda el `requestId` (ej: `a1b2c3d4`).

---

### Paso 2 — Poll del estado (mientras el usuario aprueba en Keycloak)

```bash
curl -s "http://localhost:8081/agent/status/a1b2c3d4" | python3 -m json.tool
```

**Respuesta mientras PENDING:**
```json
{
  "requestId": "a1b2c3d4",
  "status": "PENDING",
  "userId": "testuser",
  "bindingMessage": "Read your calendar"
}
```

Repetir cada 3-5 segundos hasta que el status sea `APPROVED`.

---

### Paso 3 — El usuario aprueba en Keycloak

1. Abre http://localhost:8181 y autentícate como `testuser` / `testuser`
2. Ve a **Account Console** → http://localhost:8181/realms/ciba-realm/account/
3. Busca la notificación de CIBA request pendiente
4. Approve

---

### Paso 4 — Ejecutar la acción

```bash
curl -X POST "http://localhost:8081/agent/execute/a1b2c3d4" | python3 -m json.tool
```

**Respuesta esperada:**
```json
{
  "success": true,
  "requestId": "a1b2c3d4",
  "userId": "testuser",
  "action": "calendar_list",
  "data": {
    "userId": "testuser",
    "action": "calendar_list",
    "scope": "openid profile email calendar.read",
    "endpoint": "/api/calendar/events",
    "events": [...]
  },
  "executedAt": "2026-08-01T..."
}
```

---

## 4. Todas las acciones disponibles

| Action | Scope requerido | Descripción |
|---|---|---|
| `calendar_list` | `calendar.read` | Listar eventos del calendario |
| `calendar_create` | `calendar.write` | Crear evento |
| `calendar_update` | `calendar.write` | Actualizar evento |
| `email_list` | (openid) | Listar bandeja de entrada |
| `email_send` | `email.send` | Enviar email |
| `email_modify` | `email.modify` | Modificar etiquetas/archivar |
| `profile` | (openid) | Perfil del usuario |
| `token_info` | (openid) | Info del token CIBA |

### Ejemplo: crear evento de calendario

```bash
# 1. Solicitar
curl -X POST http://localhost:8081/agent/request \
  -H "Content-Type: application/json" \
  -d '{"userId":"testuser","action":"calendar_create"}'

# 2. Aprobar en Keycloak

# 3. Ejecutar (mock — devuelve datos de prueba)
curl -X POST "http://localhost:8081/agent/execute/<requestId>"
```

---

## 5. Llamadas directas al Resource Server

Una vez tienes el `access_token` del paso anterior, puedes llamar directamente al Resource Server:

```bash
# Listar eventos (calendar.read)
curl -s http://localhost:8082/api/calendar/events \
  -H "Authorization: Bearer <access_token>" | python3 -m json.tool

# Crear evento (calendar.write)
curl -X POST http://localhost:8082/api/calendar/events \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"summary":"Reunión con cliente","start":"2026-08-05T10:00:00Z","end":"2026-08-05T11:00:00Z"}' \
  | python3 -m json.tool

# Bandeja de entrada
curl -s http://localhost:8082/api/email/inbox \
  -H "Authorization: Bearer <access_token>" | python3 -m json.tool

# Enviar email (email.send)
curl -X POST http://localhost:8082/api/email/send \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"to":"destinatario@example.com","subject":"Test","body":"Hola"}' \
  | python3 -m json.tool

# Modificar etiquetas (email.modify)
curl -X PATCH http://localhost:8082/api/email/message/msg-001/labels \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"labels":["INBOX","IMPORTANT","Archive"]}' \
  | python3 -m json.tool
```

---

## 6. Endpoints de diagnóstico

```bash
# Health check
curl -s http://localhost:8081/health
curl -s http://localhost:8082/health

# Info del cliente CIBA
curl -s http://localhost:8081/ciba/client-info

# Test directo CIBA (sin flow del agente)
curl -X POST "http://localhost:8081/ciba/auth-request?userId=testuser&scope=openid%20profile%20email%20calendar.read"

# Vaciar CTI cache (admin)
curl -X DELETE http://localhost:8082/admin/cti-cache
```

---

## 7. Simular aprobación CIBA (sin navegador)

Si no quieres usar el Account Console de Keycloak, puedes aprobar el CIBA request directamente via API de administración:

```bash
# Obtener auth_req_id del paso 1 (mirar en logs del container)
# docker logs ciba-oauth2-client --tail=20

# Approvar via Admin REST API de Keycloak
curl -X POST "http://localhost:8181/admin/realms/ciba-realm/clients/ciba-agent/backchannel-authentication-request" \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"action":"APPROVED"}'
```

O más fácil: en los logs de `ciba-oauth2-client` busca el `auth_req_id` y usa la API de polling directa:

```bash
# Poll directo al token endpoint de Keycloak
AUTH_REQ_ID="<del-log>"
curl -X POST "http://localhost:8081/ciba/poll/$AUTH_REQ_ID"
```

---

## 8. Verificar CTI replay prevention

El Resource Server rechaza tokens reuse:

```bash
# Primera llamada — OK
curl -s http://localhost:8082/api/calendar/events \
  -H "Authorization: Bearer <token>"

# Segunda llamada con el MISMO token — debe dar 401
curl -s http://localhost:8082/api/calendar/events \
  -H "Authorization: Bearer <token>"
# Esperado: {"error":"cti_replay","detail":"CTI replay attack detected..."}
```

---

## 9. Escenarios de error

```bash
# Action desconocida → 400
curl -X POST http://localhost:8081/agent/request \
  -H "Content-Type: application/json" \
  -d '{"userId":"testuser","action":"invalid_action"}'
# → {"error":"INVALID_REQUEST","detail":"Unknown action..."}

# Request no encontrado → 404
curl -s http://localhost:8081/agent/status/nonexistent

# Request aún PENDING → execute falla
curl -X POST "http://localhost:8081/agent/execute/a1b2c3d4"
# → {"success":false,"error":"Request not approved. Current status: PENDING"}

# Scope insuficiente → 403
# (Usar action=calendar_create pero token solo tiene calendar.read)
```

---

## 10. Limpiar

```bash
docker compose down
```
