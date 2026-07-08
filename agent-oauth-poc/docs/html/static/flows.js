// ============================================================
//  flows.js — specs declarativos de los 3 flujos
//  Cada step = { from, to, label, kind: 'sync'|'reply'|'self',
//                desc, code:{lang,...}, claims?, actor? }
// ============================================================

/** Plantilla para construir un actor con coordenadas calculadas después */
const actor = (id, name, role, color) => ({ id, name, role, color });

/** Helpers curl por flujo — *no* interpolan secretos reales */
const curlA = (scope = 'calendar.read') => `# 1) Cliente pide authorize URL al agente (PKCE pair generada internamente)
curl -s -X POST http://localhost:7000/agente/auth/authorize \\
  -H "Content-Type: application/json" \\
  -d '{"user_id":"ana","scope":"openid profile email ${scope}"}' | jq .`;
const curlB = () => `# 1) Cliente pide device_code al agente
curl -s -X POST http://localhost:7000/agente/auth/device \\
  -H "Content-Type: application/json" \\
  -d '{"user_id":"ana","scope":"openid profile email calendar.read"}' | jq .`;
const curlC = () => `# 3) Cliente pide OBO al agente (token de Ana -> token refinado)
curl -s -X POST http://localhost:7000/agente/auth/obo \\
  -H "Content-Type: application/json" \\
  -d "{\"user_access_token\":\"$ACCESS_TOKEN\",\"requested_scope\":\"email.send\"}" | jq .`;

// ============== FLUJO A: Auth Code + PKCE ==============
export const flowA = {
  id: 'A',
  title: 'Flujo A — Authorization Code + PKCE',
  meta: 'RFC 6749 §4.1 · RFC 7636 · 8 mensajes · ~10-15s · navegador humano cerca',
  actors: [
    actor('user',   'Humano (Ana)',    'browser + MFA',   '#fde68a'),
    actor('cliente','Cliente / App',  'invoca al agente','#a5b4fc'),
    actor('agente', 'Agente IA',       'FastAPI :7000',   '#7e83ff'),
    actor('mock',   'client-mock',     'webapp :3000',    '#c084fc'),
    actor('idp',    'Keycloak / B2C',  'Authorization',   '#5eead4'),
    actor('api',    'Spring Boot API', 'Resource :9090',  '#fb7185'),
  ],
  steps: [
    {
      from: 'cliente', to: 'agente',
      kind: 'sync', label: 'POST /agente/auth/authorize  {user_id, scope}',
      desc: 'El cliente pide al agente una URL de autorización con el scope deseado. El agente genera internamente un par PKCE (code_verifier + code_challenge = base64url(SHA256(verifier))).',
      code: { bash: curlA('calendar.read'), python:
`resp = requests.post(
  "http://localhost:7000/agente/auth/authorize",
  json={"user_id":"ana", "scope":"openid profile email calendar.read"},
).json()
print(resp["authorize_url"])` },
      actor: 'agente',
    },
    {
      from: 'agente', to: 'mock',
      kind: 'sync', label: 'devuelve {authorize_url, code_verifier, state, redirect_uri}',
      desc: 'El agente devuelve la URL completa y el code_verifier. El cliente (o su webapp client-mock) lo guarda hasta el callback.',
      code: { json:
`{
  "authorize_url":   "http://localhost:8180/realms/agent-poc/protocol/openid-connect/auth?...&code_challenge=q1Z7...&code_challenge_method=S256",
  "code_verifier":   "dBjftJeZ4CVP-...",
  "state":           "af0ifjsldkj",
  "redirect_uri":    "http://localhost:3000/auth/callback"
}` },
      actor: 'agente',
    },
    {
      from: 'mock', to: 'user',
      kind: 'sync', label: 'window.location = authorize_url',
      desc: 'La webapp redirige el browser del humano a la página de login del IdP. Esto requiere un navegador real porque la PKCE depende del flujo estándar de OAuth.',
      code: { html:
`<!-- public/index.html -->
<script>
  const { authorize_url } = await fetch("/auth/authorize", {method:"POST", body:JSON.stringify({
    user_id, scope
  })}).then(r=>r.json());
  window.location = authorize_url + "&prompt=login";
</script>` },
      actor: 'mock',
    },
    {
      from: 'user', to: 'idp',
      kind: 'sync', label: 'login + MFA (Passkey / TOTP)',
      desc: 'El humano teclea usuario + password en el formulario del IdP y completa el MFA. Crucial: el agente nunca ve las credenciales. Con Passkey ni siquiera hay password.',
      code: { note:
'Aqu\u00ed el humano interact\u00faa. El agente no ve nada.\nEn KC: pantalla de login + passkey opcional.\nEn B2C External ID: flujo signup_signin_v1 con Passkey forzado.' },
      actor: 'user',
    },
    {
      from: 'idp', to: 'mock',
      kind: 'reply', label: '302 → /auth/callback?code=...&state=...',
      desc: 'Keycloak redirige al client-mock con el authorization code. El state protege contra CSRF.',
      code: { http:
`HTTP/1.1 302 Found
Location: http://client-mock:3000/auth/callback
  ?code=SplxlOBeZQQYbYS6WxSbIA
  &state=af0ifjsldkj
  &session_state=1234abcd` },
      actor: 'idp',
    },
    {
      from: 'mock', to: 'idp',
      kind: 'sync', label: 'POST /token  (code + code_verifier)',
      desc: 'Client-mock intercambia el code por tokens. Envía el code_verifier para que IdP valide el PKCE.',
      code: { http:
`POST /realms/agent-poc/protocol/openid-connect/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&code=SplxlOBeZQQYbYS6WxSbIA
&redirect_uri=http://client-mock:3000/auth/callback
&client_id=client-mock
&code_verifier=dBjftJeZ4CVP-...` },
      actor: 'mock',
    },
    {
      from: 'idp', to: 'mock',
      kind: 'reply', label: '200 {access_token, refresh_token, id_token}',
      desc: 'El IdP devuelve los 3 tokens. El access_token lleva el scope pedido. El refresh_token puede renovar access_tokens sin nueva pantalla de login.',
      code: { json:
`{
  "access_token":  "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiJ9...",
  "id_token":      "eyJhbGciOiJSUzI1NiIs...",
  "expires_in":    300,
  "token_type":    "Bearer",
  "scope":         "openid profile email calendar.read"
}`,
      claims: {
        iss: 'http://keycloak:8080/realms/agent-poc',
        sub: 'f8a1d3e2-1b9c-4a8a-9e7f-...  (UUID de Ana)',
        aud: ['agente-ia', 'spring-boot-api', 'account'],
        azp: 'agente-ia',
        scope: 'openid profile email calendar.read',
        exp: 'now + 300s',
        iat: 'now',
        acr: '1', // KC normal; B2C Passkey ser\u00eda '2'
      } },
      actor: 'idp',
    },
    {
      from: 'mock', to: 'cliente',
      kind: 'reply', label: 'devuelve tokens al cliente',
      desc: 'La webapp entrega los tokens al cliente por sesión segura o canal out-of-band.',
      actor: 'mock',
    },
    {
      from: 'cliente', to: 'agente',
      kind: 'sync', label: 'POST /agente/call  {access_token, request, scope}',
      desc: 'El cliente pasa al agente el access_token para que ejecute la acción pedida.',
      actor: 'cliente',
    },
    {
      from: 'agente', to: 'api',
      kind: 'sync', label: 'GET /api/calendar/events  Bearer <token>',
      desc: 'El agente llama al Resource Server con el JWT. Spring valida la firma contra la JWKS del IdP y el scope via @PreAuthorize("hasAuthority(\'SCOPE_calendar.read\')").',
      code: { http:
`GET /api/calendar/events?user_id=ana HTTP/1.1
Host: spring-boot-api:9090
Authorization: Bearer eyJhbGciOi...` },
      actor: 'agente',
    },
    {
      from: 'api', to: 'agente',
      kind: 'reply', label: '200 {events: [...]}',
      desc: 'Spring devuelve los eventos del calendario. Loguea [AUDIT] con sub y azp para trazabilidad.',
      code: { json:
`{
  "user": "Ana Garc\u00eda",
  "events": [
    { "title": "Daily con Vicedo", "when": "2026-07-08T09:00Z" },
    { "title": "Review PR #482",   "when": "2026-07-08T16:30Z" }
  ]
}` },
      actor: 'api',
    },
  ],
};

// ============== FLUJO B: Device Code ==============
export const flowB = {
  id: 'B',
  title: 'Flujo B — Device Code',
  meta: 'RFC 8628 · ~8 mensajes · agente headless · polling cada 5s',
  actors: [
    actor('cliente','Cliente / CLI / CI',  'headless',         '#a5b4fc'),
    actor('agente', 'Agente IA',           'FastAPI :7000',    '#7e83ff'),
    actor('idp',    'Keycloak / B2C',      'Authorization',    '#5eead4'),
    actor('user',   'Humano (Ana)',        'smartphone / port\u00e1til','#fde68a'),
    actor('api',    'Spring Boot API',     'Resource :9090',   '#fb7185'),
  ],
  steps: [
    {
      from: 'cliente', to: 'agente',
      kind: 'sync', label: 'POST /agente/auth/device  {user_id, scope}',
      desc: 'El cliente (CLI / CI) pide al agente que obtenga un device_code. No hay navegador del humano cerca.',
      code: { bash: curlB(), python:
`resp = requests.post(
  "http://localhost:7000/agente/auth/device",
  json={"user_id":"ana",
        "scope":"openid profile email calendar.read"},
).json()` },
      actor: 'agente',
    },
    {
      from: 'agente', to: 'idp',
      kind: 'sync', label: 'POST /ext/ciba/auth/device_authorization',
      desc: 'El agente pide un device_code al IdP. Algunos IdP exponen el endpoint en /protocol/openid-connect/auth/device (KC) o en /oauth2/v2.0/devicecode (B2C).',
      code: { http:
`POST /realms/agent-poc/protocol/openid-connect/auth/device HTTP/1.1
Content-Type: application/x-www-form-urlencoded

client_id=agente-ia
&client_secret=secret-del-agente
&scope=openid+profile+email+calendar.read` },
      actor: 'agente',
    },
    {
      from: 'idp', to: 'agente',
      kind: 'reply', label: '200 {device_code, user_code, verification_uri}',
      desc: 'El IdP devuelve los códigos. user_code es legible para el humano; device_code es secreto que solo intercambia el agente.',
      code: { json:
`{
  "device_code":               "GmRhmhcxhwAzkoEqiMEg_DnyEysNkuNhszIySk9eS",
  "user_code":                 "ABCD-1234",
  "verification_uri":          "http://localhost:8180/realms/agent-poc/device",
  "verification_uri_complete": "http://localhost:8180/realms/agent-poc/device?user_code=ABCD-1234",
  "expires_in":                600,
  "interval":                  5
}` },
      actor: 'idp',
    },
    {
      from: 'agente', to: 'cliente',
      kind: 'reply', label: 'imprime user_code + verification_uri',
      desc: 'El agente imprime en pantalla para el operador del CLI:\n  "Ve a http://idp/device e introduce: ABCD-1234"',
      code: { bash:
`$ ./agente-cli
[Agente IA] device_code = GmRhmhcxhwA...
[Agente IA] user_code   = ABCD-1234
[Agente IA] URL         = http://localhost:8180/realms/agent-poc/device
[Agente IA] Esperando aprobaci\u00f3n (expira en 600s)...` },
      actor: 'agente',
    },
    {
      from: 'user', to: 'idp',
      kind: 'sync', label: 'GET /device → introduce user_code → Approve',
      desc: 'En otro dispositivo, el humano introduce user_code y aprueba. Importante: NO toca password. Solo confirmación.',
      code: { note:
'Pantalla del IdP:\n  Tu c\u00f3digo: ABCD-1234\n  [ Approve ]   [ Deny ]' },
      actor: 'user',
    },
    {
      from: 'agente', to: 'idp',
      kind: 'sync', label: 'POLLING POST /token  (cada interval=5s)',
      desc: 'Mientras tanto el agente hace polling al endpoint /token del IdP. Si el humano ya aprobó, recibe tokens; si no, recibe authorization_pending.',
      code: { http:
`POST /realms/agent-poc/protocol/openid-connect/token HTTP/1.1

grant_type=urn:ietf:params:oauth:grant-type:device_code
&device_code=GmRhmhcxhwA...
&client_id=agente-ia
&client_secret=secret-del-agente

# Respuestas posibles:
# 200  {access_token,...}                   \u2190 OK
# 400  {error: "authorization_pending"}     \u2190 seguir polling
# 400  {error: "slow_down"}                 \u2190 subir interval
# 400  {error: "access_denied"}             \u2190 parar
# 400  {error: "expired_token"}             \u2190 device_code caducado` },
      actor: 'agente',
    },
    {
      from: 'idp', to: 'agente',
      kind: 'reply', label: '200 {access_token, refresh_token, id_token}',
      desc: 'El IdP devuelve tokens ya con el scope pedido y el sub del humano que aprobó.',
      code: { json:
`{ "access_token":  "eyJ...", "expires_in": 300,
   "refresh_token": "eyJ...",
   "token_type":    "Bearer",
   "scope":         "openid profile email calendar.read" }`,
      claims: {
        iss:   'http://keycloak:8080/realms/agent-poc',
        sub:   'f8a1d3e2-1b9c-4a8a-9e7f-...  (UUID de Ana)',
        aud:   ['agente-ia', 'spring-boot-api'],
        azp:   'agente-ia',
        scope: 'openid profile email calendar.read',
        exp:   'now + 300s',
      } },
      actor: 'idp',
    },
    {
      from: 'agente', to: 'api',
      kind: 'sync', label: 'GET /api/calendar/events',
      desc: 'El agente llama ya con el JWT a la API.',
      actor: 'agente',
    },
    {
      from: 'api', to: 'agente',
      kind: 'reply', label: '200 {events: [...]}',
      desc: 'Devolución normal. Mismo flujo de auditoría que A.',
      actor: 'api',
    },
  ],
};

// ============== FLUJO C: OBO ==============
export const flowC = {
  id: 'C',
  title: 'Flujo C — On-Behalf-Of (RFC 7523)',
  meta: 'Requiere KC 26+ o Azure B2C External ID',
  actors: [
    actor('cliente','Cliente / App',  'tras A o B',            '#a5b4fc'),
    actor('agente', 'Agente IA',       'FastAPI :7000',         '#7e83ff'),
    actor('idp',    'Keycloak 26+ / B2C', 'Authorization',     '#5eead4'),
    actor('api',    'Spring Boot API', 'Resource :9090',        '#fb7185'),
  ],
  steps: [
    {
      from: 'cliente', to: 'agente',
      kind: 'sync', label: 'POST /agente/auth/obo  {user_access_token, requested_scope}',
      desc: 'El cliente ya tiene un access_token del usuario (obtenido vía A o B) pero le falta el scope concreto. Pide al agente un token delegado.',
      code: { bash: curlC() },
      actor: 'agente',
    },
    {
      from: 'agente', to: 'agente',
      kind: 'self', label: 'decodifica JWT (sin verificar firma)',
      desc: 'El agente mira el scope actual del JWT. Si requested_scope ya est\u00e1 dentro, salta el OBO y reutiliza.',
      code: { python:
`import jwt  # PyJWT
claims = jwt.decode(
  user_access_token,
  options={"verify_signature": False},
)
have = set(claims.get("scope","").split())
need = set(requested_scope.split())
missing = need - have
if not missing:
  # ya tengo lo necesario \u2192 no OBO
  return user_access_token` },
      actor: 'agente',
    },
    {
      from: 'agente', to: 'idp',
      kind: 'sync', label: 'POST /token  grant_type=jwt-bearer',
      desc: 'El agente intercambia el JWT del usuario por un nuevo token con scope más limitado. La firma del IdP garantiza que el JWT es válido.',
      code: { http:
`POST /oauth2/v2.0/token HTTP/1.1  # B2C; KC26: /protocol/openid-connect/token
Content-Type: application/x-www-form-urlencoded

grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
&assertion=<user_access_token>
&requested_token_use=on_behalf_of
&requested_scope=email.send
&client_id=agente-ia
&client_secret=secret-del-agente` },
      actor: 'agente',
    },
    {
      from: 'idp', to: 'agente',
      kind: 'reply', label: '200 {access_token refinado}',
      desc: 'El IdP emite un NUEVO access_token con scope=puntual (email.send). Valida la firma del JWT entrante, que la aserción incluye sub del humano.',
      code: { json:
`{
  "access_token": "eyJ... <NUEVO, scope=email.send>",
  "issued_token_type": "urn:ietf:params:oauth:token-type:access_token",
  "token_type":        "Bearer",
  "expires_in":        300,
  "scope":             "email.send"
}`,
      claims: {
        iss:   'https://<tenant>.ciamlogin.com/...',
        sub:   'f8a1d3e2-...  (UUID de Ana)',
        aud:   ['spring-boot-api', 'agente-ia'],
        azp:   'agente-ia',
        scope: 'email.send',                                 // M\u00cdNIMO
        exp:   'now + 300s',
        act:   { sub: 'agente-ia' },                        // act = qui\u00e9n opera
      } },
      actor: 'idp',
    },
    {
      from: 'agente', to: 'api',
      kind: 'sync', label: 'POST /api/email/send  Bearer <refinado>',
      desc: 'El agente llama a Spring con el scope MÍNIMO (email.send). Spring valida id\u00e9ntico.',
      actor: 'agente',
    },
    {
      from: 'api', to: 'agente',
      kind: 'reply', label: '200 {sent: true}',
      desc: 'Acuse de la API. Log: [AUDIT] sub=ana azp=agente-ia scope=email.send.',
      actor: 'api',
    },
  ],
};

export const FLOWS = { A: flowA, B: flowB, C: flowC };
