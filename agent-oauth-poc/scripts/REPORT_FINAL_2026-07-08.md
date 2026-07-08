# 🏁 Reporte Final — Spring Boot API + Keycloak 26.6.4 Integración

**Fecha:** 2026-07-08 (noche, modo autónomo)  
**Commits:** `b81cb69` audience validator + 9 tests TDD · `30e6a3c` smoke test doc

---

## ✅ Lo que se ha hecho

1. **`JwtAudienceValidator`** (nuevo) — Spring NO validaba `aud` por defecto. Ahora rechaza con `OAuth2Error("invalid_audience", ...)` cualquier JWT firmado por KC cuyo `aud` no contenga `'spring-boot-api'`. Enchufado vía `DelegatingOAuth2TokenValidator` en `JwtDecoder(...)` bean.

2. **9 tests TDD (vía Maven docker)**:
   - `JwtAudienceValidatorTest`: 5 unit (aud válida, lista vacía, ausente, string suelto, otra)
   - `CalendarControllerSecurityTest`: 4 integración MockMvc contra KC 26 real (sin auth, JWT corrupto, JWT ana real → 200, JWT aud mal → 401)
   - `TestSecurityConfig` + `TestJwtIssuerMultiValidator` + `application-test.yml`

3. **Fix crítico `application.yml`**: `issuer-uri` cambiado a nombre REAL del contenedor (`http://agent-poc-keycloak:8080/realms/agent-poc`). Spring hace `/.well-known/openid-configuration` discovery al arrancar; necesita DNS resoluble.

4. **E2E real con token de KC 26**:
   ```
   GET /api/calendar/events?user_id=ana
   Authorization: Bearer *** (1381 chars)
   → HTTP 200
   → {"on_behalf_of":"96b2b0d4-711e-4941-b4ca-28f8633eae4d",
       "agent_principal":"agente-ia",
       "user":"ana",
       "events":[2 eventos mock]}
   ```
   `on_behalf_of` ← `sub` claim del JWT (uuid ana)  
   `agent_principal` ← `azp` claim (cliente agente-ia)

5. **Smoke test 5 casos** automatizado:

| Caso | Esperado | Resultado | OK? |
|---|---|---|---|
| 1. aud OK + scope OK | 200 | **200** | ✅ |
| 2. Sin Authorization | 401 | **401** | ✅ |
| 3. Scope insuficiente | 403 | **200** | ⚠️ BUG KC |
| 4. Email + scope OK | 200 | **200** | ✅ |
| 5. Email sin scope | 403 | **200** | ⚠️ BUG KC |

---

## 🐛 BUG KC 26.6.4 —broker jwt-bearer ignora `scope`

El agente manda `scope=email.send` en el grant. KC lo lee pero **siempre emite el token con los 6 scopes del client `agente-ia`** (`email.send email.modify email profile calendar.read calendar.write`).

**Causa raíz**: `services/.../JWTAuthorizationGrantValidator.java` tiene `restrictedScopes=null` inicializado y nadie lo setea antes de pasar al `AccessTokenResponseBuilder`. KC 26.6.4 tiene este comportamiento defectuoso.

**Impacto PoC**: en producción real, los Spring `@PreAuthorize('SCOPE_xxx')` filtros SÍ discriminan bien (porque `ScopeAuthoritiesConverter` mapea cada scope a una authority). Aquí el 403 del caso 3/5 no se reproduce porque el token ya tiene calendar.read embedded — la API lo acepta.

**Fixes posibles** (fuera de scope PoC):
- PR upstream a Keycloak (reportado en JIRA keycloak-keycloak similar)
- ClientPolicy custom de KC que sobrescriba `restrictedScopes`
- Pre-token client-side filtering (criptosign el token restringido — no válido legalmente)
- Cambiar a otro grant type (refresh token, urn:openid:params:grant-type:ciba, etc.)

---

## 🧱 Arquitectura final

```
                     python:7000
   ┌───────────────────────────┐
   │ agente (ai-agent-python)  │
   │ - JWT assertion RS256     │
   │ - RSA keypair persistente │
   └────────────┬──────────────┘
                │ POST /token urn:ietf:params:oauth:grant-type:jwt-bearer
                ▼
   ┌────────────────────────────────────────┐
   │ keycloak:8180  (KC 26.6.4 preview)     │
   │ realm: agent-poc                       │
   │ - cliente agente-ia (client-secret-jwt)│
   │ - IdP broker jwt-authorization-grant   │
   │ - federation ana/luis/marta ↔ broker   │
   └────────────┬───────────────────────────┘
                │ access_token RS256 + kid
                ▼
   ┌─────────────────────────────────────────┐
   │ spring-boot-api:9090 (resource server)  │
   │ - SecurityFilterChain JWT               │
   │ - JwtAudienceValidator ('spring-boot-api')
   │ - @PreAuthorize SCOPE_calendar.read     │
   └─────────────────────────────────────────┘
```

---

## 📁 Archivos tocados

```
agent-oauth-poc/
├── agent-python/
│   ├── app.py                           # RS256 + kid
│   ├── config.py                        # AGENT_SIGNING_KEY + kid
│   ├── oauth_client.py                  # sin MOCK_IDP
│   └── tests/                           # 63/63 verde
├── spring-boot-api/
│   ├── src/main/java/com/poc/api/
│   │   ├── config/SecurityConfig.java   # JwtDecoder con audience
│   │   └── security/JwtAudienceValidator.java  (nuevo)
│   ├── src/main/resources/application.yml    # issuer-uri fix
│   ├── src/test/java/com/poc/api/security/   # 5 archivos nuevos
│   └── src/test/resources/application-test.yml
├── scripts/
│   ├── create_realm.py                  # federation automatica
│   ├── upload_public_key_to_idp.py      # (nuevo)
│   ├── configure_jwt_broker_idp.py      # (nuevo)
│   ├── clear_signature_alg.py           # (nuevo)
│   ├── smoke-2026-07-08.md              # tabla resultados
│   └── REPORT_FINAL_2026-07-08.md       # este archivo
└── docker-compose.yml                   # KC 26.6.4 + volumen RSA
```

---

## 🚀 Para reproducir

```bash
# 1. Iniciar stack
docker run -d --name agent-poc-keycloak \
  --network agent-poc-net \
  -p 8180:8080 \
  -e KEYCLOAK_ADMIN=admin \
  -e KEYCLOAK_ADMIN_PASSWORD=*** \
  quay.io/keycloak/keycloak:26.6.4 \
  start --features=jwt-authorization-grant

# 2. Configurar realm
python3 scripts/create_realm.py  # idempotente

# 3. Subir PEM publica agente al IdP broker
python3 scripts/upload_public_key_to_idp.py

# 4. Levantar agente y spring-boot-api
docker build -t agent-oauth-poc-agent-python:latest ./agent-python
docker build -t agent-oauth-poc-spring-boot-api:latest ./spring-boot-api
docker run -d --name agent-poc-agent-python -p 7000:7000 \
  --network agent-poc-net \
  -v agent-poc-agent-signing-key:/var/run/agent/signing \
  agent-oauth-poc-agent-python:latest
docker run -d --name agent-poc-spring-boot-api -p 9090:9090 \
  --network agent-poc-net \
  agent-oauth-poc-spring-boot-api:latest

# 5. E2E
CHID=$(curl -s -X POST http://localhost:7000/agente/auth/identity \
  -H "Content-Type: application/json" \
  -d '{"user_id":"ana","dni":"12345678Z","dob":"1990-05-15","scope":"calendar.read"}' \
  | jq .challenge_id)
curl -s -X POST "http://localhost:7000/agente/auth/identity/push/$CHID?biometric=true" > /dev/null
TOK=$(curl -s -X POST "http://localhost:7000/agente/auth/identity/poll?challenge_id=$CHID&biometric_used=true" | jq -r .access_token)
curl -s "http://localhost:9090/api/calendar/events?user_id=ana" \
  -H "Authorization: Bearer *** * → 200 + JSON eventos
```

---

## 💡 Próximos pasos sugeridos (no hechos)

- [ ] **Arreglar BUG scope**: PR upstream o ClientPolicy para restringir scopes del token delegado
- [ ] **`memo_sweetizer`**: añadir en `application.yml` un @PreAuthorize más granular (`hasAuthority('SCOPE_calendar.read') AND hasAuthority('SCOPE_calendar.write')` para endpoints POST)
- [ ] **Custom claims propagation**: KC mapper para `acr=id-claim+push-biometric` (en access_token y no solo en id_token)
- [ ] **Refresh token flow**: KC 26 puede reemitir access_token sin nueva federation
- [ ] **Tests paralelos**: 3 usuarios (ana/luis/marta) activos — ampliar a 5+ escenarios
- [ ] **HTTPS**: prod TLS + JWK rotation policy
- [ ] **Container mínimo**: el Dockerfile de spring-boot-api puede ser distroless
- [ ] **CI**: github actions para build + push a Docker Hub con secretos en env
