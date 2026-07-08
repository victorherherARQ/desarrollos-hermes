# SETUP · agent-oauth-poc

> Guía paso-a-paso reproducible para levantar la PoC **`agent-oauth-poc`** desde cero en una máquina nueva (WSL2 / Linux / macOS) y ejecutar los **5 tests end-to-end** que demuestran el patrón "agente IA con OAuth 2.0 + CIBA".
>
> Tiempo total estimado: **~10 min** (de los cuales ~3 min son build de Spring Boot la primera vez).

---

## 1. TL;DR (30 segundos)

```bash
# 1) Clonar el repo
git clone https://github.com/victorherherARQ/agent-oauth-poc.git
cd agent-oauth-poc

# 2) Arrancar los 5 contenedores (Postgres, Keycloak, Spring API, Agente Python, Client Mock)
docker compose up -d --build

# 3) Esperar a que Keycloak termine de arrancar y aceptar conexiones
until curl -sf http://localhost:8180/realms/master/.well-known/openid-configuration > /dev/null; do
  sleep 3; echo "esperando Keycloak..."; done && echo "Keycloak ready"

# 4) Provisionar el realm "agent-poc" con 3 usuarios, 4 custom scopes y el cliente agente-ia
python3 scripts/create_realm.py --reset

# 5) Probar el flujo completo (Ana → calendario)
curl -sX POST http://localhost:7000/agente/call \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"ana","request":"léeme mi calendario","scope":"calendar.read","action_type":"calendar"}' | jq .

# 6) Health-check rápido
curl -s http://localhost:7000/agente/health | jq .
# → {"status":"UP"}
```

Si los 6 pasos anteriores pasan, **la PoC está funcionando**. El resto del documento solo detalla cómo y por qué.

---

## 2. Arquitectura en 30 segundos

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                  USUARIO                                     │
│                              (Ana / Luis / Marta)                            │
└──────────────────────────────────────────────────────────────────────────────┘
                                     ▲ ② push / approve
                                     │
┌───────────────────────┐    ① peticion de agente    ┌────────────────────────┐
│   Client Mock (UI)    │ ◀────────────────────────▶│   Agente Python (IA)   │
│   :3000 (Node 20)     │   "léeme mi calendario"   │   :7000 (FastAPI)      │
│   ciient-mock/        │                           │   agent-python/        │
└───────────────────────┘                           └──────┬─────────────────┘
                                                          │ ③ ROPC + JWT
                                                          ▼
┌───────────────────────┐    ④ access_token JWT     ┌────────────────────────┐
│   Spring Boot API     │ ◀────────────────────────│   Keycloak 24 (IdP)    │
│   :9090 (Java 21)     │   GET /api/calendar/...   │   :8180 (Quarkus)      │
│   spring-boot-api/    │                           │   + CIBA habilitado    │
└───────────────────────┘                           └──────┬─────────────────┘
       ▲                                                  │ persiste realms,
       │ usa JDBC a                                    ⑤  usuarios, scopes
       │                                                  ▼
┌───────────────────────┐                           ┌────────────────────────┐
│   PostgreSQL 16       │ ◀─────────────────────────│   (volumen docker)     │
│   (interno, sin       │                           │   postgres-data        │
│    puerto expuesto)   │                           │                        │
└───────────────────────┘                           └────────────────────────┘
```

### Mapeo de puertos host → servicio

| Puerto host | Servicio          | Propósito                                              | URL                                                              |
|-------------|-------------------|--------------------------------------------------------|------------------------------------------------------------------|
| **3000**    | `client-mock`     | UI simulada del cliente iniciador de la transacción    | http://localhost:3000                                            |
| **7000**    | `agent-python`    | API del agente IA (entrypoint principal)               | http://localhost:7000                                            |
| **8180**    | `keycloak`        | Consola admin + endpoints OIDC/CIBA                    | http://localhost:8180/admin (admin / admin)                      |
| **9090**    | `spring-boot-api` | Recurso protegido (Resource Server)                    | http://localhost:9090/api/calendar/events, /api/email/send       |
| **5432**    | _no expuesto_     | Postgres vive solo dentro de la red `agent-poc-net`    | —                                                                |

---

## 3. Requisitos previos

| Requisito                 | Versión mínima          | Cómo verificar                          |
|---------------------------|-------------------------|------------------------------------------|
| WSL2 / Linux / macOS      | Ubuntu 22.04 o similar  | `uname -a`                               |
| Docker Engine o Docker Desktop | 24.0+ con `compose` v2 | `docker --version && docker compose version` |
| Python (host)             | 3.11+                   | `python3 --version`                      |
| `curl`                    | cualquier               | `curl --version`                         |
| `jq`                      | cualquier               | `jq --version`                           |
| RAM libre                 | 8 GB                    | `free -h`                                |
| Disco libre               | 10 GB                   | `df -h ~`                                |

### Verificar puertos libres

```bash
for p in 3000 7000 8180 9090; do
  (echo > /dev/tcp/127.0.0.1/$p) 2>/dev/null \
    && echo "⚠️  Puerto $p OCUPADO" \
    || echo "✅  Puerto $p libre"
done
```

Si algún puerto está ocupado:

- Edita `docker-compose.yml` y cambia `HOST_EXTERNO:PUERTO_INTERNO` (ej. `"8280:8080"` para Keycloak).
- Actualiza las URLs en este documento (paso 2 y siguientes).

### Instalar `jq`

```bash
# Ubuntu / Debian (incluido WSL2)
sudo apt-get update && sudo apt-get install -y jq

# macOS
brew install jq
```

### (Opcional) Clonar con SSH

```bash
# Si vas a clonar con SSH en vez de HTTPS, asegúrate de tener la key pública en GitHub
ssh -T git@github.com
```

---

## 4. Instalación paso a paso

### Paso 1 · Clonar el repositorio

```bash
git clone https://github.com/victorherherARQ/agent-oauth-poc.git
cd agent-oauth-poc
```

Comprobar que estás en la raíz del proyecto:

```bash
ls -F
# debe verse:  agent-python/  client-mock/  docker-compose.yml  docs/  INSTRUCCIONES.md
#               keycloak/  README.md  scripts/  spring-boot-api/
```

### Paso 2 · Arrancar los 5 contenedores

```bash
docker compose up -d --build
```

- **Primera ejecución**: ~3 min (descarga imágenes + compilación Maven de Spring Boot).
- **Siguientes ejecuciones**: ~15-25 s (reutiliza caché de capas y volumen de Postgres).

Verificar que los 5 contenedores están "running":

```bash
docker compose ps
```

Salida esperada (5 servicios, columna `State` todos `running` o `Up`):

```
NAME                          STATUS
agent-poc-postgres            Up
agent-poc-keycloak            Up
agent-poc-spring-boot-api     Up
agent-poc-agent-python        Up
agent-poc-client-mock         Up
```

### Paso 3 · Esperar a que Keycloak arranque

Keycloak necesita ~45-90 s en arrancar importando el driver JDBC de Postgres y arrancando el broker JPA. Lanza este loop que **reintenta hasta que responda**:

```bash
until curl -sf http://localhost:8180/realms/master/.well-known/openid-configuration > /dev/null; do
  printf '.'; sleep 3
done
echo
echo "✅ Keycloak ready"
```

Si se eterniza (>2 min), mira los logs:

```bash
docker logs agent-poc-keycloak --tail 30
```

### Paso 4 · Crear el realm y todo lo necesario

```bash
python3 scripts/create_realm.py --reset
```

El `--reset` borra el realm `agent-poc` si existía y lo recrea desde cero. **Es seguro ejecutarlo varias veces**.

Para actualizar sin destruir (modo idempotente, recomendado para cambios triviales):

```bash
python3 scripts/create_realm.py     # sin --reset
```

Output esperado (7 pasos ✅):

```
[1/7] Realm 'agent-poc'
  ✅ ...
[2/7] Realm capabilities (CIBA, ...)
  ✅ ...
[3/7] Client 'agente-ia'
  ✅ ...
[4/7] Client 'spring-boot-api'
  ✅ ...
[5/7] Custom scopes (calendar.read, calendar.write, email.send, email.modify)
  ✅ ...
[6/7] Audience mapper para API Spring Boot
  ✅ ...
[7/7] Usuarios demo (ana, luis, marta)
  ✅ ...
```

### Paso 5 · Verificación rápida

```bash
# Health del agente
curl -s http://localhost:7000/agente/health | jq .
# → {"status":"UP"}

# Health del Keycloak
curl -s http://localhost:8180/health/ready | jq .
# → {"status":"UP"}

# Catálogo OIDC del realm recién creado
curl -s http://localhost:8180/realms/agent-poc/.well-known/openid-configuration | jq '.issuer, .grant_types_supported, .authorization_endpoint'
```

Si los tres responden, **el entorno está completamente operativo**.

---

## 5. Tests end-to-end (los 5 que pasan)

Todos los tests llaman a `POST http://localhost:7000/agente/call` con el mismo payload JSON. El agente:

1. Resuelve el `user_id` contra el mapa interno (`agent-python/config.py`) — **no** contra Keycloak.
2. Pide un `access_token` a Keycloak con `grant_type=password` (ROPC) usando las credenciales del usuario.
3. Llama al endpoint de la Spring Boot API correspondiente al `scope`.
4. Devuelve la respuesta del recurso protegido al cliente.

### Test 1 · Ana lee su calendario (`scope: calendar.read`)

```bash
curl -sX POST http://localhost:7000/agente/call \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"ana","request":"léeme mi calendario","scope":"calendar.read","action_type":"calendar"}' | jq .
```

**Salida esperada** (Ana tiene 2 eventos):

```json
{
  "ok": true,
  "user": "Ana García",
  "scope": "calendar.read",
  "result": {
    "events": [
      { "title": "Daily con Vicedo",          "when": "2026-07-08T09:00:00Z" },
      { "title": "Review PR #482",            "when": "2026-07-08T16:30:00Z" }
    ]
  }
}
```

### Test 2 · Luis lee su calendario

```bash
curl -sX POST http://localhost:7000/agente/call \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"luis","request":"qué tengo hoy","scope":"calendar.read","action_type":"calendar"}' | jq .
```

**Salida esperada** (Luis tiene 1 evento distinto):

```json
{
  "ok": true,
  "user": "Luis Pérez",
  "scope": "calendar.read",
  "result": {
    "events": [
      { "title": "Standup equipo Hermes",     "when": "2026-07-08T08:30:00Z" }
    ]
  }
}
```

### Test 3 · Marta lee su calendario

```bash
curl -sX POST http://localhost:7000/agente/call \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"marta","request":"muestra agenda","scope":"calendar.read","action_type":"calendar"}' | jq .
```

**Salida esperada** (Marta tiene 1 evento):

```json
{
  "ok": true,
  "user": "Marta López",
  "scope": "calendar.read",
  "result": {
    "events": [
      { "title": "Dentista - Dra Suárez",     "when": "2026-07-08T17:00:00Z" }
    ]
  }
}
```

> **Nota clave**: las tres respuestas son distintas porque cada usuario tiene sus propios eventos en la base de datos mock del Spring Boot. Esto demuestra que el `user_id` viaja en la petición Y se preserva hasta el recurso protegido (no solo el `sub` del JWT sino el `X-User-Id`/claim `user_id`).

### Test 4 · Ana envía un email (`scope: email.send`)

```bash
curl -sX POST http://localhost:7000/agente/call \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"ana","request":"manda un mail al equipo","scope":"email.send","action_type":"Release v0.3 publicada, screenshots adjuntos"}' | jq .
```

**Salida esperada**:

```json
{
  "ok": true,
  "user": "Ana García",
  "scope": "email.send",
  "result": {
    "sent": true,
    "to": "ana@example.com",
    "subject": "Release v0.3 publicada, screenshots adjuntos",
    "message_id": "msg-<uuid>"
  }
}
```

### Test 5 · Luis envía un email (`scope: email.send`)

```bash
curl -sX POST http://localhost:7000/agente/call \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"luis","request":"avisa a desarrollo","scope":"email.send","action_type":"Build verde en CI, podemos mergear"}' | jq .
```

**Salida esperada**:

```json
{
  "ok": true,
  "user": "Luis Pérez",
  "scope": "email.send",
  "result": {
    "sent": true,
    "to": "luis@example.com",
    "subject": "Build verde en CI, podemos mergear",
    "message_id": "msg-<uuid>"
  }
}
```

### Test negativo · Token sin scope → 401/403

Para verificar que Spring Boot **realmente** valida el `scope` y no solo la firma del JWT, primero conseguimos un token con un scope distinto y luego llamamos al endpoint protegido directamente.

```bash
# 1) Conseguir un token SIN scope calendar.read (usando email.send en su lugar)
# 1.a) Definir el password de Ana (el mismo que usa el agente internamente — ver config.py)
ANA_PASS=$ANA_PASS  # <-- reemplaza por la contraseña real del usuario 'ana'

# 1.b) Conseguir un token SIN scope calendar.read (usando email.send en su lugar)
TOK=$(curl -sX POST http://localhost:8180/realms/agent-poc/protocol/openid-connect/token \
    -d 'grant_type=password' \
    -d 'client_id=agente-ia' \
    -d 'client_secret=secret-del-agente' \
    -d 'username=ana' \
    -d "password=$ANA_PASS" \
    -d 'scope=email.send' \
  | jq -r .access_token)

# 2) Llamar a /api/calendar/events con ese token → debe fallar (401 o 403)
curl -i "http://localhost:9090/api/calendar/events?user_id=ana" \
     -H "Authorization: Bearer $TOK"
```

**Salida esperada**:

```
HTTP/1.1 403       ← Preferred (Forbidden por scope insuficiente)
o bien
HTTP/1.1 401       ← Spring Security 6.x por defecto (sin WWW-Authenticate)
```

> ⚠️ Si el código de estado es `403` estás ante el comportamiento Spring Security "estándar". Si es `401`, ver *Troubleshooting §8*.

---

## 6. Cómo ver logs y debug

### Logs por servicio

```bash
docker logs agent-poc-keycloak          # Keycloak 24 (Quarkus)
docker logs agent-poc-spring-boot-api    # API Spring Boot
docker logs agent-poc-agent-python       # Agente IA (FastAPI)
docker logs agent-poc-client-mock        # UI móvil mock (Node 20)
docker logs agent-poc-postgres           # Postgres 16
```

### Todos los logs en una sola vista

```bash
docker compose logs -f --tail 50
```

Para ver los logs de un solo servicio en streaming:

```bash
docker compose logs -f spring-boot-api
docker compose logs -f agent-python
```

### Entrar en un contenedor

```bash
docker exec -it agent-poc-keycloak /bin/bash
docker exec -it agent-poc-spring-boot-api /bin/sh
docker exec -it agent-poc-agent-python /bin/sh
docker exec -it agent-poc-postgres psql -U keycloak -d keycloak
```

### Filtros útiles

```bash
# Solo ERROR / WARN
docker logs agent-poc-keycloak 2>&1 | grep -iE "error|warn|exception"

# Solo requests HTTP del agente
docker logs agent-poc-agent-python 2>&1 | grep -E "POST|GET"

# requests HTTP de Spring Boot
docker logs agent-poc-spring-boot-api 2>&1 | grep -E "INFO.*RequestMapping"
```

---

## 7. Operaciones frecuentes (cheatsheet)

### Parar todo (conservando datos)

```bash
docker compose down
```

### Parar y borrar TODO (incluye DB de Keycloak)

```bash
docker compose down -v
```

> Usar cuando el realm está corrupto, los `CUSTOM_SCOPES` cambiaron, o el contenedor Postgres da errores raros.

### Reconstruir un solo servicio

```bash
docker compose build spring-boot-api
docker compose up -d spring-boot-api
```

Misma forma con `agent-python`, `keycloak`, `client-mock`.

### Reiniciar Keycloak sin perder datos

```bash
docker compose restart keycloak
```

Y luego re-esperar a que responda:

```bash
until curl -sf http://localhost:8180/realms/master/.well-known/openid-configuration > /dev/null; do sleep 3; done
echo "ready"
```

### Borrar y recrear solo el realm (sin tocar contenedores)

```bash
python3 scripts/create_realm.py --reset
```

### Obtener un token de admin de Keycloak desde el host

```bash
# 1) Conseguir token de admin (admin/admin es la cuenta admin del realm 'master')
ADMIN_TOK=$(curl -sX POST http://localhost:8180/realms/master/protocol/openid-connect/token \
    -d 'grant_type=password' \
    -d 'client_id=admin-cli' \
    -d 'username=admin' \
    -d 'password=admin' | jq -r .access_token)

# 2) Inspeccionar realms
curl -sH "Authorization: Bearer $ADMIN_TOK" \
     http://localhost:8180/admin/realms | jq '.[].realm'

# 3) Inspeccionar usuarios del realm agent-poc
curl -sH "Authorization: Bearer $ADMIN_TOK" \
     http://localhost:8180/admin/realms/agent-poc/users | jq '[.[] | {username, email}]'
```

### Inspeccionar un JWT (sin librerías)

```bash
# Reusa $TOK del bloque anterior (admin) o del bloque del Test negativo (ana)
echo "$ADMIN_TOK" | cut -d'.' -f2 | base64 -d 2>/dev/null | jq .
# → header y payload del access_token (claims: scope, aud, sub, ...)
```

---

## 8. Troubleshooting (5 problemas típicos con solución)

### 8.1 · "Puerto 8180 ocupado" (y similares)

**Síntoma**: `Error response from daemon: Ports are not available: ...`

**Causa**: otro proceso (structurizr, otro Keycloak, etc.) ocupa el puerto del host.

**Solución**: editar `docker-compose.yml` y cambiar solo la parte izquierda (host) de `HOST:CONT`:

```yaml
# antes
- "8180:8080"      # Keycloak
- "9090:9090"      # Spring Boot
- "7000:7000"      # Agente

# después (ejemplo)
- "8280:8080"
- "9190:9090"
- "7100:7000"
```

Luego **actualizar todos los comandos de este documento** que usan los puertos cambiados.

### 8.2 · "Keycloak no responde tras 60-90 s"

**Síntoma**: el loop del paso 3 nunca termina.

**Diagnóstico**:

```bash
docker logs agent-poc-keycloak --tail 50
```

- Si ves `Failed to determine a suitable driver class` o `Connection refused: postgres:5432` → el contenedor `postgres` aún no está listo (raro, el `depends_on: healthy` debería cubrirlo, pero pasa si la máquina está muy cargada). Esperar más.
- Si ves `ERROR: invalid username/password` repetido → bumpear memoria. Solución: `docker compose down -v && docker compose up -d --build`.
- Si no ves **nada** útil: `docker compose logs keycloak | head -100`.

**Solución nuclear** (desde cero, perdiendo la DB de Keycloak):

```bash
docker compose down -v
docker compose up -d --build
```

### 8.3 · "invalid_scope al pedir calendar.read"

**Síntoma**: `{"ok": false, "error": "...invalid_scope..."}` en respuesta del agente.

**Causa documentada**: bug conocido en Keycloak 24 — al crear un custom scope, `include.in.token.scope` debe ir en la **forma dotted canónica** (`include.in.token.scope=true`), no en camelCase. El script `create_realm.py` ya lo aplica correctamente. Si reaparece, casi siempre significa que el realm se modificó a mano por la consola admin y se "ensució".

**Solución**:

```bash
python3 scripts/create_realm.py --reset
```

Si persiste tras el reset, ver `docs/POOL.md §5` para el diagnóstico paso a paso.

### 8.4 · "Spring da 401 en lugar de 403"

**Síntoma**: el *Test negativo* (§5) devuelve `HTTP/1.1 401` en vez de `403`.

**Explicación**: es **comportamiento estándar** de Spring Security 6.x cuando no hay un `AuthenticationEntryPoint` configurado que añada `WWW-Authenticate`. Ver [Spring Security #13543](https://github.com/spring-projects/spring-security/issues/13543).

**No es un bug**, pero si necesitas `403` siempre:

```java
// spring-boot-api/src/main/java/.../SecurityConfig.java
http.exceptionHandling(eh -> eh
    .authenticationEntryPoint((req, res, ex) ->
        res.setStatus(HttpServletResponse.SC_UNAUTHORIZED))
    .accessDeniedHandler((req, res, ex) ->
        res.setStatus(HttpServletResponse.SC_FORBIDDEN)));
```

### 8.5 · "El agente no encuentra el usuario"

**Síntoma**: `{"ok": false, "error": "user_id 'pepe' no encontrado en el mapa local"}`.

**Causa**: solo `ana`, `luis` y `marta` están registrados en `agent-python/config.py`. La PoC no consulta el directorio de Keycloak.

**Solución A · usar uno existente**:

```bash
# cambiar 'pepe' por uno de:
#   ana / luis / marta
```

**Solución B · añadir un cuarto usuario** (ver §9).

---

## 9. Cómo personalizar / extender

### Añadir un nuevo scope custom

1. Editar `scripts/create_realm.py` línea ~37 (`CUSTOM_SCOPES`):
   ```python
   CUSTOM_SCOPES = ["calendar.read", "calendar.write", "email.send", "email.modify", "drive.read"]
   ```
2. Añadir la rama de dispatch en `agent-python/app.py` línea ~110:
   ```python
   elif req.scope == "drive.read":
       r = httpx.get(f"{API_BASE_URL}/api/drive/files", headers=headers, params={"user_id": user_id})
   ```
3. Añadir el endpoint en Spring Boot (`spring-boot-api/.../DriveController.java`).
4. Reaplicar el realm:
   ```bash
   python3 scripts/create_realm.py --reset
   docker compose build spring-boot-api agent-python
   docker compose up -d spring-boot-api agent-python
   ```

### Cambiar la contraseña de un usuario

**Opción A** (recomendada): re-ejecutar el script con `--reset`:

```bash
# editar DEMO_USERS en scripts/create_realm.py (incluye nuevo password)
python3 scripts/create_realm.py --reset
```

**Opción B** (cambiar en runtime, sin reset):

```bash
ADMIN_TOK=$ADMIN_TOK ... # ver §7
curl -sX PUT http://localhost:8180/admin/realms/agent-poc/users/<user-uuid>/reset-password \
  -H "Authorization: Bearer $ADMIN_TOK" \
  -H "Content-Type: application/json" \
  -d '{"type":"password","value":"nueva-pass","temporary":false}'
```

Y **además** actualizar `agent-python/config.py` y reconstruir el contenedor del agente.

### Cambiar el puerto del agente (7000 → otro)

Hay que tocar **tres sitios**:

```bash
# 1) agent-python/Dockerfile        → EXPOSE 8000
# 2) docker-compose.yml              → "8000:8000"
# 3) scripts/create_realm.py         → AGENT_CLIENT_SECRET (no cambia)
```

Después:

```bash
docker compose build agent-python
docker compose up -d agent-python
```

### Apuntar el agente a otra API (`API_BASE_URL`)

```bash
# agent-python/config.py
API_BASE_URL = "http://mi-api-prod:8080"

docker compose build agent-python
docker compose up -d agent-python
```

> Cuidado: la nueva API debe validar `iss == http://<keycloak-host>/realms/agent-poc` o Spring Boot rechazará el token.

---

## 10. Referencias

| Documento                                                         | Para qué sirve                                              |
|-------------------------------------------------------------------|-------------------------------------------------------------|
| [`README.md`](../README.md)                                       | Visión general del proyecto (qué, por qué, cómo).            |
| [`INSTRUCCIONES.md`](../INSTRUCCIONES.md)                         | Brief original de la PoC, objetivos de negocio.             |
| [`docs/POOL.md`](./POOL.md)                                       | Decisiones técnicas, bugs conocidos y workarounds (incluye el §5 sobre `invalid_scope`). |
| [`docs/ESTUDIO_COMPARATIVO.md`](./ESTUDIO_COMPARATIVO.md)         | Trade-offs ROPC vs CC vs CIBA, OAuth client-credentials vs token-exchange. |
| Keycloak 24 docs · https://www.keycloak.org/docs/24.0.5/          | Manual de Keycloak (admin REST, clients, scopes, CIBA).     |
| RFC 6749 · https://www.rfc-editor.org/rfc/rfc6749                 | OAuth 2.0 Framework (roles, grants, flows).                 |
| RFC 7523 · https://www.rfc-editor.org/rfc/rfc7523                 | JWT Bearer Client Authentication.                            |
| RFC 8693 · https://www.rfc-editor.org/rfc/rfc8693                 | OAuth 2.0 Token Exchange (lo que NO usamos en esta PoC).     |
| OIDC Core · https://openid.net/specs/openid-connect-core-1_0.html | OpenID Connect Core (claims, ID token, UserInfo).            |
| OIDC CIBA · https://openid.net/specs/openid-connect-ciba-1_0.html | Client Initiated Backchannel Authentication (la pieza clave habilitada con `-Dkeycloak.profile.feature.ciba=enabled`). |

---

<p align="center">
  <sub>Victor H. · 2026 · Documento vivo · PRs bienvenidos a <code>docs/SETUP.md</code></sub>
</p>
