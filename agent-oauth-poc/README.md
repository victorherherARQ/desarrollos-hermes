# 🛡️ Agent OAuth PoC v2 — Agente de IA con A+B+C estándar

> **Proof-of-Concept v2** que demuestra cómo un agente de IA opera de forma segura **en nombre de un usuario humano** contra APIs protegidas, **sin password grant, sin CIBA**.
>
> Implementa los **3 flujos OAuth/OIDC estándar** que cualquier IdP moderno soporta — portable entre **Keycloak 24** y **Azure AD B2C External ID**.

> 📚 Lee primero [`docs/SETUP.md`](docs/SETUP.md) (cómo levantarla) y [`docs/POOL.md`](docs/POOL.md) (detalle técnico exhaustivo).
> Estudio de migración a B2C: [`docs/ESTUDIO_AZURE_B2C.md`](docs/ESTUDIO_AZURE_B2C.md).

---

## 🎯 El problema

Tienes un **usuario humano** y un **agente de IA** que necesita:

1. **Identificar al usuario** que lo llamó
2. **Obtener tokens OAuth/OIDC** válidos para APIs externas — **sin que el humano comparta password**
3. **Operar con el menor privilegio** (scope mínimo)
4. **Renovar tokens sin molestar al humano cada vez**
5. **Ser portable** entre Keycloak y Azure B2C
6. **Auditabilidad total**: `sub` = humano que actúa, `azp` = cliente que pidió el token

---

## 🚫 Lo que NO hace (decisiones de seguridad)

| Antipatrón | Por qué eliminado |
|---|---|
| ❌ **ROPC / Password Grant** | El agente vería la contraseña del humano. En producción esto es inaceptable. |
| ❌ **CIBA** | Microsoft Azure B2C External ID NO soporta CIBA. Para migrar a B2C (o para producción) necesitamos flujos estándar. |
| ❌ **Implicit Flow** | Deprecado en OAuth 2.1. |
| ❌ **Solo Client Credentials** | El agente se identifica a sí mismo, no al usuario. No delega identidad real. |

---

## ✅ Lo que SÍ hace — 3 flujos estándar implementados

### Flujo A — Authorization Code + PKCE (RFC 6749 + RFC 7636)

**Cuándo**: hay un browser del humano cerca (webapp cliente, app móvil).

```
1. Cliente → agente: POST /agente/auth/authorize {user_id, scope}
2. Agente → cliente: {authorize_url, code_verifier, state, redirect_uri}
3. Cliente redirige al browser del humano al authorize_url
4. Humano aprueba en IdP (login + MFA)
5. IdP redirige a client-mock/callback?code=...&state=...
6. Client-mock → IdP: POST /token (con code + code_verifier)
7. Client-mock recibe {access_token, refresh_token, id_token}
8. Cliente entrega access_token al agente
9. Agente llama a la API con Authorization: Bearer <token>
```

**Standards**: RFC 6749 §4.1 (Authorization Code) + RFC 7636 (PKCE).

**Portable**: KC 24 ✅ | B2C External ID ✅.

### Flujo B — Device Code Flow (RFC 8628)

**Cuándo**: agente headless (CLI, server, CI/CD, kiosko) sin UI del humano cerca.

```
1. Cliente → agente: POST /agente/auth/device {user_id, scope}
2. Agente → IdP: POST /device_authorization_endpoint
3. IdP → agente: {device_code, user_code, verification_uri, expires_in=600, interval=5}
4. Agente imprime: "Ve a https://idp/device e introduce: ABCD-1234"
5. [humano va a su dispositivo, introduce user_code, aprueba]
6. Agente hace polling cada 5s: POST /token grant_type=urn:ietf:params:oauth:grant-type:device_code
7. IdP → agente: {access_token, refresh_token}
```

**Standards**: RFC 8628 (Device Code Flow).

**Portable**: KC 24 ✅ | B2C External ID ✅.

### Flujo C — On-Behalf-Of / JWT Bearer (RFC 7523)

**Cuándo**: el agente tiene un `user_access_token` (de A o B) y necesita un token delegado con scope más limitado.

```
1. Cliente → agente: POST /agente/call {access_token, scope}
2. Agente decodifica el JWT (sin verificar firma) y lee el scope actual
3. Si el scope pedido YA está en el token → flujo A (o B)
4. Si NO está → agente hace OBO:
   POST /token
     grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
     assertion=<user_access_token>
     requested_scope=<scope mínimo>
     requested_token_use=on_behalf_of
5. IdP → agente: {access_token (refinado)}
```

**Standards**: RFC 7523 (JWT Bearer) + RFC 8693 (Token Exchange cousin).

**Portable**: B2C External ID ✅ nativo. **Keycloak 24 ⚠️** requiere KC 26+. En KC 24 la PoC pide el scope completo en el paso A.

---

## 📐 Arquitectura

```
                       ┌─────────────────────────┐
                       │     USUARIO / CLIENTE   │
                       │ (Ana, Luis o Marta)     │
                       │   Device (browser / app)│
                       └────────────┬────────────┘
                                    │ A: PKCE  B: User Code
                                    │
                ┌───────────────────┴───────────────────┐
                ▼                                       ▼
       ┌────────────────────┐                ┌────────────────────┐
       │ client-mock :3000  │                │ Agente (headless)  │
       │ Webapp del usuario │                │ o CI/CD            │
       │ Auth Code + PKCE   │                │ B: Device Code     │
       │ Device Code UI     │                │                    │
       └─────────┬──────────┘                └─────────┬──────────┘
                 │ POST /token (PKCE)                  │ POST /device
                 │                                      │
                 ▼                                      ▼
       ┌──────────────────────────────────────────────────────────────────┐
       │     IdP (Keycloak 24 / Azure B2C External ID)                   │
       │     http://keycloak:8080  o  https://<tenant>.ciamlogin.com     │
       │  Emite: access_token, refresh_token, id_token                   │
       └──────────────────────────┬───────────────────────────────────────┘
                                  │ Bearer JWT
                                  ▼
       ┌──────────────────────────────────────────────────────────────────┐
       │ agent-poc-agent-python :7000                                    │
       │ FastAPI · OAuthClient (A+B+C en una clase unificada)            │
       │ - A: gestiona authorize_url + PKCE pair                         │
       │ - B: device_code + polling                                      │
       │ - C: OBO exchange (refinar scope)                               │
       │ Llama a Spring API con Bearer                                   │
       └──────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
       ┌──────────────────────────────────────────────────────────────────┐
       │ agent-poc-spring-boot-api :9090                                 │
       │ Apigee-stub · Resource Server                                   │
       │ @PreAuthorize("hasAuthority('SCOPE_xxx')")                     │
       └──────────────────────────────────────────────────────────────────┘
```

---

## 🧱 Componentes

| Componente | Puerto | Tecnología | Propósito |
|---|---|---|---|
| `keycloak` | 8180 | Keycloak 24.0 | IdP (PKCE + Device Code activados; **sin** ROPC ni CIBA) |
| `postgres` | (interno) | Postgres 16 | Persistencia de Keycloak |
| `spring-boot-api` | 9090 | Spring Boot 3.2 + Java 17 | **Apigee-stub** que valida JWT. En producción = Apigee real |
| `agent-python` | 7000 | FastAPI Python 3.11 | Agente IA — refactorizado con A+B+C |
| `client-mock` | 3000 | Node 18 + Express | Webapp que ahora hace Auth Code + PKCE (no más receptor CIBA) |

---

## 👥 Usuarios demo

| Usuario | Password | Email | Notas |
|---|---|---|---|
| `ana` | `demo1234` | ana@example.com | Demo user — el password solo lo teclea el humano en KC login |
| `luis` | `demo1234` | luis@example.com | Demo user |
| `marta` | `demo1234` | marta@example.com | Demo user |

> ⚠️ **Importante**: el agente **nunca** lee ni transmite estos passwords. El humano los teclea **solo** en la pantalla de login del IdP.

---

## 🔧 Scopes disponibles

| Scope | Tipo | Endpoint | Ejemplo de flujo |
|---|---|---|---|
| `calendar.read` | Rutinario | `GET /api/calendar/events` | A o B |
| `email.send` | Sensible | `POST /api/email/send` | A (con MFA) o B |

Los scopes `calendar.write` y `email.modify` están creados en Keycloak pero **no tienen endpoint** en Spring en esta PoC.

---

## 🚀 Cómo arrancarlo

```bash
cd /home/vhdez/desarrollos-hermes/agent-oauth-poc

# Levantar el stack
docker compose up -d --build

# Esperar a Keycloak (~45-90 s)
until curl -sf http://localhost:8180/realms/master/.well-known/openid-configuration > /dev/null; do
  printf '.'; sleep 3
done
echo "Keycloak ready"

# Provisionar el realm v2 (PKCE + Device Code; sin ROPC ni CIBA)
KEYCLOAK_URL=http://localhost:8180 python3 scripts/create_realm.py --reset

# (Solo si hay código nuevo) restart de los 2 servicios
docker restart agent-poc-agent-python agent-poc-client-mock

# Verificar
curl -s http://localhost:7000/agente/health | jq .
# → {
#     "status": "UP",
#     "idp_issuer": "...",
#     "agent_client_id": "agente-ia",
#     "supported_flows": ["A:auth_code+pkce", "B:device_code", "C:obo"]
#   }
```

---

## 🧪 Tests end-to-end — Los 3 flujos

### Test A · Auth Code + PKCE

```bash
# Paso 1: cliente pide authorize URL al agente
RESP=$(curl -s -X POST http://localhost:7000/agente/auth/authorize \
  -H "Content-Type: application/json" \
  -d '{"user_id":"ana","scope":"openid profile email calendar.read"}')
echo "$RESP" | jq .

# Paso 2: HUMANO abre authorize_url en su browser
# Paso 3: KC autentica a Ana (login + MFA si se solicitó)
# Paso 4: client-mock recibe /auth/callback?code=...&state=...
# Paso 5: client-mock obtiene los tokens y los guarda en su session store

# Paso 6: el cliente-mock expone los tokens
SESSION_ID=<sid_devuelto>
curl -s http://localhost:3000/auth/session/$SESSION_ID | jq .

# Paso 7: con el access_token, llamar a la API vía agente
ACCESS_TOKEN=*** arriba>
curl -s -X POST http://localhost:7000/agente/call \
  -H "Content-Type: application/json" \
  -d "{\"access_token\":\"$ACCESS_TOKEN\",\"request\":\"mis eventos\",\"scope\":\"calendar.read\",\"action_type\":\"read_calendar\"}" | jq .
```

### Test B · Device Code Flow

```bash
# Paso 1: pedir device_code
RESP=$(curl -s -X POST http://localhost:7000/agente/auth/device \
  -H "Content-Type: application/json" \
  -d '{"user_id":"ana","scope":"openid profile email calendar.read"}')
USER_CODE=$(echo "$RESP" | jq -r .user_code)
VERIFY=$(echo "$RESP" | jq -r .verification_uri)
echo "User code: $USER_CODE"
echo "Verification URI: $VERIFY"

# Paso 2: HUMANO abre la URL e introduce el user_code
xdg-open "$VERIFY"  # o pegar en browser

# Paso 3: el agente, internamente, hace polling hasta que llegue el access_token
# (en PoC este polling bloquea ~5-30s)
```

### Test C · OBO exchange

> ⚠️ Requiere **Keycloak 26+** para soporte nativo. En KC 24 el código detecta y se adapta pidiendo el scope completo en A.

```bash
# Solo aplicable si IdP soporta requested_token_use=on_behalf_of
ACCESS_TOKEN=*** arriba>
curl -s -X POST http://localhost:7000/agente/call \
  -H "Content-Type: application/json" \
  -d "{\"access_token\":\"$ACCESS_TOKEN\",\"request\":\"...\",\"scope\":\"email.send\",\"action_type\":\"...\"}" | jq .
# Si el scope 'email.send' no está en el JWT actual, el agente hace OBO (en KC 26+ / B2C).
```

### Test negativo · Token sin scope → 401/403

```bash
TOKEN=*** -s -X POST http://localhost:8180/realms/agent-poc/protocol/openid-connect/token \
  -d 'grant_type=password' \
  -d 'client_id=agente-ia' \
  -d 'client_secret=secret-del-agente' \
  -d 'username=ana' \
  -d 'password=demo1234' \
  -d 'scope=openid' | jq -r .access_token)

curl -i "http://localhost:9090/api/calendar/events?user_id=ana" \
     -H "Authorization: Bearer *** | head -n 1
# Esperado: HTTP/1.1 401 (o 403 según config)
```

> **Nota**: este test usa ROPC password grant **únicamente** para validar la API de Spring, NO como flujo del agente. El agente real nunca usa ROPC.

---

## 🔍 Inspección de tokens

Cada token generado tiene estos claims:

| Claim | Significado | Ejemplo |
|---|---|---|
| `sub` | Usuario real (subject) | UUID de Ana |
| `iss` | Quién lo emitió | `http://keycloak:8080/realms/agent-poc` |
| `aud` | Para qué API es | `spring-boot-api`, `agente-ia` |
| `scope` | Permisos concedidos | `calendar.read email.send` |
| `azp` | Authorized party (cliente que pidió el token) | `agente-ia` |
| `exp` | Cuándo expira | `1718770123` (5 min) |

El claim **`azp`** es la clave para auditoría: sabes que la acción la pidió el agente, pero `sub` te dice por quién se hizo.

---

## 📊 Logs y auditoría

```log
# En agent-python (con LOG_LEVEL=INFO)
INFO: [A] Construyendo authorize URL: user=ana scope=calendar.read
INFO: [A] Intercambiando code por tokens...
INFO: [C/OBO] scope=email.send NO está en el token, aplicando OBO...
INFO: [API] POST http://spring-boot-api:9090/api/email/send

# En spring-boot-api
INFO: [AUDIT] sub=ana-uuid azp=agente-ia scope=email.send
       endpoint=POST /api/email/send at=2026-07-08T...
```

```bash
# Ver todos los logs de auditoría
docker compose logs -f agent-python | grep -E "\[A\]|\[B\]|\[C\]"
docker compose logs -f spring-boot-api | grep AUDIT
```

---

## 🔐 Por qué este diseño (v2) es seguro

| Riesgo | Mitigación en este diseño (v2) |
|---|---|
| Agente roba credenciales del usuario | **Imposible**: el agente nunca tiene acceso al password. El humano lo teclea SOLO en IdP. El agente solo recibe `access_token` (corto) o un JWT canjeable. |
| ROPC grant desactivado por seguridad | `directAccessGrantsEnabled: false` en el realm. El password grant ya no funciona, ni siquiera para tests manuales. |
| Agente se compromete | Quitas `agente-ia` en IdP → agente muere. **Sin tocar nada del usuario.** |
| Token del agente se filtra | Access_token dura **5 min**. Refresh_token rota con cada uso. |
| Suplantación de identidad | `sub` en cada token es el usuario real. `azp` es el cliente que pidió el token. Audit trail completo vía logs. |
| Costo Azure B2C | Free tier = **50.000 MAU gratis**. Suficiente para una PoC completa. |

---

## 📚 Estándares usados

| Estándar | Para qué |
|---|---|
| OAuth 2.0 (RFC 6749) | Base. Authorization framework. |
| OpenID Connect Core 1.0 | `id_token` para identificar usuarios |
| PKCE (RFC 7636) | Protección del authorization code en A |
| Device Code (RFC 8628) | Flujo B para agentes headless |
| JWT Bearer (RFC 7523) | Flujo C: On-Behalf-Of |
| WebAuthn (opcional) | Para reemplazar password en producción |

> **Ya NO usamos**: CIBA (eliminado de la PoC por incompatibilidad con B2C).

---

## 🏭 Migración a Azure B2C — Pasos

```bash
# 1. Crear tenant en azure.com/entra/external-id (~10 min en portal)
# 2. Crear user flow "signup_signin_v1" con Passkey como MFA
# 3. Crear App Registration → obtener client_id + client_secret
# 4. (Opcional) Crear un segundo App Registration para Spring API → aud=spring-boot-api
# 5. Exportar env vars en docker-compose override:
```

```yaml
# docker-compose.override.yml
services:
  agent-python:
    environment:
      IDP_ISSUER: https://<tenant>.ciamlogin.com/<tenant_id>.onmicrosoft.com
      AGENT_CLIENT_ID: <app-id>
      AGENT_CLIENT_SECRET: <secret>
```

**Cero cambios en código Python.** La detección automática de B2C en `config.py:25-40` selecciona los paths correctos.

Detalle en [`docs/ESTUDIO_AZURE_B2C.md`](docs/ESTUDIO_AZURE_B2C.md).

---

## 🔄 Lo que cambió en v2 (migración desde v1)

| Aspecto | v1 (CIBA + ROPC) | v2 (A+B+C) |
|---|---|---|
| Flujo rutinario | ROPC password grant | Auth Code + PKCE (A) o Device Code (B) |
| Flujo sensible | CIBA con push | Auth Code + PKCE con MFA síncrono (A) |
| Agente conoce password | Sí (inseguro) | **No** (humano lo teclea en IdP) |
| Portable a B2C | No (B2C no tiene CIBA) | **Sí** (mismo flujo A/B/C) |
| PKCE habilitado | No | **Sí** |
| Device Code habilitado | No | **Sí** |
| OBO disponible | Vía ROPC (inseguro) | Vía RFC 7523 estándar |
| Refinado de scope | Imposible (ROPC da todo) | **Sí** con OBO |

---

## 🚦 Próximos pasos (post-PoC)

1. **Actualizar a Keycloak 26+** para soporte OBO nativo en PoC v2 ✅ ya queda path
2. **Refresh tokens con rotación**: ya implementado en `oauth_client.refresh_user_token()`; integrar persistencia en `client-mock`
3. **MFA forzado** vía `acr_values=2` para scopes críticos (`email.send`, `*.modify`)
4. **Logging centralizado** con Loki/ELK y campos estructurados
5. **Rate limiting** en FastAPI middleware
6. **CI con GitHub Actions** que levante el stack y corra los 3 tests E2E

---

## 📖 Documentación

| Archivo | Contenido |
|---|---|
| [`docs/SETUP.md`](docs/SETUP.md) | Quickstart + tests E2E + troubleshooting |
| [`docs/POOL.md`](docs/POOL.md) | Doc técnica exhaustiva, causa raíz del bug `invalid_scope`, tests plantilla, limitaciones y trabajo futuro |
| [`docs/ESTUDIO_AZURE_B2C.md`](docs/ESTUDIO_AZURE_B2C.md) | Estudio de migración a B2C + replanteamiento de flujos (§14) |
| [`docs/ESTUDIO_COMPARATIVO.md`](docs/ESTUDIO_COMPARATIVO.md) | Análisis de las opciones OAuth/OIDC para el agente |
| `keycloak/realm/README.md` | Detalle del realm v2 |

---

**Última actualización**: 2026-07-08 (v2 — A+B+C)
**Mantenedor**: Victor (khum1982) + Hermes Agent
**Licencia**: MIT (es un PoC, adaptalo a tu necesidad)
