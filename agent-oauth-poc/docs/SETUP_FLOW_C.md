# SETUP · agent-oauth-poc — Flujo C con Identity Claim (DNI+DOB)

> Guía específica para configurar **Keycloak 24** de forma que acepte el flujo C
> con **identity-assertion** basada en datos identificativos (DNI + fecha de nacimiento)
> en lugar de voiceprint.
>
> **Estado**: documentación nueva 2026-07-08. Reemplaza la versión voice-first del
> flujo C. No requiere migración de datos de usuario (DNI+DOB ya están en la tabla
> interna del agente).
>
> **Diferencia con v2-voice**: el cambio es **en la assertion que firma el agente**
> y en **los protocol mappers del realm** que traducen esos claims al access_token.
> La arquitectura (JWT Bearer / RFC 7523) y el canal (push + biometría) son los mismos.

---

## 1. TL;DR — qué cambia respecto a v2-voice

| Pieza | v2-voice | v3-identity-claim (actual) |
|---|---|---|
| Identificación humana | voiceprint + nº entrante | DNI + fecha de nacimiento |
| Factor de auth primario | algo-que-eres (voz) | algo-que-sabe (DNI) + algo-que-tiene (DNI físico) |
| Push step-up | ✅ | ✅ (idéntico) |
| Biometría móvil | ✅ | ✅ (idéntica) |
| ACR final | `phone-voice+push-biometric` | `id-claim+push-biometric` |
| Claims custom en assertion | `voice_verified`, `voiceprint_score`, `caller_phone` | `dni_verified`, `dob_verified`, `identity_method` |
| Verificación de la identidad | matching interno (cosine sim > 0.92) | tabla DNI+DOB hasheada con SHA-256 (PoC) / servicio externo AEAT/SEP (prod) |
| Endpoint del agente | (n/a — el agente ya tenía voz) | `POST /agente/auth/identity` |

**El resto del flujo C es idéntico**:
1. Cliente envía DNI+DOB → agente verifica contra tabla
2. Agente firma identity-assertion JWT con sus claves
3. Agente canjea assertion → access_token en Keycloak
4. Push al móvil de Ana + biometría
5. access_token final con `acr=id-claim+push-biometric`

---

## 2. Requisitos en Keycloak 24

Para que Keycloak acepte la JWT bearer assertion firmada por el agente, el realm
`agent-poc` necesita:

### 2.1 Client `agente-ia` con permisos JWT Bearer

El cliente confidencial `agente-ia` debe tener activado el flujo
`urn:ietf:params:oauth:grant-type:jwt-bearer`. KC 24 lo soporta pero **no lo activa
por defecto** en todos los realms — hay que verificarlo en:

```
Realm agent-poc → Clients → agente-ia → Settings → Capability config →
  ✅ Direct access grants: OFF (sigue off)
  ❌ Service accounts:   ON  (debe estar ON para client_credentials de fallback)
  ❌ Standard flow:      ON  (Auth Code + PKCE para flujo A)
  ❌ Device flow:        ON  (Device Code para flujo B)
```

Verificar también en **Advance Settings → OAuth 2.0 Compatibility**:
- `Grant Type` debe permitir `urn:ietf:params:oauth:grant-type:jwt-bearer` además de los
  3 flujos canónicos. En KC 24 hay que añadirlo manualmente en la pestaña
  `Fine grain OpenID Connect configuration` o vía Admin REST API
  (parámetro `attributes."oauth2.grant.type"=["...","urn:ietf:params:oauth:grant-type:jwt-bearer"]`).

### 2.2 Protocol Mappers para los nuevos claims custom

KC no conoce `dni_verified`, `dob_verified`, `identity_method` por defecto.
Hay que añadir 3 mappers en el cliente `agente-ia` (o en el scope, según preferencia):

| Mapper | Mapper Type | Token Claim Name | Claim JSON Type | Source |
|---|---|---|---|---|
| `dni_verified` | User Attribute | `dni_verified` | `boolean` | User Attribute `dni_verified` |
| `dob_verified` | User Attribute | `dob_verified` | `boolean` | User Attribute `dob_verified` |
| `identity_method` | User Attribute | `identity_method` | `String` | User Attribute `identity_method` |

Estos mappers traducen los atributos del usuario al access_token, pero los atributos
los rellena **el agente** en la identity-assertion. KC 24 (con `--features=preview` o
en 26+) puede extraer claims directamente de la JWT bearer assertion entrante y
mergearlos en el access_token de salida. **Sin ese feature**, hay que:

1. Configurar un **Script Mapper** (KC 24+ premium feature) o un **Protocol Mapper
   custom** vía SPI Java que extraiga los 3 claims de la assertion y los propague.
2. O **alternativa más simple**: que el agente rellene esos atributos en el usuario
   KC antes de pedir el token. El agente tiene permisos `manage-users` en el realm,
   así que puede hacer `PUT /admin/realms/agent-poc/users/{user_id}` con el body:
   ```json
   {
     "attributes": {
       "dni_verified": ["true"],
       "dob_verified": ["true"],
       "identity_method": ["dni+dob"]
     }
   }
   ```
   y luego los mappers de User Attribute los propagan al token automáticamente.

**Esta segunda vía es la que implementa la PoC actual** (ver §3.2 de `app.py`):
el agente escribe los atributos del usuario antes de pedir el token. Es menos elegante
que un SPI pero funciona en KC 24 stock y es trivial de portar a KC 26+.

### 2.3 ACR válido

El realm debe reconocer `acr=id-claim+push-biometric` como un valor de contexto
válido. KC 24 NO valida valores de ACR (los acepta como string arbitrario) pero
las **policies** que lo consuman deben declararlo en su `loa` o `auth_flow` config.
En la PoC actual el `acr` es **meramente informativo** — la API (Spring Boot) lo
loguea pero no lo enforza (a excepción de requerir `dni_verified=true` en scopes
sensibles).

---

## 3. Endpoints nuevos del agente

| Método | Path | Propósito | Auth |
|---|---|---|---|
| `POST` | `/agente/auth/identity` | Cliente envía DNI+DOB → agente crea challenge | `Bearer` client_token |
| `GET`  | `/agente/auth/identity/poll` | Cliente pregunta si push fue aprobado | `Bearer` client_token |
| `POST` | `/agente/auth/identity/push/{id}?biometric=true` | Mock del móvil que aprueba | ninguna (es el mock) |

Todos los tests están en `agent-python/tests/test_*.py` (52 tests, 100% passing
a 2026-07-08). Para ejecutar la suite:

```bash
cd /home/vhdez/desarrollos-hermes/agent-oauth-poc/agent-python
python3 -m pytest tests/ -v
```

### 3.1 Tabla de usuarios en `config.py`

La tabla `USERS` (líneas 81-99) tiene 3 entradas con DNI+DOB hasheados. Para
añadir un usuario nuevo:

```python
USERS["nombre"] = {
    "password_hash": "<bcrypt o pbkdf2>",
    "dni_hash": hashlib.sha256(b"DNI").hexdigest(),
    "dob_hash": hashlib.sha256(b"YYYY-MM-DD").hexdigest(),
    "name":     "Nombre Apellido",
    "email":    "user@example.com",
    "scopes":   ["calendar.read", "email.read"],
}
```

**IMPORTANTE**: en producción NUNCA se guardan DNI en plano. La PoC los hashea en
build-time para que la verificación sea `dni_input_hash == users[id].dni_hash`
constante y no permita leak por logs.

### 3.2 Flujo interno del agente

```python
# 1. Cliente POST /agente/auth/identity {user_id, dni, dob, scope}
# 2. verify_identity(user_id, dni, dob) -> True|False
# 3. Si False -> 401
# 4. Si True -> crear challenge PENDING_CHALLENGES[challenge_id] con:
#       - user_id, scope, identity_assertion (payload sin firmar)
#       - expires_at = now + 120s
# 5. Devolver challenge_id + verification_uri
# 6. (En paralelo) el móvil recibe push, hace POST /agente/auth/identity/push/{id}?biometric=true
# 7. Cliente hace GET /agente/auth/identity/poll?challenge_id=X&biometric_used=true
# 8. Agente:
#       a) Verifica challenge existe y no expirado
#       b) Verifica push_status == "approved" y biometric_used == True
#       c) Rellena atributos en KC: PUT /admin/realms/agent-poc/users/{id}
#       d) Firma identity_assertion JWT con AGENT_CLIENT_SECRET (HS256 PoC)
#       e) POST /realms/agent-poc/protocol/openid-connect/token con
#          grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer&assertion=...
#       f) Devuelve access_token al cliente
```

### 3.3 Pendiente: validación E2E con Keycloak real

A 2026-07-08 los **52 tests pasan en mockeado** (`httpx.AsyncClient` simulado) pero
**NO se ha validado contra Keycloak real**. Pasos para hacerlo manualmente:

1. Levantar el stack: `docker compose up -d --build` (en `/home/vhdez/desarrollos-hermes/agent-oauth-poc/`)
2. Verificar que el realm está provisionado: `KEYCLOAK_URL=http://localhost:8180 python3 scripts/create_realm.py`
3. Añadir los 3 mappers custom al cliente `agente-ia` (vía Admin UI o REST)
4. Ejecutar `python3 scripts/flow_c_e2e.py` (script que se añade en el Paso 8 del plan)
5. Verificar en logs de Keycloak: `[C/Identity] access_token emitido para user=ana`
6. Verificar que el token contiene `dni_verified=true, dob_verified=true, identity_method=dni+dob`

> **Nota**: el contenedor `agent-poc-agent-python` actualmente corriendo está
> basado en la imagen anterior al rebuild (2026-07-07 21:38). Para E2E real
> hay que `docker compose build agent-python && docker compose up -d agent-python`
> (pendiente de aprobación del usuario).

---

## 4. Migración desde v2-voice

Si tienes un PoC voice-first corriendo y quieres migrar:

### 4.1 Lo que NO cambia
- Cliente mock (webapp Auth Code + PKCE) → igual
- Spring Boot API → igual (los claims `voice_verified` no se leen, solo se loguean)
- Push broker (Keycloak authenticator) → igual
- Realm JSON (`realm-agent-poc.json`) → sin cambios estructurales

### 4.2 Lo que SÍ cambia

| Pieza | Acción |
|---|---|
| Tabla de usuarios en `config.py` | Añadir `dni_hash` y `dob_hash` a cada usuario (ver §3.1) |
| Protocol mappers en KC | Añadir 3 mappers `dni_verified`, `dob_verified`, `identity_method` (ver §2.2) |
| Diagrama HTML (`flowstudio.html`) | Ya actualizado (commit 8d9f909) |
| Variables de entorno del agente | Sin cambios (mismas vars que v2-voice) |
| Endpoint de envío de datos | Nuevo: `POST /agente/auth/identity` (sustituye al flujo de audio) |

### 4.3 Rollback

Si necesitas volver a v2-voice temporalmente:
1. `git checkout 8d9f909^ -- agent-python/ docs/html/static/flows.js docs/html/flowstudio.html`
2. Rebuild agente: `docker compose build agent-python && docker compose up -d agent-python`
3. **NO** borres los mappers de KC (son inocuos y no afectan al flujo v2-voice)

---

## 5. Tests cubiertos

| Test | Cobertura | Estado |
|---|---|---|
| `test_config.py` | `verify_identity()`, hash DNI+DOB, edge cases (None, vacío, espacios) | ✅ 12/12 |
| `test_oauth_client_identity.py` | `identity_exchange()` POST al IdP, manejo de errores | ✅ 4/4 |
| `test_sign_assertion.py` | `_sign_identity_assertion()` PyJWT HS256, validación temporal | ✅ 6/6 |
| `test_app_identity_endpoint.py` | `POST /agente/auth/identity` happy path + 401s | ✅ 10/10 |
| `test_app_identity_push_poll.py` | Push mock + polling + errores de red | ✅ 10/10 |
| `test_identity_flow_e2e.py` | Integración cliente → push → poll (mockeando IdP) | ✅ 4/4 |
| `test_flows_js_identity.py` | Diagrama HTML sin claims de voz | ✅ 6/6 |
| **Total** | | **52/52 ✅** |

---

## 6. Próximos pasos (TODO)

- [ ] Validar E2E contra Keycloak real (requiere rebuild del agente + reinicio, pendiente de aprobación)
- [ ] Migrar `_sign_identity_assertion` de HS256 a **RS256** (asimétrico) cuando el agente tenga keypair real
- [ ] Añadir Script Mapper en KC para extraer `dni_verified` directamente de la assertion entrante (en vez de escribir atributos en usuario)
- [ ] Implementar el endpoint `GET /agente/auth/identity/poll` con long-polling o SSE para evitar polling agresivo del cliente
- [ ] Internacionalizar mensajes de error (i18n)
- [ ] Rate-limiting en `/agente/auth/identity` para evitar brute force de DNI
