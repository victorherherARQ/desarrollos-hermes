---
fecha_creada: 2026-08-03
fecha_avanzada: 2026-08-07
prioridad: alta
persona: Victor
proyecto: agent-oauth-poc
fecha_limite: ""
tags: [tarea/en-curso, prioridad/alta, area/trabajo]
---

# Completar desarrollo CIBA con Keycloak (FASE 1/5)

> **✅ Avance 2026-08-07**: ADR-001 publicado, Resource Server migrado, skill generalizada. Detalle completo en [`actuaciones/2026-08-07-ciba-consolidacion-fase-1.md`](../actuaciones/2026-08-07-ciba-consolidacion-fase-1.md).
>
> **Bloqueo actual**: `/home/vhdez/desarrollos-hermes/agent-oauth-poc/spring-boot-api/target/` es root-owned. Necesito sudo o que Víctor lo arregle para Fase 2 (docker E2E).

## 📊 Estado de las 5 fases

| Fase | Descripción | Estado | Commit |
|------|-------------|--------|--------|
| 0 | ADR consolidación | ✅ | `833c72c` |
| 1 | Migrar Resource Server | ✅ | `b58baff` |
| 2 | Validar E2E con docker | ⏸️ Bloqueado | — |
| 3 | Generalizar skill `oauth-flow-html` | ✅ | `0b4b03d` |
| 4 | Eliminar `ciba-callagent/` | ⏸️ Pospuesto | — |

## 🔑 Decisiones Víctor 2026-08-07

1. ✅ **Consolidar CIBA en `agent-oauth-poc/`** (revierte parcialmente v2)
2. ✅ **Skill `oauth-flow-html`**: restaurar + generalizar para opencode
3. ✅ **`poll` y `ping` mode**: ambos, documentados
4. ⏸️ **`ciba-callagent/` se queda donde está** hasta validar
5. ✅ **Keycloak 26.6+** como IdP objetivo

## Estado real del código

### `agent-oauth-poc/` (proyecto asignado originalmente)

- ❌ 0 menciones a CIBA en código
- Implementa: Auth Code + PKCE, Device Code, JWT Bearer (OBO)
- README.md línea 354: *"Ya NO usamos: CIBA (eliminado de la PoC por incompatibilidad con B2C)"*

### `ciba-callagent/` (el verdadero proyecto CIBA)

- ✅ Spring Boot 3.3.4, 2 microservicios Maven, 17 archivos `.java`
- ✅ Docker Compose (3 servicios), realm JSON, HTML viewer standalone (1587 líneas)
- ⚠️ **`target/classes/` solo contiene `application.yml`** — **necesita `mvn package`**
- ❌ **Nunca fue validado end-to-end con Keycloak real**

**Servicios**:
| Servicio | Puerto | Función |
|----------|--------|---------|
| keycloak | 8181 | Keycloak 26.6 con realm `ciba-realm` |
| ciba-oauth2-client | 8081 | CIBA Client (Hermes llama aquí) |
| ciba-resource-server | 8082 | Resource Server con CTI replay prevention |

**Credenciales test** (hardcodeadas en repo):
| Recurso | Valor |
|---------|-------|
| KC admin | `admin` / `admin` |
| Test user | `testuser` / `testuser` |
| CIBA client | `ciba-agent` / `ciba-agent-secret` |

## Estructura de `ciba-callagent/`

```
ciba-callagent/
├── ciba-oauth2-client/      :8081
│   ├── controller/
│   │   ├── AgentController.java          (POST /agent/request, GET /agent/status, POST /agent/execute)
│   │   ├── CibaClientController.java     (POST /ciba/auth-request, POST /ciba/poll/{id})
│   │   └── PingCallbackController.java   (POST /ciba/ping-callback — modo ping)
│   ├── service/
│   │   ├── CibaClientService.java        (WebClient → Keycloak authreq + token poll)
│   │   └── AgentOrchestrator.java        (state machine: PENDING → APPROVED → COMPLETED)
│   └── config/                            (CibaProperties, SecurityConfig, AgentApiKeyFilter)
├── ciba-resource-server/     :8082
│   ├── security/
│   │   ├── CibaTokenValidator.java       (CTI replay + auth_req_id + scope)
│   │   └── CibaJwtAuthenticationConverter.java
│   ├── config/
│   │   └── CtiReplayCache.java           (Caffeine, 24h TTL, max 10k entries)
│   └── controller/                        (Calendar, Email, User)
├── keycloak/
│   ├── ciba-realm-realm.json             (IMPORTANTE: nombre con sufijo `-realm`)
│   └── import-realm.sh
├── docker-compose.yml                     (3 servicios)
├── README.md                              (9.0 KB)
├── TESTING.md                             (7.1 KB, guía curl)
└── docs/html/ciba-flow.html               (1587 líneas, viewer standalone)
```

## Versión Keycloak mínima

**Keycloak 26.6+** — NO usar 26.0 (bug H2 + campos CIBA no soportados).

Configuración correcta (en `clients[].attributes`, NO a nivel de realm):
```json
{
  "clientId": "ciba-agent",
  "attributes": {
    "ciba.mode": "poll",
    "ciba.backchannelAuthenticationRequestSigningAlg": "PS256",
    "ciba.backchannelClientNotificationEndpoint": "",
    "oidc.ciba.interval": "5"
  }
}
```

## CIBA claims obligatorios

| Claim | Requerido | Uso |
|-------|-----------|-----|
| `cti` | ✅ Mandatory | CIBA Token Identifier — replay prevention |
| `auth_req_id` | ✅ Mandatory | Liga el token al request de auth |
| `nonce` | Recomendado | Anti-replay adicional |
| `aud` | ✅ Incluye resource server ID | Validación JwtAudienceValidator |
| `scope` | ✅ Solicitado | `calendar.read`, `email.send`, etc. |

Ya implementados en `CibaTokenValidator.java`.

## Pasos pendientes priorizados

### P0 — Crítico (bloquea cualquier uso)

- [ ] **P0.1** Decidir alcance:
  - (a) terminar `ciba-callagent/` (casi listo, falta E2E)
  - (b) añadir CIBA a `agent-oauth-poc/` (rompe decisión v2 "no CIBA")
  - (c) consolidar ambos
- [ ] **P0.2** Compilar y arrancar: `cd ciba-callagent && docker compose up --build -d`
- [ ] **P0.3** Validar E2E con TESTING.md (curl :8081/agent/request → approve KC → :8082/api/calendar/events)
- [ ] **P0.4** Verificar CTI replay prevention (2ª vez 401 `cti_replay`)

### P1 — Alto (necesario para integración)

- [ ] **P1.1** Conectar `ciba-callagent` con `agent-oauth-poc/agent-python/app.py`
- [ ] **P1.2** Decidir dónde va la skill borrada `oauth-flow-html` (en `~/.hermes/skills/` o restaurar)
- [ ] **P1.3** Restaurar skill si se conserva: `git checkout c204cdb -- "opencode/opencode skills/oauth-flow-html/"`
- [ ] **P1.4** Enlazar workaround `X-Requested-Scope-Token` desde aquí → `agent-oauth-poc/docs/05_KNOWN_ISSUES.md`

### P2 — Medio (mejoras)

- [ ] **P2.1** Migrar state store de `ConcurrentHashMap` → Redis (pérdida de estado en restart)
- [ ] **P2.2** Usar `ping` mode en vez de `poll` (latencia <1s vs 5-15s)
- [ ] **P2.3** Tests integración Spring Boot (ampliar a 10+ desde 1 actual)
- [ ] **P2.4** Hermetic tests con Testcontainers Keycloak
- [ ] **P2.5** Hardening healthcheck `wget --spider`

### P3 — Bajo

- [ ] **P3.1** i18n mensajes binding_message
- [ ] **P3.2** Métricas Prometheus (`/actuator/prometheus`)
- [ ] **P3.3** Documentar scope-narrowing diferencia vs `X-Requested-Scope-Token` workaround

## Ejemplo funcional CIBA Python (70 líneas standalone)

Archivo: `/home/vhdez/desarrollos-hermes/ciba-callagent/ciba_flow_demo.py`

```python
#!/usr/bin/env python3
"""ciba_flow.py — Standalone CIBA demo client."""
import json, time, requests

KC_BASE = "http://localhost:8181"
REALM = "ciba-realm"
CLIENT_ID = "ciba-agent"
CLIENT_SECRET = "ciba-agent-secret"
USER_ID = "testuser"
SCOPE = "openid profile email calendar.read"


def ciba_authreq():
    """Step 1: Agent → Keycloak. Init CIBA auth request."""
    url = f"{KC_BASE}/realms/{REALM}/protocol/openid-connect/ext/ciba/auth/authreq"
    body = (
        f"client_id={CLIENT_ID}&client_secret={CLIENT_SECRET}"
        f"&login_hint={USER_ID}&binding_message=Read+your+calendar"
        f"&requested_scope={SCOPE.replace(' ', '+')}"
    )
    r = requests.post(url, data=body,
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
    r.raise_for_status()
    return r.json()


def ciba_poll(auth_req_id, timeout=120):
    """Step 2: Agent → Keycloak. Poll until approved."""
    url = f"{KC_BASE}/realms/{REALM}/protocol/openid-connect/ext/ciba/auth/token"
    body = (
        f"grant_type=urn:openid:params:grant-type:ciba"
        f"&auth_req_id={auth_req_id}"
        f"&client_id={CLIENT_ID}&client_secret={CLIENT_SECRET}"
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.post(url, data=body,
                          headers={"Content-Type": "application/x-www-form-urlencoded"})
        if r.status_code == 200:
            return r.json()
        if r.json().get("error") == "authorization_pending":
            print("  ... waiting for user approval")
            time.sleep(5)
            continue
        r.raise_for_status()
    raise TimeoutError(f"No approval in {timeout}s")


if __name__ == "__main__":
    print("=== CIBA Flow Demo ===")
    auth = ciba_authreq()
    print(f"Step 1: auth_req_id={auth['auth_req_id']}")
    print(f"Step 2: Waiting for approval at "
          f"http://localhost:8181/realms/{REALM}/account/")
    token = ciba_poll(auth["auth_req_id"])
    print(f"Step 3: Got access_token (expires_in={token['expires_in']}s)")

    # Step 4: Call resource server
    r = requests.get(
        "http://localhost:8082/api/calendar/events",
        headers={"Authorization": f"Bearer {token['access_token']}"},
    )
    print(f"Step 4: resource server responded {r.status_code}")
```

## 12 Tests a verificar

| # | Test | Comando | Criterio |
|---|------|---------|----------|
| 1 | Health check | `curl :8081/health && curl :8082/health` | 200 + `"status":"UP"` |
| 2 | CIBA authreq inicia | `POST :8081/agent/request -d '{"userId":"testuser","action":"calendar_list"}'` | 202 + `requestId` |
| 3 | Poll devuelve PENDING | `GET :8081/agent/status/<rid>` | `{"status":"PENDING"}` |
| 4 | Approve manual | Aprobar en KC Account Console | `{"status":"APPROVED","accessToken":"..."}` |
| 5 | Execute resource | `POST :8081/agent/execute/<rid>` | `success:true` con datos |
| 6 | Resource valida JWT | `GET :8082/api/calendar/events -H "Bearer *** | 200 con eventos |
| 7 | CTI replay | Repetir #6 | 1ª 200, 2ª 401 `cti_replay` |
| 8 | Scope insuficiente | `calendar_create` con token `calendar.read` | 403 |
| 9 | Action inválida | `action: foo` | 400 INVALID_REQUEST |
| 10 | Request inexistente | `GET :8081/agent/status/nonexistent` | 404 NOT_FOUND |
| 11 | mvn test | `cd ciba-callagent && mvn test` | Suite verde |
| 12 | docker compose ps | `docker compose ps` | Todos healthy |

## Comparativa IdPs con CIBA

| IdP | Soporte | Estabilidad |
|-----|---------|-------------|
| **Keycloak 26.6** | ✅ Nativo | ⚠️ Quirks (H2, naming) |
| **Auth0** | ✅ Sí, docs limitadas | Estable |
| **AWS Cognito** | ❌ No nativo | N/A |
| **Ping Identity** | ✅ PingFederate | Estable, mejor tooling |
| **Azure Entra ID** | ⚠️ Preview | No producción |
| **Azure B2C Ext ID** | ❌ No soporta | Por eso `agent-oauth-poc` lo descartó |

## 5 Preguntas abiertas para Víctor

1. **¿Cuál es el verdadero alcance?**
   - (a) terminar `ciba-callagent/`
   - (b) añadir CIBA a `agent-oauth-poc/` (rompe decisión v2)
   - (c) consolidar
2. **¿Conservar skill `oauth-flow-html`?** Restaurar desde `c204cdb` o mover a `~/.hermes/skills/`
3. **`poll` o `ping` mode?**
   - poll (current): simple, 5-15s latencia
   - ping: necesita endpoint callback, <1s
4. **¿Subir `ciba-callagent/` a su propio repo?** Vive sin `.git` propio
5. **¿Probar Auth0 o Ping Identity como alternativa más estable?**

## Workarounds críticos (de skill `oauth-agent-on-behalf-of-user`)

| # | Problema | Solución |
|---|----------|----------|
| 1 | Spring autoconfig OIDC discovery | `spring.autoconfigure.exclude: org.springframework.boot.autoconfigure.security.oauth2.client.servlet.OAuth2ClientAutoConfiguration` |
| 2 | `api-key: ***` YAML rompe | Usar `apikey` (sin guion) |
| 3 | Lombok scope = compile | `<optional>true</optional>` o `provided` |
| 4 | Duplicate `POST /ciba/ping-callback` | Solo en `PingCallbackController` |
| 5 | H2 db bug KC 26.0 | `KC_DB=dev-mem` o `KC_DB=postgres` |
| 6 | `wget` vs `curl` Alpine | `wget -q --spider ... || exit 1` |
| 7 | `start-dev` no expone `/q/health/ready` | No añadir healthcheck al KC |

## Referencias

- OpenID Connect CIBA Core 1.0: https://openid.net/specs/openid-client-initiated-backchannel-authentication-core-1_0.html
- Keycloak CIBA docs: https://www.keycloak.org/docs/latest/authorization_services/index.html#_client_initiated_backchannel_authentication_grant
- Skill `~/.hermes/skills/oauth-agent-on-behalf-of-user/SKILL.md` (967 líneas)
- Skill `~/.hermes/skills/software-development/oauth-scope-debugging/SKILL.md`
- Skill `~/.hermes/skills/devops/oauth-b2c-vs-keycloak-comparison/SKILL.md`
- Workaround X-Requested-Scope-Token: `agent-oauth-poc/docs/05_KNOWN_ISSUES.md` (sección 1)

## Próxima acción recomendada

**Opción A (recomendada)**: ejecutar `cd /home/vhdez/desarrollos-hermes/ciba-callagent && docker compose up --build -d` y validar flujo completo con TESTING.md. ETA: 30-60 min.

**Opción B**: si Víctor confirma `agent-oauth-poc`, primero decidir si revertir la decisión "no CIBA" de v2.
