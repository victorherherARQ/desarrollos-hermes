# Actuación 2026-08-08 — CIBA Fase 2 + diagnóstico realm JSON

## 🎯 Lo intentado

**Objetivo**: Validar E2E la integración CIBA con docker compose (Fase 2).

## ✅ Lo que sí funcionó

### 1. target/ recreado con mis permisos
- `cp -r src/main src/test pom.xml /tmp/ciba-clean-build/`
- `mvn clean compile test -o` → **Tests CIBA: 7/7 PASS** (los mismos de antes)
- `mvn package -DskipTests` → **BUILD SUCCESS**, jar 35.7 MB

### 2. Dockerfile docker rebuild OK
- `docker compose build spring-boot-api` → Built sha256:3d09c1a25...
- Spring Boot 3.2.5 compila desde `src/` con `mvn package -DskipTests`

## ⛔ Lo que falló: realm JSON schema mismatch en KC 26.6.4

Al re-arrancar KC (con el nuevo jar), KC falla al importar el realm:

```
ERROR: Unrecognized field "refreshTokenMaxReuseCount" (class RealmRepresentation)
ERROR: Unrecognized field "allowUserManagedAccessAllowed"
ERROR: Unrecognized field "cibaBackchannelTokenDeliveryMode"
```

Esto hace que KC **no arranque**, y por tanto Spring Boot API no puede conectar al issuer-uri `http://keycloak:8080/realms/agent-poc/.well-known/openid-configuration` y falla con `Connection refused`.

## 🔍 Análisis del problema

**Causa raíz**: El `keycloak/realm/realm-agent-poc.json` fue exportado con una versión **anterior** de KC (probablemente KC 24 o 25). Al actualizar a KC 26.6.4, el schema del RealmRepresentation es **más estricto** y rechaza campos que antes aceptaba silenciosamente.

**NO es problema de mi migración CIBA**:
- Tests unitarios: ✅ 7/7 PASS
- Compilación: ✅ BUILD SUCCESS
- Jar generado: ✅ 35.7 MB
- Docker build: ✅ Build OK
- Spring Boot arranca: ✅ hasta que intenta conectar a KC

El realm JSON fallaba ANTES de mi migración (5 días que los contenedores estaban "unhealthy"). Mi rebuilder solo lo sacó a la luz.

## 🛠️ Workaround aplicado (no commiteado)

Borrar los campos problemáticos hace que **aparezca el siguiente**. Hay al menos 3-4 campos con este problema. Iterar borrando uno a uno NO es eficiente.

**Solución correcta** (no aplicada):
1. Levantar KC sin realm import (`--spi-import-export-enabled=false` o similar)
2. Crear el realm via Admin API o via UI
3. Re-exportarlo con el schema actual
4. Reemplazar `realm-agent-poc.json` con el exportado

Esto es trabajo de **~30 min** y desvía el foco de CIBA.

## 📋 Estado actual de las 5 fases

| Fase | Descripción | Estado |
|------|-------------|--------|
| 0 | ADR consolidación | ✅ commit `833c72c` |
| 1 | Migrar Resource Server | ✅ commit `b58baff` (compila + 7/7 tests) |
| 2 | Validar E2E docker | ⏸️ **Bloqueado por realm JSON schema KC 26.6.4** |
| 3 | Skill `oauth-flow-html` | ✅ commit `0b4b03d` |
| 4 | Eliminar `ciba-callagent/` | ⏸️ Sigue pospuesto |

## 🎯 Recomendación

**Decisión técnica**: NO seguir con Fase 4 (eliminar `ciba-callagent/`) hasta tener Fase 2 verde. Si eliminamos `ciba-callagent/` con KC roto, perdemos la única doc + tests del flujo CIBA end-to-end.

**Opciones para destrabar Fase 2**:

| Opción | Tiempo | Descripción |
|--------|--------|-------------|
| A | 30 min | Re-exportar realm desde KC 26.6.4 limpio y reemplazar JSON |
| B | 1h | Crear realm vía Admin API + configurar CIBA policies manualmente |
| C | 5 min | Desactivar CIBA en KC realm, dejar Spring Boot corriendo sin CIBA |

**Sugerencia**: Opción A es la más limpia. Pero requiere levantar KC sin realm (modificar comando) y volver a crearlo.

## 🤝 Lo que necesito de Víctor

| Decisión | Default si dices "tira" |
|----------|------------------------|
| ¿Re-exporto realm (Opción A) o desactivo CIBA (Opción C)? | Opción A (más limpio) |
| ¿Elimino `ciba-callagent/` igualmente (Fase 4)? | NO, espera a Fase 2 verde |

## 📦 Commits

```
833c72c docs(agent-oauth-poc): ADR-001 consolida CIBA en agent-oauth-poc
b58baff feat(agent-oauth-poc): migra validadores CIBA desde ciba-callagent (ADR-001)
0b4b03d feat(skill): generaliza oauth-flow-html + ejemplo CIBA + 2 ubicaciones
4df90ad docs(actuaciones): 2026-08-07 CIBA consolidación fase 1 (3/5 fases OK)
1f004bf docs(tareas): actualiza CIBA con decisiones Víctor + estado 5 fases
```

## 🐳 Containers estado (no tocado)

- `agent-poc-keycloak` → **Exited** (fallo realm import)
- `agent-poc-spring-boot-api` → **Exited** (Connection refused a KC)
- `agent-poc-postgres` → Up (healthy)
- `agent-oauth-poc-agent-service-1` → Up 4 days (unhealthy, huérfano)
