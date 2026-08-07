# Actuación 2026-08-07 — CIBA consolidada en `agent-oauth-poc/`

## 🎯 Resumen

**Avance real en la consolidación de CIBA** siguiendo las decisiones de Víctor (1-5).

| Fase | Estado | Detalle |
|------|--------|---------|
| **Fase 0** — ADR | ✅ | `agent-oauth-poc/docs/CIBA_CONSOLIDATION_DECISION.md` |
| **Fase 1** — Migración Resource Server | ✅ | 3 clases + 1 test + SecurityConfig + pom |
| **Fase 2** — Validar E2E docker | ⏸️ | Pospuesto: `target/` bloqueado por permisos (root) |
| **Fase 3** — Skill `oauth-flow-html` | ✅ | Generalizada, ejemplo CIBA, 2 ubicaciones |
| **Fase 4** — Cleanup `ciba-callagent/` | ⏸️ | Pospuesto: necesario `docker compose up` primero |

## ✅ Lo que YA funciona

### 1. ADR-001 publicado
- 5 decisiones documentadas con contexto, consecuencias y alternativas
- 5 fases con ETA y estado
- `commit 833c72c`

### 2. Resource Server migrado
- `com.poc.api.ciba.CtiReplayCache` — Caffeine, 24h TTL, 10k entries
- `com.poc.api.ciba.CibaTokenValidator` — cti + auth_req_id + scope
- `com.poc.api.ciba.CibaTokenValidatorAdapter` — `OAuth2TokenValidator<Jwt>` para Spring
- `SecurityConfig#jwtDecoder` enchufa CIBA solo si `ciba.enabled=true`
- `pom.xml` añade Caffeine + WebFlux (opcional)
- `CibaTokenValidatorTest`: **7/7 PASS** (valid, replay, missing cti, blank cti, scope true/false, missing auth_req_id)
- `commit b58baff`

### 3. Skill generalizada
- Restaurada desde `c204cdb`
- SKILL.md ampliado: incluye CIBA, OIDC, SAML
- Compatibilidad: `opencode, hermes`
- Nuevo frontmatter: `generalized`, `locations`
- Ejemplo `examples/ciba-flow.json` (12 pasos, 6 actores, ambos modos)
- 2 ubicaciones sincronizadas:
  - `~/.hermes/skills/oauth-flow-html/`
  - `desarrollos-hermes/.hermes/skills/oauth-flow-html/`
- README en mi home con instrucciones
- Build verificado: HTML 5848 bytes generado OK
- `commit 0b4b03d`

## ⏸️ Lo que falta

### Fase 2: Validar E2E con docker

**Bloqueo actual**: `/home/vhdez/desarrollos-hermes/agent-oauth-poc/spring-boot-api/target/` está **root-owned**. No puedo `mvn clean` ni escribir `target/classes/`.

**Solución**: compilé en `/tmp/ciba-build/` (verificado: 7/7 tests pasan). Pero `mvn package` para docker necesita `target/` accesible.

**Opciones**:
- (a) Pedir a Víctor que haga `sudo chown -R vhdez:vhdez target/`
- (b) Esperar a tener docker compose y validar con curl en lugar de mvn
- (c) Recrear proyecto desde cero con `target/` bien de origen

### Fase 4: Eliminar `ciba-callagent/`

**Bloqueo**: depende de Fase 2. No quiero borrar el código antes de validar que la migración funciona E2E.

## 🐛 Issues pendientes (no críticos)

1. **`ciba.enabled=true` requiere config extra**: el `application.yml` actual NO tiene `ciba.enabled`. Añadir flag + bloque opcional.
2. **Migrar `ciba-resource-server` controllers**: los `CalendarController`, `EmailController`, `UserController` de ciba-callagent son similares pero NO idénticos a los de `agent-oauth-poc`. Decidir si se consolidan en uno.
3. **`ciba-client-spring`** (AgentController, CibaClientService, etc.) NO migrado aún. Quedaría como sub-módulo dentro de `agent-oauth-poc/`.
4. **Tests E2E con curl** (TESTING.md de ciba-callagent): no adaptados a la nueva estructura.
5. **`docker-compose.yml`**: actualmente solo tiene Keycloak + spring-boot-api. Falta añadir el CIBA client si se levanta.

## 🎯 Próximos pasos sugeridos

| # | Acción | ETA |
|---|--------|-----|
| 1 | Víctor da sudo o recrea target con permisos | 5 min |
| 2 | `mvn clean package` | 5 min |
| 3 | `docker compose up -d --build` | 5 min |
| 4 | Ejecutar curl tests del TESTING.md | 30 min |
| 5 | Validar CTI replay (2ª request → 401) | 5 min |
| 6 | Si OK, eliminar `ciba-callagent/` | 5 min |
| 7 | Decidir migración de `ciba-client-spring` o usar solo Python | 1h |

Total ETA: ~1h si Víctor desbloquea permisos.

## 📦 Commits

```
833c72c docs(agent-oauth-poc): ADR-001 consolida CIBA en agent-oauth-poc
b58baff feat(agent-oauth-poc): migra validadores CIBA desde ciba-callagent (ADR-001)
0b4b03d feat(skill): generaliza oauth-flow-html + ejemplo CIBA + 2 ubicaciones
```

## 🤝 Lo que necesito de Víctor

- **Permisos sudo** en WSL para `chown -R vhdez:vhdez /home/vhdez/desarrollos-hermes/agent-oauth-poc/spring-boot-api/target/`, O
- **Confirmación** de cómo proceder con `target/` root-owned (¿lo recreo desde cero con permisos OK?)
