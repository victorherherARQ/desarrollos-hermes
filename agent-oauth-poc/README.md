# 🛡️ Agent OAuth PoC — Agente de IA operando en nombre del usuario

> **Proof-of-Concept funcional** que demuestra cómo un agente de IA identifica al cliente que lo llama y obtiene tokens OAuth/OIDC para operar en su nombre contra APIs protegidas por Apigee.


> 📚 **Lee primero** [`docs/SETUP.md`](docs/SETUP.md) (cómo levantar la PoC paso a paso) y
> [`docs/ESTUDIO_COMPARATIVO.md`](docs/ESTUDIO_COMPARATIVO.md) (qué opciones OAuth existen y por qué se eligió esta).
> Detalle técnico en [`docs/POOL.md`](docs/POOL.md).

---

## 🎯 El problema

Tienes un usuario real (persona humana) y un **agente de IA** que necesita:

1. **Identificar al cliente** que lo llamó
2. Obtener un **access token OAuth** válido para APIs externas
3. Operar con **el menor privilegio** (no le das la cuenta entera)
4. Para acciones sensibles, que el usuario **apruebe en el momento**
5. **Auditabilidad total**: saber siempre quién pidió qué y quién lo hizo

---

## 📐 Arquitectura

```
                       ┌─────────────────────────┐
                       │      CLIENTE HUMANO     │
                       │   (Ana, Luis, Marta)    │
                       └────────────┬────────────┘
                                    │
                                    │ 📞 HTTP call
                                    ▼
                       ┌─────────────────────────┐
                       │   CLIENT-MOCK (:3000)   │◀──────┐
                       │   Simula app móvil      │       │
                       │   Notificaciones CIBA   │       │
                       └─────────────────────────┘       │
                                                        │ push
                       ┌─────────────────────────┐       │ notification
                       │    AGENTE IA (:7000)    │       │
                       │    FastAPI Python       │       │
                       └────────────┬────────────┘       │
                                    │                    │
                       ┌────────────▼────────────┐       │
                       │   KEYCLOAK (:8080)      │───────┘
                       │   Authorization Server  │
                       │   Realm: agent-poc      │
                       │   + CIBA habilitado     │
                       └────────────┬────────────┘
                                    │ valida JWT
                                    ▼
                       ┌─────────────────────────┐
                       │   SPRING BOOT API       │
                       │   (:9090)               │
                       │   Apigee-STUB           │
                       └─────────────────────────┘
                          (En producción: Apigee real)
```

---

## 🔐 Los flujos OAuth/OIDC

Este PoC implementa **dos patrones estándar combinados**, según la sensibilidad de la acción:

### Flujo 1 — JWT Bearer (rutinario, sin interacción)

**Cuándo**: scopes de solo lectura (ej. `calendar.read`)

**Cómo funciona**:

```
1. Ana llama al agente: "léeme el calendario"
2. El agente construye un user_assertion JWT firmado con su client_secret
   → sub=ana, iss=agente-ia, scope=calendar.read
3. POST /token con grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
   assertion=<user_assertion>
4. Keycloak valida y devuelve access_token para scope calendar.read
5. El agente llama a la API con Authorization: Bearer <token>
6. La API valida JWT, extrae claims, ejecuta la acción
```

**Estándar**: RFC 7523 (JWT Bearer Authorization Grant)

**Ventaja**: Ana configuró UNA VEZ la delegación y el agente puede actuar automáticamente para scope rutinarios.

### Flujo 2 — CIBA (sensible, con aprobación del usuario)

**Cuándo**: scopes que modifican datos (ej. `email.send`, `calendar.write`)

**Cómo funciona**:

```
1. Ana llama al agente: "envía un email a Pedro"
2. El agente construye login_hint_token firmado (sub=ana, scope=email.send)
3. POST /ext/ciba/auth con scope=email.send, login_hint_token, bind_token
4. Keycloak genera auth_req_id y lo manda al cliente mock de Ana (backchannel)
5. Keycloak devuelve auth_req_id al agente (status: pending)
6. Mientras tanto, el cliente mock muestra en la UI: "Ana, el agente quiere enviar email. ¿Apruebas?"
7. Ana toca [Aprobar] en la UI
8. El agente poll el /token hasta recibir access_token
9. El agente llama a la API con Authorization: Bearer <token>
10. La API valida JWT, ejecuta el envío
```

**Estándar**: OpenID Connect CIBA 1.0 (Client Initiated Backchannel Authentication)

**Ventaja**: El usuario SIEMPRE aprueba explícitamente acciones sensibles. Sin aprobación, no hay token.

---

## 🧱 Componentes

| Componente | Puerto | Tecnología | Propósito |
|---|---|---|---|
| `keycloak` | 8080 | Keycloak 24.0 | Authorization Server. Realm `agent-poc` con CIBA habilitado. |
| `postgres` | 5432 | Postgres 16 | Persistencia de Keycloak. |
| `spring-boot-api` | 9090 | Spring Boot 3.2 + Java 17 | **Apigee-stub** que valida JWT. En producción = Apigee real. |
| `agent-python` | 7000 | FastAPI Python 3.11 | El agente IA. Recibe llamadas, identifica usuario, obtiene token, opera. |
| `client-mock` | 3000 | Node 18 + Express | UI web que simula el móvil. Recibe CIBA push, usuario aprueba/rechaza. |

---

## 👥 Usuarios demo

| Usuario | Password | Email | Notas |
|---|---|---|---|
| `ana` | `demo1234` | ana@example.com | Persona con CIBA habilitado |
| `luis` | `demo1234` | luis@example.com | Persona con CIBA habilitado |
| `marta` | `demo1234` | marta@example.com | Persona con CIBA habilitado |

---

## 🔧 Scopes disponibles

| Scope | Tipo | Flujo | Endpoint |
|---|---|---|---|
| `calendar.read` | Rutinario | JWT Bearer | `GET /api/calendar/events` |
| `email.send` | Sensible | CIBA | `POST /api/email/send` |

---

## 🚀 Cómo arrancarlo

### Requisitos

- Docker + Docker Compose
- 8 GB RAM disponibles
- 2 GB disco

### Arrancar

```bash
cd /home/vhdez/desarrollos-hermes/agent-oauth-poc

# Levantar todo el stack
docker compose up -d --build

# Esperar ~2-3 min a que Keycloak arranque e importe el realm
# Ver logs
docker compose logs -f keycloak

# Confirmar que todo está UP
docker compose ps
```

### Verificar Keycloak

Una vez arrancado, abre:

```
http://localhost:8080/admin
```

Login: `admin` / `admin`. Realm: `agent-poc`. Verás:
- 3 usuarios (ana, luis, marta)
- 2 clientes (agente-ia, client-mock)
- Realm attributes con CIBA habilitado

---

## 🧪 Test end-to-end

### Test 1 — Flujo JWT Bearer (calendar.read)

**Terminal 1 — llamar al agente**:

```bash
curl -X POST http://localhost:7000/agente/call \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "ana",
    "request": "léeme mi calendario de hoy",
    "scope": "calendar.read"
  }'
```

**Salida esperada**:

```json
{
  "user": "ana",
  "agent": "agente-ia",
  "scope": "calendar.read",
  "flow": "jwt_bearer",
  "api_response": {
    "user": "ana",
    "events": [
      { "id": "evt1", "title": "Reunión", "when": "2026-07-08T10:00:00Z" }
    ]
  }
}
```

### Test 2 — Flujo CIBA (email.send)

**Terminal 1 — llamar al agente**:

```bash
curl -X POST http://localhost:7000/agente/call \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "ana",
    "request": "envía email a Pedro",
    "scope": "email.send"
  }'
```

**Respuesta del agente** (mientras espera):

```json
{ "status": "pending_ciba_approval", "auth_req_id": "..." }
```

**Navegador — abrir client-mock**:

```
http://localhost:3000
```

Selecciona "ana". Verás:

```
┌──────────────────────────────────────┐
│ El agente-ia quiere enviar email     │
│ Scope: email.send                    │
│ [Aprobar]   [Rechazar]               │
└──────────────────────────────────────┘
```

Click en **Aprobar**.

Vuelve a Terminal 1 — el agente terminó:

```json
{
  "user": "ana",
  "agent": "agente-ia",
  "scope": "email.send",
  "flow": "ciba",
  "api_response": { "status": "sent", "to": "..." }
}
```

### Test 3 — Acceso directo a la API (verificar JWT)

```bash
# Token de Ana (después del flujo)
TOKEN=$(curl -s -X POST http://localhost:8080/realms/agent-poc/protocol/openid-connect/token \
  -d 'grant_type=password' \
  -d 'client_id=agente-ia' \
  -d 'client_secret=secret-del-agente' \
  -d 'username=ana' \
  -d 'password=demo1234' \
  | jq -r '.access_token')

# Llamar a la API
curl -X GET "http://localhost:9090/api/calendar/events?user_id=ana" \
  -H "Authorization: Bearer $TOKEN" | jq
```

---

## 🔍 Inspección de tokens

Cada token generado tiene estos claims (visibles en https://jwt.io):

| Claim | Significado | Ejemplo |
|---|---|---|
| `sub` | Usuario real (subject) | `f8a1-...-ana-uuid` |
| `iss` | Quién lo emitió | `http://keycloak:8080/realms/agent-poc` |
| `aud` | Para qué API es | `spring-boot-api`, `agente-ia` |
| `scope` | Permisos concedidos | `calendar.read email.send` |
| `act` | Quién actúa en nombre de `sub` | `{ "sub": "agente-ia-client-id" }` |
| `exp` | Cuándo expira | `1718770123` (5 min) |

El claim **`act`** es la clave para auditoría: sabes que la acción la hizo el agente, pero el `sub` te dice por quién.

---

## 📊 Logs y auditoría

Cada servicio loguea con `info`:

```log
# En spring-boot-api
INFO: [AUDIT] sub=ana-uuid act=agente-ia scope=calendar.read
       evento=GET /api/calendar/events
       at=2026-07-06T19:55:00Z

# En agent-python
INFO: [CIBA] auth_req_id=abc-123 init OK
INFO: [CIBA] status=approved at 2026-07-06T19:55:02Z
INFO: [API] called /api/email/send with token (aud=spring-boot-api)
```

Para ver todos los logs de auditoría en un stream:

```bash
docker compose logs -f spring-boot-api | grep AUDIT
```

---

## 🔐 Por qué este diseño es seguro

| Riesgo | Mitigación en este diseño |
|---|---|
| Agente roba credenciales del usuario | El agente nunca toca passwords ni refresh tokens del usuario. Solo recibe user_assertion auto-firmado o usa CIBA sin identidad persistente. |
| Agente se compromete | Quitas `act` en Keycloak → agente muere. No tienes que tocar nada del usuario. |
| Token del agente se filtra | access_token dura **5 min**. Después caduca solo. |
| Usuario pierde control | Cada acción sensible requiere aprobación CIBA. Sin tocar "Aprobar" → no hay token. |
| Suplantación de identidad | El `sub` en cada token es el usuario real. El claim `act` es quién opera. Audit trail completo. |
| APIs externas reciben tokens del agente | Las APIs validan JWT contra Keycloak y ven `act`. Saben que es un agente, no un humano directo. |

---

## 📚 Estándares usados

| Estándar | Para qué |
|---|---|
| OAuth 2.0 (RFC 6749) | Base. Authorization framework. |
| OpenID Connect Core 1.0 | `id_token` para identificar usuarios |
| OAuth 2.0 + JWT Bearer (RFC 7523) | `urn:ietf:params:oauth:grant-type:jwt-bearer` para delegación |
| OIDC CIBA | Aprobación backchannel sin browser |
| RFC 8693 | Token Exchange (para futuro cuando escales) |
| PKCE (RFC 7636) | Protección contra intercepción del `code` |
| WebAuthn (opcional) | Para reemplazar password en producción |

---

## 🏭 Migración a producción

Este PoC está diseñado para ser **production-ready friendly**. Las piezas que cambian:

| En PoC | En producción |
|---|---|
| `spring-boot-api` (Spring Boot) | **Apigee real** (mismo estándar OIDC, mismas claims) |
| `client-mock` (Node UI) | **App móvil real** (iOS/Android) con push notifications FCM/APNs |
| `postgres` (DB del PoC) | **Postgres gestionado** (RDS, Cloud SQL) |
| Passwords en claro | **WebAuthn / passkeys** |
| 3 usuarios demo | **LDAP/AD/Okta federation** |
| Docker local | **Kubernetes / Cloud Run / ECS** |

Lo que **NO cambia**:

- Los flujos OAuth (CIBA + JWT Bearer siguen funcionando)
- El cliente `agente-ia` registrado en Keycloak
- Los scopes y sus definiciones
- El protocolo Apigee ↔ APIs
- Los claims en los tokens (`sub`, `act`, `scope`)

---

## 🛠️ Cómo se compara con otras opciones

| Patrón | Por qué no lo usamos |
|---|---|
| **Client Credentials Grant** (RFC 6749 §4.4) | El agente operaría con identidad propia, no del usuario. NO delega identidad real. |
| **Password Grant** (RFC 6749 §4.3) | Antipatrón. Comparte passwords. |
| **Implicit Flow** | Deprecado desde OAuth 2.1. |
| **Solo RFC 8693 Token Exchange** | Funciona pero no tiene "human in the loop" para acciones sensibles. |
| **Solo CIBA** | Pierdes la agilidad para scopes rutinarios que no necesitan aprobación. |

---

## 🚦 Próximos pasos (post-PoC)

1. **WebAuthn** en Keycloak: reemplazar passwords por passkeys biométricos
2. **Refresh tokens rotativos**: añadir capa con refresh + sliding sessions
3. **Token Exchange (RFC 8693)**: cuando necesites que el agente pase tokens a otros agentes downstream
4. **Apigee policy**: configurar el Apigee real con la misma lógica que el stub
5. **Logging centralizado**: enviar logs a Elasticsearch / Datadog
6. **MFA step-up**: forzar `acr_values=2` en CIBA para scopes críticos

---

## 📖 Documentación

| Archivo | Contenido |
|---|---|
| [`docs/ESTUDIO_COMPARATIVO.md`](docs/ESTUDIO_COMPARATIVO.md) | Análisis profundo (opción B) de las 7 opciones de OAuth/OIDC para un agente IA que actúa en nombre de un usuario en APIs Spring Boot+Apigee, con tabla de scoring ponderada y roadmap. |
| [`docs/POOL.md`](docs/POOL.md) | Documentación técnica exhaustiva de esta PoC: arquitectura, 5 contenedores, JWT claims, mapeo scopes→authorities, **causa raíz documentada del bug `invalid_scope` en Keycloak 24**, tests end-to-end, limitaciones y trabajo futuro. |
| [`docs/SETUP.md`](docs/SETUP.md) | Guía paso-a-paso reproducible para levantar la PoC desde cero y ejecutar los 5 tests end-to-end. Cheatsheet de operaciones frecuentes y troubleshooting. |
| `keycloak/realm/README.md` | Detalle del realm y CIBA config |

---

**Última actualización**: 2026-07-06
**Mantenedor**: Victor (khum1982) + Hermes
**Licencia**: MIT (es un PoC, adaptalo a tu necesidad)