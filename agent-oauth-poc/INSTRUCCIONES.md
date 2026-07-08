# 🚀 PoC — Agente IA con OAuth/OIDC + CIBA

PoC local que demuestra un flujo **CIBA (Client-Initiated Backchannel Authentication)**
donde un agente IA actúa como cliente confidencial de Keycloak para invocar APIs
en nombre del usuario, mientras el usuario autoriza la acción desde otro canal
(`client-mock`).

---

## 1. Componentes

| Servicio           | Puerto host | Imagen / Build                  | Función                                            |
|--------------------|-------------|---------------------------------|----------------------------------------------------|
| `postgres`         | —           | `postgres:16-alpine`            | Base de datos de Keycloak                          |
| `keycloak`         | 8080        | `quay.io/keycloak/keycloak:24.0`| IdP con CIBA habilitado + realm `agent-poc` importado |
| `spring-boot-api`  | 9090        | `./spring-boot-api`             | API protegida (Resource Server JWT)                |
| `agent-python`     | 7000        | `./agent-python`                | Cliente confidencial OIDC + CIBA requester         |
| `client-mock`      | 3000        | `./client-mock`                 | UI simulada que aprueba/deniega el challenge CIBA  |

Todos los servicios comparten la red bridge **`agent-poc-net`** y se resuelven
entre sí por nombre (DNS interno de Docker).

---

## 2. Requisitos previos

* Docker Engine ≥ 24 y Docker Compose v2 (`docker compose version`)
* Puertos libres en el host: `3000`, `7000`, `8080`, `9090`
* El realm exportado debe estar en `./keycloak/realm/` (formato JSON de Keycloak)
* Cada subproyecto (`spring-boot-api/`, `agent-python/`, `client-mock/`) debe
  contener un `Dockerfile` propio

> ⚠️ **Las carpetas de build y `keycloak/realm/` aún están vacías.**
> Antes de levantar el stack hay que poblar el `Dockerfile` correspondiente de
> cada servicio y exportar el realm desde una instalación de Keycloak
> (o generarlo a mano). Sin eso, `docker compose up` fallará al construir /
> importar el realm.

---

## 3. Levantar el stack

```bash
cd /home/vhdez/desarrollos-hermes/agent-oauth-poc

# Construir imágenes y arrancar en background
docker compose up -d --build

# Seguir logs (Ctrl+C para salir, los contenedores siguen corriendo)
docker compose logs -f
```

Orden de arranque gracias al `healthcheck` de postgres y los `depends_on`:

```
postgres (healthy) → keycloak → spring-boot-api / agent-python → client-mock
```

### Healthcheck manual

```bash
# Postgres
docker compose exec postgres pg_isready -U keycloak -d keycloak

# Keycloak (tarda ~20-40 s en estar listo la primera vez)
curl -fsS http://localhost:8080/health/ready | jq .

# Spring Boot
curl -fsS http://localhost:9090/actuator/health | jq .

# Agent Python
curl -fsS http://localhost:7000/health | jq .

# Client mock
curl -fsS http://localhost:3000/health | jq .
```

---

## 4. Validar la configuración

Sólo parsear (no construye ni arranca):

```bash
docker compose config        # exit 0 si todo OK
docker compose config -q     # silencioso, sólo exit code
```

Ver configuración efectiva con paths resueltos:

```bash
docker compose config | less
```

---

## 5. Acceso a Keycloak

* **Admin Console**: http://localhost:8080/admin
  * usuario: `admin`
  * contraseña: `admin`
* **Realm**: `agent-poc` (importado automáticamente desde
  `./keycloak/realm/agent-poc-realm.json` por el flag `--import-realm`)
* **Issuer**: `http://keycloak:8080/realms/agent-poc`
  (desde fuera del host usar `http://localhost:8080/realms/agent-poc`)

> La primera vez, abre `http://localhost:8080` — si ves el *Welcome page*
> significa que Keycloak está listo.

---

## 6. Usuarios demo (a crear en el realm)

El realm no incluye usuarios por seguridad. Desde Admin Console:

| Usuario | Contraseña | Email            | Roles / notas                  |
|---------|------------|------------------|--------------------------------|
| `ana`   | `ana`      | ana@example.com  | `user`, `payments`             |
| `luis`  | `luis`     | luis@example.com | `user`, `payments`             |
| `marta` | `marta`    | marta@example.com| `user`, readonly               |

Pasos:
1. **Realm: agent-poc** → **Users** → **Add user**
2. Username + Email verified ON → **Save**
3. **Credentials** tab → **Set password** (desmarcar *Temporary*)

---

## 7. Cliente OIDC del agente

`agent-python` actúa como **confidential client**:

* `client_id`: `agente-ia`
* `client_secret`: `secret-del-agente`
* `auth_method`: `client_secret_basic`
* **Standard flow**: OFF (es una IA, no usa redirect)
* **CIBA grant**: ON, con `auth_req_id` mode

Estos valores vienen por variables de entorno (`AGENT_CLIENT_ID`,
`AGENT_CLIENT_SECRET`) en `docker-compose.yml`.

---

## 8. Flujo CIBA de extremo a extremo

```
┌──────────────┐          ┌──────────────┐        ┌──────────────┐
│ client-mock  │ ──POST──▶│ agent-python │ ──────▶│   Keycloak   │
│ (user @web)  │          │ (IA cliente) │  BC    │   (IdP)      │
└──────┬───────┘          └──────┬───────┘        └──────┬───────┘
       │ ▲                       │                       │
       │ │                       │                       ▼
       │ │                       │              push notification
       │ │                       ▼                       │
       │ │              ┌────────────────┐                │
       │ └──────────────│  Spring Boot   │◀── access ─────┘
       │     401/200    │   API (RBAC)   │
       └──────final──── └────────────────┘
```

1. **client-mock** recibe un prompt del usuario ("págale 100 € a proveedor X")
   y llama a **agent-python** `POST /agent/run` con un `binding_message`
   (ej. `pago-123`) y un canal de notificación (`client-mock`).
2. **agent-python** arranca el **CIBA grant** contra Keycloak con
   `client_secret_basic`, scope `openid payments`, login_hint_token apuntando
   al usuario (`ana`) y `binding_message`.
3. Keycloak emite `auth_req_id` y manda el challenge al canal configurado
   (en este PoC, el `client-mock`).
4. **client-mock** muestra "ana, ¿autorizas pago-123 por 100 €?" y publica
   el resultado (allow/deny) vía endpoint interno de Keycloak.
5. **agent-python** hace *polling* del `token_endpoint` con el `auth_req_id`
   hasta recibir `access_token` (con `payment:write`) y `id_token`.
6. Con ese token llama a `spring-boot-api` `POST /payments` que valida JWT
   contra el issuer `http://keycloak:8080/realms/agent-poc`.
7. Resultado vuelve al `client-mock`.

---

## 9. Comandos útiles del día a día

```bash
# Estado
docker compose ps
docker compose top

# Logs
docker compose logs -f keycloak
docker compose logs -f agent-python

# Reinicio selectivo
docker compose restart keycloak
docker compose up -d --force-recreate spring-boot-api

# Parar todo (conservando el volumen de postgres)
docker compose down

# Parar y BORRAR el volumen de postgres (reset total)
docker compose down -v

# Ejecutar comandos dentro de un contenedor
docker compose exec keycloak /opt/keycloak/bin/kcadm.sh config ...
docker compose exec postgres psql -U keycloak -d keycloak

# Reconstruir una sola imagen
docker compose build spring-boot-api

# Validar sin tocar el demonio
docker compose config -q && echo "OK"
```

---

## 10. Troubleshooting

| Síntoma                                                | Causa probable                                         | Solución                                            |
|--------------------------------------------------------|--------------------------------------------------------|-----------------------------------------------------|
| `keycloak` reinicia en bucle                           | `postgres` no healthy                                  | Esperar 10-30 s a que pg_isready pase                |
| `agent-python` no puede resolver `keycloak`            | Network mal declarado                                  | `docker compose config \| grep networks`             |
| `403 Forbidden` al llamar a `spring-boot-api`          | Rol `payments` falta o scope insuficiente              | Verificar role mapping en el realm                   |
| `invalid_client` en CIBA                               | `agente-ia` no es confidential o no tiene CIBA enabled | Revisar *Client capabilities* en admin console      |
| Realm no aparece tras login                            | JSON mal situado                                       | El archivo debe ir en `/opt/keycloak/data/import/`  |
| `JAVA_TOOL_OPTIONS=...ciba` ignorado                   | Compose lo pisa                                        | Verificar `docker compose config`                   |

> **Reset limpio**:
> `docker compose down -v && docker compose up -d --build`

---

## 11. Producción (nota)

* Sustituir `spring-boot-api` por **Apigee** o un API Gateway equivalente que
  aplique políticas Apigee (verify API key, OAuth, SpikeArrest, Quota).
* `client-mock` se sustituye por la **app nativa** real que recibe el push.
* Cambiar credenciales del admin y de la BD, montar secretos vía
  `docker secrets` / vault, habilitar TLS en Keycloak, mover la BD a un
  PostgreSQL gestionado, y configurar realm de **producción** (no
  `start-dev`).
* El realm `agent-poc` debe versionarse **sin** secretos embebidos.
