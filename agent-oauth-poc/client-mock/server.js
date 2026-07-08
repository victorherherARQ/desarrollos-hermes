/**
 * Client Mock — Simula el móvil del usuario recibiendo CIBA push notifications.
 *
 * Keycloak (con CIBA habilitado) hace POST /ciba/notify cuando un agente
 * solicita un token con scopes sensibles. Esta UI mock recibe la notificación,
 * la encola en memoria y permite al usuario aprobar/rechazar desde una
 * interfaz web tipo móvil.
 *
 * IMPORTANTE: Esto es solo UI para la PoC. La autenticación real del
 * usuario (biometría, PIN, etc.) sería responsabilidad de la app móvil
 * real en producción. Aquí simplemente seleccionas tu identidad en el
 * selector dropdown.
 */

const express = require('express');
const bodyParser = require('body-parser');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// ──────────────────────────────────────────────────────────────────
// Middleware
// ──────────────────────────────────────────────────────────────────
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, 'public')));

// ──────────────────────────────────────────────────────────────────
// Estado en memoria: notificaciones CIBA pendientes / resueltas
// ──────────────────────────────────────────────────────────────────
/**
 * Estructura de cada elemento:
 * {
 *   auth_req_id:   string   // Identificador único de la petición CIBA
 *   user:          string   // Usuario al que va dirigida ('ana', 'luis', 'marta')
 *   scope:         string   // Scopes solicitados, ej: 'calendar.read email.send'
 *   agent:         string   // Nombre/identificador del agente que pide
 *   request_text:  string   // Texto legible de lo que pide el agente
 *   expires_at:    number   // Timestamp UNIX de expiración
 *   requested_at:  number   // Timestamp UNIX de cuándo se recibió la notificación
 *   status:        'pending' | 'approved' | 'rejected'
 * }
 */
const pendingRequests = [];

// ──────────────────────────────────────────────────────────────────
// Logging helper
// ──────────────────────────────────────────────────────────────────
function log(...args) {
  const ts = new Date().toISOString();
  console.log(`[${ts}] [client-mock]`, ...args);
}

// ──────────────────────────────────────────────────────────────────
// POST /ciba/notify
// Keycloak llama aquí cuando hay una nueva CIBA backchannel notification.
// ──────────────────────────────────────────────────────────────────
app.post('/ciba/notify', (req, res) => {
  const {
    auth_req_id,
    user,
    scope,
    agent,
    request_text,
    expires_at,
  } = req.body || {};

  if (!auth_req_id || !user) {
    log('⚠ /ciba/notify recibido SIN auth_req_id o user:', req.body);
    return res.status(400).json({
      ok: false,
      error: 'auth_req_id and user are required',
    });
  }

  const entry = {
    auth_req_id,
    user,
    scope: scope || '',
    agent: agent || 'agente-ia',
    request_text: request_text || `Acceso a ${scope || 'recurso protegido'}`,
    expires_at: expires_at || (Date.now() / 1000) + 120,
    requested_at: Math.floor(Date.now() / 1000),
    status: 'pending',
  };

  // Evitar duplicados (reintentos de Keycloak)
  const existing = pendingRequests.find((r) => r.auth_req_id === auth_req_id);
  if (existing) {
    log(`⚠ Notificación duplicada para auth_req_id=${auth_req_id}, ignorando.`);
    return res.json({ ok: true, duplicate: true });
  }

  pendingRequests.push(entry);
  log(
    `📩 Nueva notificación CIBA: user=${user} agent=${entry.agent} ` +
      `scope=${entry.scope} auth_req_id=${auth_req_id}`
  );

  return res.json({ ok: true, auth_req_id });
});

// ──────────────────────────────────────────────────────────────────
// GET /api/pending-requests?user=ana
// Devuelve las notificaciones pendientes para un usuario concreto
// (incluye también las recién aprobadas/rechazadas para que la UI
//  pueda hacer fade out).
// ──────────────────────────────────────────────────────────────────
app.get('/api/pending-requests', (req, res) => {
  const user = req.query.user;
  if (!user) {
    return res.status(400).json({ ok: false, error: 'user query param required' });
  }

  const items = pendingRequests
    .filter((r) => r.user === user)
    .map((r) => ({
      auth_req_id: r.auth_req_id,
      scope: r.scope,
      agent: r.agent,
      request_text: r.request_text,
      requested_at: r.requested_at,
      status: r.status,
    }));

  return res.json({ ok: true, items });
});

// ──────────────────────────────────────────────────────────────────
// POST /approve { auth_req_id }
// Marca la request como aprobada.
// ──────────────────────────────────────────────────────────────────
app.post('/approve', (req, res) => {
  const { auth_req_id } = req.body || {};
  if (!auth_req_id) {
    return res.status(400).json({ ok: false, error: 'auth_req_id required' });
  }

  const entry = pendingRequests.find((r) => r.auth_req_id === auth_req_id);
  if (!entry) {
    return res.status(404).json({ ok: false, error: 'auth_req_id not found' });
  }

  if (entry.status !== 'pending') {
    return res
      .status(409)
      .json({ ok: false, error: `already ${entry.status}`, status: entry.status });
  }

  entry.status = 'approved';
  entry.resolved_at = Math.floor(Date.now() / 1000);
  log(`✅ Aprobada auth_req_id=${auth_req_id} user=${entry.user} agent=${entry.agent}`);

  return res.json({ ok: true, status: 'approved', auth_req_id });
});

// ──────────────────────────────────────────────────────────────────
// POST /reject { auth_req_id }
// Marca la request como rechazada.
// ──────────────────────────────────────────────────────────────────
app.post('/reject', (req, res) => {
  const { auth_req_id } = req.body || {};
  if (!auth_req_id) {
    return res.status(400).json({ ok: false, error: 'auth_req_id required' });
  }

  const entry = pendingRequests.find((r) => r.auth_req_id === auth_req_id);
  if (!entry) {
    return res.status(404).json({ ok: false, error: 'auth_req_id not found' });
  }

  if (entry.status !== 'pending') {
    return res
      .status(409)
      .json({ ok: false, error: `already ${entry.status}`, status: entry.status });
  }

  entry.status = 'rejected';
  entry.resolved_at = Math.floor(Date.now() / 1000);
  log(`❌ Rechazada auth_req_id=${auth_req_id} user=${entry.user} agent=${entry.agent}`);

  return res.json({ ok: true, status: 'rejected', auth_req_id });
});

// ──────────────────────────────────────────────────────────────────
// GET /healthz — healthcheck para docker-compose / k8s
// ──────────────────────────────────────────────────────────────────
app.get('/healthz', (req, res) => {
  res.json({ status: 'UP' });
});

// ──────────────────────────────────────────────────────────────────
// 404 handler
// ──────────────────────────────────────────────────────────────────
app.use((req, res) => {
  res.status(404).json({ ok: false, error: 'not found', path: req.path });
});

// ──────────────────────────────────────────────────────────────────
// Arrancar
// ──────────────────────────────────────────────────────────────────
app.listen(PORT, '0.0.0.0', () => {
  log(`📱 Client Mock escuchando en http://0.0.0.0:${PORT}`);
  log(`   UI móvil:    http://localhost:${PORT}/`);
  log(`   Healthcheck: http://localhost:${PORT}/healthz`);
  log(`   Notify hook: POST http://localhost:${PORT}/ciba/notify`);
});