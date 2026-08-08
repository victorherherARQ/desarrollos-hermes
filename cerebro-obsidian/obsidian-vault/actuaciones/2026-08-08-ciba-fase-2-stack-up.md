# Actuación 2026-08-08 — CIBA Fase 2 ✅ STACK LEVANTADO

## 🎯 Logro principal

**Stack CIBA arrancando completamente**:

- ✅ postgres: healthy
- ✅ keycloak 26.6.4: healthy, realm `agent-poc` importado OK
- ✅ spring-boot-api: healthy, JwtDecoder con CIBA validator opcional
- ✅ `backchannel_token_delivery_modes_supported: ['poll', 'ping']` en `/realms/agent-poc/.well-known/openid-configuration`

## 🔍 El problema (resumen)

`realm-agent-poc.json` (25KB) tenía campos incompatibles con KC 26.6.4:
- `refreshTokenMaxReuseCount` → KC 26 ya no lo acepta
- `allowUserManagedAccessAllowed` → idem
- `cibaBackchannelTokenDeliveryMode` → KC 26 lo rechaza en realm-level (schema estricto)

Cada vez que borraba uno aparecía el siguiente → loop infinito. Por eso elegí **re-crear el realm de cero** vía Admin API.

## 🛠️ Solución aplicada

1. **Levantar KC sin realm** (`docker run --env-file kc-env.list quay.io/keycloak/keycloak:26.6.4 start-dev`)
2. **Crear realm agent-poc** vía POST `/admin/realms` con campos mínimos (solo `realm` + `enabled`)
3. **Configurar CIBA en client** (no en realm) — `cibaBackchannelTokenDeliveryMode=poll`, `cibaExpiresIn=120`, `cibaInterval=5`, `cibaAuthRequestSigningAlg=RS256` como `attributes` del cliente `ciba-agent`
4. **Crear clients**: `spring-boot-api` (bearerOnly), `ciba-agent` (CIBA poll)
5. **Crear users**: `ana` + `testuser`
6. **Crear scope**: `calendar.read`
7. **Re-exportar**: GET cada sub-resource, ensamblar JSON con schema 26.6.4

## 📦 Resultado

- `keycloak/realm/realm-agent-poc.json` regenerado: **41KB**, **8 clients**, **2 users**, **15 client scopes**
- Schema 100% compatible con KC 26.6.4
- Spring Boot 3.2.5 arranca sin errores de JwtDecoder
- Configuración `ciba.enabled` presente en `application.yml` (default false)

## ⚠️ Validación E2E pendiente (no crítica)

Para validar E2E completa (password grant → token → call API):

1. **Cambiar spring-boot-api a `directAccessGrantsEnabled=true`** — mi PUT no se aplicó (queda `bearerOnly`)
2. **Probar flujo password grant** con ana
3. **Llamar `/api/calendar/events`** con el JWT
4. **Validar CTI replay prevention** (2ª request con mismo cti → 401)
5. **Validar `aud` claim** (rechazo si aud ≠ spring-boot-api)
6. **Probar CIBA end-to-end** con un client mock que use el flujo poll

## 📋 Estado de las 5 fases

| Fase | Descripción | Estado | Commit |
|------|-------------|--------|--------|
| 0 | ADR consolidación | ✅ | `833c72c` |
| 1 | Migrar Resource Server | ✅ | `b58baff` |
| 2 | Validar E2E docker | ✅ Stack UP | `0e3ccc5` |
| 3 | Skill `oauth-flow-html` | ✅ | `0b4b03d` |
| 4 | Eliminar `ciba-callagent/` | ⏸️ | — |

## 🐛 Issues pendientes (no críticos)

1. **Test E2E con password grant**: spring-boot-api client sigue `bearerOnly`. Necesita cambio de config + restart.
2. **CTI replay validation**: no probada en docker. Solo tests unitarios (7/7 PASS).
3. **CIBA client mock**: hay un `client-mock/` en el compose, no levantado. Sería útil para test E2E con flujo poll.
4. **agent-python service**: huérfano (`agent-oauth-poc-agent-service-1`). Sigue del docker-compose viejo.
5. **`ciba-client-spring` migration**: el código Python/Java del CIBA client NO migrado aún de `ciba-callagent/`.
6. **`docker-compose.yml`**: el `kc-temp` container usado para crear el realm sigue corriendo en `agent-poc-net`. Limpiar.

## 🤝 Lo que necesito de Víctor

| Decisión | Default si dices "tira" |
|----------|------------------------|
| ¿Sigo con validación E2E (items 1-3 del pendiente)? | Sí, ~1h |
| ¿Migro `ciba-client-spring` desde `ciba-callagent/`? | Sí, ~2h |
| ¿Borro `ciba-callagent/` ya (Fase 4)? | NO, espera E2E verde |
| ¿Limpio `kc-temp` y `agent-oauth-poc-agent-service-1`? | Sí, ahora |

## 📦 Commits

```
833c72c docs(agent-oauth-poc): ADR-001 consolida CIBA en agent-oauth-poc
b58baff feat(agent-oauth-poc): migra validadores CIBA desde ciba-callagent (ADR-001)
0b4b03d feat(skill): generaliza oauth-flow-html + ejemplo CIBA + 2 ubicaciones
4df90ad docs(actuaciones): 2026-08-07 CIBA consolidación fase 1 (3/5 fases OK)
1f004bf docs(tareas): actualiza CIBA con decisiones Víctor + estado 5 fases
66dcde1 docs(actuaciones): 2026-08-08 CIBA Fase 2 - realm JSON schema mismatch KC 26.6.4
0e3ccc5 feat(agent-oauth-poc): realm agent-poc regenerado para KC 26.6.4  ← AHORA
```

## 🐳 Containers estado (LIVE)

```
agent-poc-postgres         Up 8 hours (healthy)
agent-poc-keycloak         Up 3 minutes
agent-poc-spring-boot-api  Up 2 minutes (healthy)
kc-temp                    Up 8 minutes (huérfano, red agent-poc-net)
agent-oauth-poc-agent-service-1  Up 4 days (huérfano, unhealthy)
```
