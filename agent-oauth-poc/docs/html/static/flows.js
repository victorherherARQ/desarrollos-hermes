// ============================================================
//  flows.js - specs declarativos de los 3 flujos
//  Cada step = { from, to, label, kind: 'sync'|'reply'|'self',
//                desc, code:{lang,...}, claims?, actor? }
//
//  Estado (a partir de la decisión operativa del 2026-07-08):
//    Ana está REGISTRADA en el IdP pero NO LOGADA.
//    Ana NO tiene token (llama por teléfono, no navega).
//    El Agente IA es quien la identifica (voz + número entrante).
//    Verificación más segura = móvil cercano (push + biometría).
//    → Flujo C (Voice-Channel Identity + Push Step-Up) es el VIABLE.
//    → A y B no son viables: requieren navegador interactivo del humano,
//      y Ana está hablando por teléfono.
// ============================================================

/** Plantilla para construir un actor con coordenadas calculadas después */
const actor = (id, name, role, color) => ({ id, name, role, color });

/** Helpers curl por flujo - *no* interpolan secretos reales */
const curlC = () => `# Flujo C arranca sin tokens previos.
// La llamada es el primer contacto del humano con el IdP.
# 1) Ana llama al voicebot. El agente la identifica por voz + nº entrante.
#    Aquí no hay curl: la señal es voz sobre PSTN/SIP/Teams.
# 2) El agente pide step-up al IdP (push al móvil de Ana)
curl -s -X POST http://localhost:8180/realms/agent-poc/login-actions/action-token \\
  -H "Content-Type: application/json" \\
  -d '{
    "sub":"f8a1d3e2-...ana",
    "act":"agente-ia",
    "exp":300,
    "scope":"openid email calendar.read"
  }' | jq .`;

// ============== FLUJO A: Auth Code + PKCE - NO VIABLE ==============
export const flowA = {
  id: 'A',
  title: 'Flujo A - Authorization Code + PKCE',
  meta: 'RFC 6749 §4.1 · RFC 7636 · navegador humano interactivo',
  viable: false,
  nonViableReason:
    'Ana está hablando por teléfono. No tiene navegador a mano. ' +
    'Forzarle a abrir URL + login web + MFA durante una llamada de voz ' +
    'rompe la experiencia y aumenta abandono. Requeriría call-transfer ' +
    'o callback que pierde el contexto de la conversación.',
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
      code: { bash:
`# No se ejecutaría en la realidad: Ana no tiene navegador.
# Se conserva como referencia técnica.
curl -s -X POST http://localhost:7000/agente/auth/authorize \\
  -H "Content-Type: application/json" \\
  -d '{"user_id":"ana","scope":"openid profile email calendar.read"}' | jq .` },
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
      code: { note:
'Aqu\\u00ed el humano interact\\u00faa en su navegador.\\nNO aplicable: Ana est\\u00e1 al tel\\u00e9fono.' },
      actor: 'mock',
    },
    {
      from: 'user', to: 'idp',
      kind: 'sync', label: 'login + MFA (Passkey / TOTP)',
      desc: 'El humano teclea usuario + password en el formulario del IdP y completa el MFA. Crucial: el agente nunca ve las credenciales.',
      code: { note:
'Pantalla del IdP:\\n  login + passkey opcional.\\nNO aplicable: Ana est\\u00e1 al tel\\u00e9fono.' },
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
  &state=af0ifjsldkj` },
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
      desc: 'El IdP devuelve los 3 tokens. El access_token lleva el scope pedido.',
      code: { json:
`{
  "access_token":  "eyJhbG...VCJ9...",
  "refresh_token": "eyJhbG...NiJ9...",
  "id_token":      "eyJhbG...NiIs...",
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
        acr: '1',
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
      desc: 'El agente llama al Resource Server con el JWT. Spring valida firma + scope.',
      code: { http:
`GET /api/calendar/events?user_id=ana HTTP/1.1
Host: spring-boot-api:9090
Authorization: Bearer ***` },
      actor: 'agente',
    },
    {
      from: 'api', to: 'agente',
      kind: 'reply', label: '200 {events: [...]}',
      desc: 'Spring devuelve los eventos. Log: [AUDIT] sub=ana azp=agente-ia scope=calendar.read.',
      code: { json:
`{
  "user": "Ana Garc\\u00eda",
  "events": [
    { "title": "Daily con Vicedo", "when": "2026-07-08T09:00Z" }
  ]
}` },
      actor: 'api',
    },
  ],
};

// ============== FLUJO B: Device Code - NO VIABLE ==============
export const flowB = {
  id: 'B',
  title: 'Flujo B - Device Code',
  meta: 'RFC 8628 · agente headless · polling cada 5s',
  viable: false,
  nonViableReason:
    'Aunque Ana podría técnicamente abrir URL y teclear user_code ' +
    'mientras está al teléfono, la fricción es alta: tiene que sacar el móvil, ' +
    'abrir navegador, escribir un código alfanumérico y aprobar. Durante una ' +
    'llamada activa la atención está en la voz - abrir pestañas extra rompe la ' +
    'conversación. Device Code está pensado para TVs, CLIs y CI, no para ' +
    'voicebots con humano en línea.',
  actors: [
    actor('cliente','Cliente / CLI / CI',  'headless',         '#a5b4fc'),
    actor('agente', 'Agente IA',           'FastAPI :7000',    '#7e83ff'),
    actor('idp',    'Keycloak / B2C',      'Authorization',    '#5eead4'),
    actor('user',   'Humano (Ana)',        'smartphone / portátil','#fde68a'),
    actor('api',    'Spring Boot API',     'Resource :9090',   '#fb7185'),
  ],
  steps: [
    {
      from: 'cliente', to: 'agente',
      kind: 'sync', label: 'POST /agente/auth/device  {user_id, scope}',
      desc: 'El cliente (CLI / CI) pide al agente que obtenga un device_code.',
      code: { bash:
`curl -s -X POST http://localhost:7000/agente/auth/device \\
  -H "Content-Type: application/json" \\
  -d '{"user_id":"ana","scope":"openid profile email calendar.read"}' | jq .` },
      actor: 'agente',
    },
    {
      from: 'agente', to: 'idp',
      kind: 'sync', label: 'POST /ext/ciba/auth/device_authorization',
      desc: 'El agente pide un device_code al IdP.',
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
      desc: 'El IdP devuelve los códigos. user_code es legible para el humano; device_code es secreto.',
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
      desc: 'El agente imprime para el operador del CLI: "Ve a http://idp/device e introduce: ABCD-1234"',
      actor: 'agente',
    },
    {
      from: 'user', to: 'idp',
      kind: 'sync', label: 'GET /device → introduce user_code → Approve',
      desc: 'En otro dispositivo, el humano introduce user_code y aprueba. NO toca password, solo confirmación.',
      code: { note:
'Pantalla del IdP:\\n  Tu c\\u00f3digo: ABCD-1234\\n  [ Approve ]   [ Deny ]\\n\\nNO aplicable: Ana est\\u00e1 al tel\\u00e9fono.' },
      actor: 'user',
    },
    {
      from: 'agente', to: 'idp',
      kind: 'sync', label: 'POLLING POST /token  (cada interval=5s)',
      desc: 'Mientras tanto el agente hace polling al endpoint /token del IdP.',
      code: { http:
`POST /realms/agent-poc/protocol/openid-connect/token HTTP/1.1

grant_type=urn:ietf:params:oauth:grant-type:device_code
&device_code=GmRhmhcxhwA...
&client_id=agente-ia
&client_secret=secret-del-agente

# Respuestas posibles:
# 200  {access_token,...}                    OK
# 400  {error: "authorization_pending"}      seguir polling
# 400  {error: "slow_down"}                  subir interval
# 400  {error: "access_denied"}              parar
# 400  {error: "expired_token"}              device_code caducado` },
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

// ============== FLUJO C: Voice-Channel Identity + JWT Bearer + Push Step-Up - VIABLE ==============
// Modelo operacional:
//   • Ana REGISTRADA en el IdP (tiene sub, mobile vinculado, biometría).
//   • Ana NO logada. NO tiene token. Llama por teléfono.
//   • Agente IA identifica a Ana por voz (voiceprint) + nº entrante
//     (matching con la agenda interna del agente).
//   • Agente pide al IdP step-up vía push al móvil de Ana.
//   • Ana confirma con biometría (FaceID / huella) en su móvil.
//   • IdP emite access_token con sub=ana, act=agente-ia, acr=phone-voice+push.
//   • Agente llama a la API con ese token.
//
// Estándares: RFC 7521/7523 (JWT Bearer Assertion), CIBA-style step-up,
//             OAuth 2.0 Token Exchange (RFC 8693) para el "act" claim.
export const flowC = {
  id: 'C',
  title: 'Flujo C - Voice-Channel Identity + Push Step-Up',
  meta: 'RFC 7521/7523 · RFC 8693 · CIBA-style · voicebot + push al móvil',
  viable: true,
  nonViableReason: null,
  actors: [
    actor('user',   'Humano (Ana)',         'voz (llamada) + push al móvil',  '#fde68a'),
    actor('agente', 'Agente IA',            'voicebot :7000',                '#7e83ff'),
    actor('idp',    'Keycloak 24+ / B2C',   'Authorization + Push broker',   '#5eead4'),
    actor('mobile', 'Móvil de Ana',         'app nativa · biometría',        '#a78bfa'),
    actor('api',    'Spring Boot API',      'Resource :9090',                '#fb7185'),
  ],
  steps: [
    {
      from: 'user', to: 'agente',
      kind: 'sync', label: 'Llamada entrante (PSTN/SIP/Teams)',
      desc: 'Ana marca al número del call-center. La PBX enruta al Agente IA. NO hay canal web. Ana está registrada pero NO logada en el IdP.',
      code: { note:
'Canal: voz sobre SIP/PSTN/Teams Voice.\\nIdentificadores:\\n  - n\\u00famero origen: +34 600 000 000\\n  - voiceprint (enrollment previo)\\nAna NO presenta token. NO tiene navegador.\\nEstado IdP: NO autenticada.' },
      actor: 'agente',
    },
    {
      from: 'agente', to: 'agente',
      kind: 'self', label: 'identifica Ana (voz + nº entrante + voiceprint)',
      desc: 'El agente corre matching en 2 niveles: (1) número entrante → entrada de la agenda interna, (2) voiceprint contra el enrollment para confirmar. Si voiceprint > umbral → candidato único = Ana. Si no → escalado a humano.',
      code: { python:
`# internamente, en el agente
candidates = crm.lookup_by_phone(caller_id)   # +34 600 000 000 → 1 contacto
score = voiceprint.verify(stream, candidates)  # cosine sim > 0.92
if score > 0.92:
    user = candidates[0]   # Ana
else:
    transfer_to_human()    # baja confianza` },
      actor: 'agente',
    },
    {
      from: 'agente', to: 'idp',
      kind: 'sync', label: 'POST /token  grant_type=password  +  x-voice-assertion',
      desc: 'El agente (cliente confidencial) pide un token al IdP SIN password de Ana. Demuestra identidad con su client_secret Y firma un JWT de "voice assertion" que dice: sub=ana, voice_verified=true, acr=phone-voice. El IdP debe tener un protocol mapper que acepte esta assertion.',
      code: { http:
`POST /realms/agent-poc/protocol/openid-connect/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded
X-Voice-Assertion: eyJhbG...NiIs...  // JWT firmado por el agente

grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
&assertion=<voice-assertion-jwt>
&requested_token_type=urn:ietf:params:oauth:token-type:access_token
&scope=openid+email+calendar.read
&client_id=agente-ia
&client_secret=secret-del-agente

// OJO: NO se envia password de Ana.
// El agente firma una "voice assertion" en su lugar:
//   iss = agente-ia
//   sub = f8a1d3e2-...ana
//   aud = https://idp/realms/agent-poc
//   iat = 1751990000
//   exp = 1751990120  (2 minutos)
//   auth_time = 1751990000
//   acr = phone-voice
//   voiceprint_score = 0.94
//   caller_phone = +34...0
` },
      actor: 'agente',
    },
    {
      from: 'idp', to: 'idp',
      kind: 'self', label: 'verifica firma del agente + estado de Ana',
      desc: 'El IdP hace 4 checks: (1) la voice-assertion está firmada por el agente-ia, (2) no está expirada, (3) Ana está registrada y activa en el realm, (4) el agente-ia tiene scope permitido para actuar en nombre de Ana. Si todo OK → emite token "preliminar" + lanza push al móvil de Ana.',
      code: { note:
'Checks IdP:\\n  [x] firma del agent-ia v\\u00e1lida (JWKS interna)\\n  [x] assertion no expirada\\n  [x] Ana existe y est\\u00e1 activa\\n  [x] agent-ia tiene scope para sub=ana\\n  [x] liveness challenge pendiente (push)' },
      actor: 'idp',
    },
    {
      from: 'idp', to: 'mobile',
      kind: 'sync', label: 'PUSH "Agente IA quiere actuar en tu nombre"',
      desc: 'El IdP manda push al móvil de Ana (vía APNs/FCM o Keycloak mobile broker). Mensaje: "Agente IA está hablando contigo. ¿Le autorizas a consultar tu calendario y enviar emails en tu nombre?"',
      code: { json:
`# notificación push (APNs / FCM payload)
{
  "title":       "Agente IA · autorización",
  "body":        "¿Autorizas al agente a leer tu calendario?",
  "ttl":         120,
  "action_url":  "universal://oauth/approve?ctx=ciba-1f2e3d4c",
  "actions":     ["Approve", "Deny"],
  "challenge":   "abc123"
}` },
      actor: 'mobile',
    },
    {
      from: 'mobile', to: 'user',
      kind: 'sync', label: 'FaceID / huella + tap "Approve"',
      desc: 'Ana mira la notificación en su móvil (que tiene en la mano mientras habla), confirma con biometría, y toca Approve. El móvil manda al IdP el challenge firmado por el device-bound key.',
      code: { note:
'Pantalla del m\\u00f3vil:\\n  "Agente IA est\\u00e1 hablando contigo.\\n   \\u00bfLe autorizas?\\n   [ FaceID ]   [ Deny ]"' },
      actor: 'user',
    },
    {
      from: 'mobile', to: 'idp',
      kind: 'sync', label: 'POST /ext/ciba/auth/device  (challenge firmado)',
      desc: 'El móvil envía al IdP la aprobación firmada con la clave del dispositivo. Esto actúa como segundo factor (algo que tienes = el móvil, algo que eres = la cara/huella).',
      code: { http:
`POST /realms/agent-poc/ext/ciba/auth/device HTTP/1.1
Content-Type: application/json

{
  "ctx":      "ciba-1f2e3d4c",
  "decision": "approve",
  "device_assertion": "eyJ...firma-con-device-key...",
  "biometric_used":   "faceid",
  "ts": 1751990042
}` },
      actor: 'mobile',
    },
    {
      from: 'idp', to: 'agente',
      kind: 'reply', label: '200 {access_token, refresh_token, id_token}',
      desc: 'El IdP valida la aprobación del móvil y emite el token DEFINITIVO. acr sube a "phone-voice+push-biometric" → cumple requisitos de SCA fuerte (PSD2) y NIST AAL2/AAL3.',
      code: { json:
`{
  "access_token":  "eyJ... <NUEVO>",
  "refresh_token": "eyJ... <NUEVO>",
  "id_token":      "eyJ... <NUEVO>",
  "expires_in":    300,
  "token_type":    "Bearer",
  "scope":         "openid email calendar.read"
}`,
      claims: {
        iss:        'http://keycloak:8080/realms/agent-poc',
        sub:        'f8a1d3e2-1b9c-4a8a-9e7f-...  (UUID de Ana)',
        aud:        ['agente-ia', 'spring-boot-api'],
        azp:        'agente-ia',
        scope:      'openid email calendar.read',
        exp:        'now + 300s',
        iat:        'now',
        auth_time:  'now',
        acr:        'phone-voice+push-biometric',     // AAL3-style
        amr:        ['voice', 'push', 'faceid'],      // multi-factor
        act:        { sub: 'agente-ia' },             // RFC 8693: quién actúa
        voice_score: 0.94,                           // opcional
        caller_phone: '+34...0',                     // opcional
      } },
      actor: 'idp',
    },
    {
      from: 'agente', to: 'api',
      kind: 'sync', label: 'GET /api/calendar/events  Bearer <token>',
      desc: 'El agente llama a la API con el JWT. Spring valida: firma OK, sub=ana, act=agente-ia, scope=calendar.read. Log: [AUDIT] voice-verified + push-approved.',
      code: { http:
`GET /api/calendar/events?user_id=ana HTTP/1.1
Host: spring-boot-api:9090
Authorization: Bearer ***
X-Original-Channel: voice
X-Original-Actor:   ana` },
      actor: 'agente',
    },
    {
      from: 'api', to: 'agente',
      kind: 'reply', label: '200 {events: [...]}',
      desc: 'Spring devuelve los eventos. El agente responde a Ana por voz: "tienes 3 eventos hoy: …"',
      code: { json:
`{
  "user": "Ana Garc\\u00eda",
  "events": [
    { "title": "Daily con Vicedo", "when": "2026-07-08T09:00Z" },
    { "title": "Review PR #482",   "when": "2026-07-08T16:30Z" }
  ]
}` },
      actor: 'api',
    },
  ],
};

export const FLOWS = { A: flowA, B: flowB, C: flowC };
