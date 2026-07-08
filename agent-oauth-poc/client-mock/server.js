/**
 * Client Mock — Webapp Auth Code + PKCE (flujo A) y Device Code (flujo B).
 *
 * VERSIÓN 2.0: ya no es un receptor CIBA. Ahora es una webapp que:
 *  - actúa como el "móvil del usuario"
 *  - hace Auth Code + PKCE contra el IdP (flujo A) — ESTO ES LO PRINCIPAL
 *  - muestra los códigos del Device Code Flow (flujo B) al humano
 *  - entrega el access_token al agente vía API interna (POST /agente/call)
 *
 * No almacena credenciales. El humano escribe su password SOLO en la
 * página de login del IdP (Keycloak / Azure B2C), nunca aquí.
 */

const express = require('express');
const bodyParser = require('body-parser');
const path = require('path');
const crypto = require('crypto');
const querystring = require('querystring');

const app = express();
const PORT = process.env.PORT || 3000;

// ─── Config (env-driven) ──────────────────────────────────────────────────
const IDP_ISSUER = process.env.IDP_ISSUER || 'http://localhost:8180/realms/agent-poc';
const IDP_ISSUER_LC = IDP_ISSUER.toLowerCase();
const IS_B2C = IDP_ISSUER_LC.includes('ciamlogin.com') || IDP_ISSUER_LC.includes('b2clogin.com');

const AGENT_URL = process.env.AGENT_URL || 'http://agent-python:7000';
const AGENT_CLIENT_ID = process.env.AGENT_CLIENT_ID || 'agente-ia';
const B2C_USER_FLOW = process.env.B2C_USER_FLOW || 'signup_signin_v1';

let AUTHORIZE_ENDPOINT, TOKEN_ENDPOINT, USERINFO_ENDPOINT, LOGOUT_ENDPOINT;
if (IS_B2C) {
  AUTHORIZE_ENDPOINT = `${IDP_ISSUER.replace(/\/$/, '')}/oauth2/v2.0/authorize?p=${B2C_USER_FLOW}`;
  TOKEN_ENDPOINT = `${IDP_ISSUER.replace(/\/$/, '')}/oauth2/v2.0/token`;
  USERINFO_ENDPOINT = 'https://graph.microsoft.com/oidc/userinfo';
  LOGOUT_ENDPOINT = `${IDP_ISSUER.replace(/\/$/, '')}/oauth2/v2.0/logout`;
} else {
  AUTHORIZE_ENDPOINT = `${IDP_ISSUER.replace(/\/$/, '')}/protocol/openid-connect/auth`;
  TOKEN_ENDPOINT = `${IDP_ISSUER.replace(/\/$/, '')}/protocol/openid-connect/token`;
  USERINFO_ENDPOINT = `${IDP_ISSUER.replace(/\/$/, '')}/protocol/openid-connect/userinfo`;
  LOGOUT_ENDPOINT = `${IDP_ISSUER.replace(/\/$/, '')}/protocol/openid-connect/logout`;
}

// ─── Middleware ────────────────────────────────────────────────────────────
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, 'public')));

// ─── Session store en memoria (PoC; en prod: Redis) ──────────────────────
const sessions = new Map();
function makeSession() {
  return {
    created: Date.now(),
    access_token: null,
    refresh_token: null,
    id_token: null,
    user: null,
    pkce: null,        // {code_verifier, state}
  };
}
function log(...args) {
  const ts = new Date().toISOString();
  console.log(`[${ts}] [client-mock]`, ...args);
}

// ────────────────────────────────────────────────────────────────────────
// 1. INICIO DEL FLUJO A — el agente nos llama aquí
//    Devolvemos: { authorize_url, code_verifier, state, session_id }
// ────────────────────────────────────────────────────────────────────────
app.post('/auth/authorize', async (req, res) => {
  const { scope, acr_values, session_id } = req.body || {};
  if (!scope) {
    return res.status(400).json({ ok: false, error: 'scope required' });
  }
  const sid = session_id || crypto.randomUUID();
  const session = sessions.get(sid) || makeSession();
  sessions.set(sid, session);

  // Generamos PKCE aquí (en lugar del agente) para que el verifier se
  // quede del lado "cliente público" (client-mock).
  const code_verifier = base64url(crypto.randomBytes(32));
  const code_challenge = base64url(
    crypto.createHash('sha256').update(code_verifier).digest()
  );
  const state = base64url(crypto.randomBytes(16));

  session.pkce = { code_verifier, state };

  const params = {
    response_type: 'code',
    client_id: AGENT_CLIENT_ID,
    scope: scope,
    state: state,
    code_challenge: code_challenge,
    code_challenge_method: 'S256',
    redirect_uri: `${getBaseUrl(req)}/auth/callback`,
  };
  if (acr_values) params.acr_values = acr_values;

  const authorize_url = `${AUTHORIZE_ENDPOINT}?${querystring.stringify(params)}`;
  log(`[A] session=${sid.slice(0, 8)}... scope=${scope} state=${state.slice(0, 8)}...`);

  res.json({
    ok: true,
    session_id: sid,
    authorize_url,
    code_verifier,  // el agente lo necesita para /auth/token (vía POST)
    state,
  });
});

// ────────────────────────────────────────────────────────────────────────
// 2. CALLBACK del IdP — el humano vuelve aquí con ?code=...&state=...
//    Intercambiamos el code por tokens (con client_secret del agente)
// ────────────────────────────────────────────────────────────────────────
app.get('/auth/callback', async (req, res) => {
  const { code, state, error, error_description } = req.query;
  if (error) {
    log(`[A] callback error: ${error} -- ${error_description}`);
    return res.redirect(
      `/?error=${encodeURIComponent(error)}&` +
      `error_description=${encodeURIComponent(error_description || '')}`
    );
  }
  if (!code || !state) {
    return res.status(400).send('Faltan parámetros en el callback');
  }
  // Buscar la sesión por state
  let sid = null;
  for (const [k, v] of sessions.entries()) {
    if (v.pkce && v.pkce.state === state) {
      sid = k;
      break;
    }
  }
  if (!sid) {
    return res.status(400).send(`state inválido o expirado: ${state}`);
  }
  const session = sessions.get(sid);
  const { code_verifier } = session.pkce;
  const redirect_uri = `${getBaseUrl(req)}/auth/callback`;

  log(`[A] session=${sid.slice(0, 8)}... code=${code.slice(0, 16)}... exchanging...`);

  try {
    const tokenResp = await fetch(TOKEN_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: querystring.stringify({
        grant_type: 'authorization_code',
        client_id: AGENT_CLIENT_ID,
        client_secret: process.env.AGENT_CLIENT_SECRET || 'secret-del-agente',
        code,
        code_verifier,
        redirect_uri,
      }),
    });
    if (!tokenResp.ok) {
      const errText = await tokenResp.text();
      log(`[A] token exchange failed: HTTP ${tokenResp.status} -- ${errText}`);
      return res.redirect(`/?error=token_exchange_failed&detail=${encodeURIComponent(errText)}`);
    }
    const tokens = await tokenResp.json();
    session.access_token = tokens.access_token;
    session.refresh_token = tokens.refresh_token;
    session.id_token = tokens.id_token;
    session.expires_at = Date.now() + (tokens.expires_in || 300) * 1000;
    log(`[A] session=${sid.slice(0, 8)}... tokens obtained: scope=${tokens.scope}`);

    // UserInfo (opcional, para mostrar nombre)
    if (tokens.access_token) {
      try {
        const ui = await fetch(USERINFO_ENDPOINT, {
          headers: { Authorization: `Bearer ${tokens.access_token}` },
        });
        if (ui.ok) session.user = await ui.json();
      } catch (e) {
        log(`[A] userinfo failed: ${e.message}`);
      }
    }

    res.redirect(`/?session_id=${sid}&auth=ok`);
  } catch (e) {
    log(`[A] exchange error: ${e.message}`);
    res.redirect(`/?error=exchange_failed&detail=${encodeURIComponent(e.message)}`);
  }
});

// ────────────────────────────────────────────────────────────────────────
// 3. El agente (o un test) consulta los tokens de una sesión
// ────────────────────────────────────────────────────────────────────────
app.get('/auth/session/:sid', (req, res) => {
  const sid = req.params.sid;
  const session = sessions.get(sid);
  if (!session || !session.access_token) {
    return res.status(404).json({ ok: false, error: 'session not found or not authed' });
  }
  res.json({
    ok: true,
    access_token: session.access_token,
    refresh_token: session.refresh_token,
    id_token: session.id_token,
    user: session.user,
    expires_at: session.expires_at,
  });
});

// ────────────────────────────────────────────────────────────────────────
// 4. Endpoint de healthcheck
// ────────────────────────────────────────────────────────────────────────
app.get('/healthz', (req, res) => {
  res.json({ status: 'UP', idp: IDP_ISSUER, is_b2c: IS_B2C });
});

// ────────────────────────────────────────────────────────────────────────
// 5. Device Code Flow (flujo B) — UI que muestra el código al humano
// ────────────────────────────────────────────────────────────────────────
app.get('/device', (req, res) => {
  const { user_code, verification_uri, expires_in } = req.query;
  if (!user_code) return res.status(400).send('Faltan parámetros');
  res.send(`
    <!doctype html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <title>Dispositivo pendiente de aprobación</title>
      <style>
        body { font-family: system-ui; max-width: 480px; margin: 60px auto; padding: 20px; text-align: center; }
        .code { font-size: 2.5em; font-family: 'Courier New', monospace; background: #f0f0f0; padding: 20px; border-radius: 8px; letter-spacing: 4px; margin: 20px 0; }
        a { display: inline-block; margin-top: 20px; padding: 14px 28px; background: #0066cc; color: white; border-radius: 6px; text-decoration: none; font-weight: bold; }
        .timer { color: #888; margin-top: 20px; }
      </style>
    </head>
    <body>
      <h1>📱 Aprueba este dispositivo</h1>
      <p>Ve a este enlace desde tu móvil/PC e introduce el código:</p>
      <p><a href="${verification_uri}" target="_blank">${verification_uri}</a></p>
      <div class="code">${user_code}</div>
      <p class="timer">Este código expira en <span id="timer">${expires_in}</span> segundos.</p>
      <script>
        let t = ${expires_in};
        setInterval(() => {
          t--;
          document.getElementById('timer').textContent = t;
          if (t <= 0) location.reload();
        }, 1000);
      </script>
    </body>
    </html>
  `);
});

// ────────────────────────────────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────────────────────────────────
function base64url(buf) {
  return buf.toString('base64')
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}
function getBaseUrl(req) {
  // Para PoC: usar header Host. En prod detrás de proxy: usar X-Forwarded-Proto/Host.
  const proto = req.headers['x-forwarded-proto'] || req.protocol;
  const host = req.headers['x-forwarded-host'] || req.headers.host;
  return `${proto}://${host}`;
}

// 404 handler
app.use((req, res) => {
  res.status(404).json({ ok: false, error: 'not found', path: req.path });
});

app.listen(PORT, '0.0.0.0', () => {
  log(`🌐 Client Mock escuchando en http://0.0.0.0:${PORT}`);
  log(`   IdP issuer:    ${IDP_ISSUER}  (B2C=${IS_B2C})`);
  log(`   Agent URL:     ${AGENT_URL}`);
  log(`   Authorize URL: ${AUTHORIZE_ENDPOINT}`);
  log(`   UI:            http://localhost:${PORT}/`);
  log(`   Device page:   http://localhost:${PORT}/device?user_code=...&verification_uri=...`);
});
