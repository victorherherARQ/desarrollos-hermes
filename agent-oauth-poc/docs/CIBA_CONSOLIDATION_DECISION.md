# ADR-001: Consolidación de CIBA en `agent-oauth-poc`

- **Fecha**: 2026-08-07
- **Estado**: Aceptado
- **Decisor**: Víctor
- **Tarea origen**: `Tareas/2026-08-03-completar-desarrollo-ciba.md`

## Contexto

Hasta ahora teníamos **dos proyectos OAuth separados**:

| Proyecto | Función | Líneas .java | E2E validado |
|----------|---------|--------------|--------------|
| `agent-oauth-poc/` | Auth Code+PKCE, Device Code, JWT Bearer (OBO) | ~13 | Sí |
| `ciba-callagent/` | Solo CIBA (cliente + RS) | 17 | **Nunca** |

`ciba-callagent/` nació como POC aislado pero:
1. **Duplica** SecurityConfig, CalendarController, EmailController, docker-compose
2. **Rompe** la decisión arquitectural v2 de `agent-oauth-poc` ("no CIBA, para ser portable a Azure B2C")
3. **Nunca compiló** (`target/classes/` solo tiene `application.yml`)
4. Tiene **mejor seguridad** (CTI replay prevention, ping callback) que `agent-oauth-poc/`

## Decisión

**Consolidar todo en `agent-oauth-poc/`** y eliminar `ciba-callagent/`. Esto **revierte parcialmente la decisión v2** ("no CIBA"), pero se justifica porque:

- Keycloak 26.6+ ya está disponible
- Las **mejoras de seguridad** de `ciba-callagent/` (CTI replay, ping callback) son superiores
- Mantener **un solo proyecto** simplifica CI/CD, tests, onboarding
- La portabilidad a B2C se mantiene **opcional** vía flag (CIBA solo en Keycloak)

## Cambios estructurales

### 1. CIBA se añade a `agent-oauth-poc/` (no se mantiene `ciba-callagent/`)

```
agent-oauth-poc/                       (proyecto canónico)
├── spring-boot-api/                   (Resource Server, ya existe)
│   └── security/
│       ├── JwtAudienceValidator.java       (existente)
│       ├── CibaTokenValidator.java        ← MOVER de ciba-callagent
│       └── CtiReplayCache.java            ← MOVER de ciba-callagent
├── agent-python/                      (Python agent, ya existe)
│   └── ciba_client.py                    ← NUEVO, ~150 líneas standalone
├── ciba-client-spring/                ← MOVER ciba-oauth2-client (Spring Boot CIBA client)
├── keycloak/ciba-realm/               ← MOVER realm JSON + import script
└── docs/CIBA.md                       ← NUEVO (poll vs ping, cuándo usar)
```

### 2. Skill `oauth-flow-html` se conserva y generaliza

- Restaurar desde `git checkout c204cdb -- "opencode/opencode skills/oauth-flow-html/"`
- **Mover** a **dos sitios** (sincronizados):
  - `~/.hermes/skills/oauth-flow-html/` (mi home, para uso desde opencode CLI)
  - `desarrollos-hermes/.hermes/skills/oauth-flow-html/` (en repo, para trabajo)
- **Generalizar**: parametrizar paths hardcoded (hoy asume `ciba-callagent/`)

### 3. `poll` y `ping` mode: ambos implementados

| Modo | Latencia | Infra extra | Cuándo usar |
|------|----------|-------------|-------------|
| `poll` | 5-15s | Ninguna | Default, MVP, demos |
| `ping` | <1s | Endpoint callback público | Producción, mobile-first |

Ambos van detrás de un flag `ciba.mode=poll|ping` en `application.yml`.

### 4. `ciba-callagent/` se queda donde está hasta finalizar

No mover a repo propio todavía. Cuando esté validado y estable, decidir.

### 5. Keycloak 26.6+ como IdP objetivo

NO se consideran Auth0 / Ping / Azure por ahora. Keycloak cubre el 100% del caso y ya está dockerizado.

## Consecuencias

### ✅ Positivas

- **Un solo proyecto** OAuth (antes 2)
- **Mejor seguridad**: CTI replay prevention disponible para todos los flows
- **Tests E2E** del flujo CIBA (que nunca se hicieron)
- **Skill reutilizable** desde Hermes + opencode

### ❌ Negativas (aceptadas)

- **Rompe portabilidad B2C** (Azure B2C no soporta CIBA). Mitigación: CIBA queda tras flag `ciba.enabled=false` por defecto para el modo B2C.
- **Trabajo de migración** (~2h mover + validar)
- **`ciba-callagent/` queda muerto** hasta Fase 4

## Plan de ejecución

| Fase | Acción | ETA | Estado |
|------|--------|-----|--------|
| 0 | Este ADR | 15m | ✅ 2026-08-07 |
| 1 | Migrar código CIBA a `agent-oauth-poc/` | 1-2h | ⏳ |
| 2 | Validar E2E con docker compose + TESTING | 30-60m | ⏳ |
| 3 | Generalizar skill `oauth-flow-html` | 1h | ⏳ |
| 4 | Eliminar `ciba-callagent/` | 5m | ⏳ |

## Alternativas consideradas

### (a) Mantener 2 proyectos separados

❌ **Rechazado**: duplicación, drift, doble mantenimiento.

### (b) Añadir CIBA a `agent-oauth-poc/` sin tocar `ciba-callagent/`

❌ **Rechazado**: deja código muerto, no se gana nada.

### (c) Consolidar (esta decisión)

✅ **Aceptado**: mejor relación trabajo/beneficio.

## Referencias

- Tarea: `Tareas/2026-08-03-completar-desarrollo-ciba.md`
- Skill: `~/.hermes/skills/oauth-agent-on-behalf-of-user/SKILL.md` (967 líneas)
- Skill a restaurar: `oauth-flow-html` (commit `c204cdb`)
- OpenID CIBA Core 1.0: https://openid.net/specs/openid-client-initiated-backchannel-authentication-core-1_0.html
