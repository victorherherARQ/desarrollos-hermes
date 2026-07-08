# A+B+C Flow Studio

Diagrama de actores **dinámico e interactivo** (JavaScript puro, sin frameworks) de los 3 flujos OAuth/OIDC que implementa la PoC `agent-oauth-poc`:

- **A** — Authorization Code + PKCE (RFC 6749 §4.1 + RFC 7636) — **NO VIABLE**
- **B** — Device Code (RFC 8628) — **NO VIABLE**
- **C** — Voice-Channel Identity + JWT Bearer Assertion + Push Step-Up (RFC 7521/7523 + RFC 8693) — **VIABLE** ✅

## 🟢 Decisión de viabilidad (turno 2026-07-08)

**Escenario real**: Ana está registrada en el IdP pero **no está logada**. Ana **no tiene token** porque llama por **teléfono** (no navega). El **agente IA la identifica por voz + número entrante + voiceprint**. Ana está **cerca de su móvil** (push + biometría como step-up).

| Flujo | ¿Por qué no? | Resumen |
|---|---|---|
| **A** (Auth Code + PKCE) | ❌ NO viable | Requiere navegador interactivo. Ana está en llamada de voz, no tiene pantalla para login web + MFA. Forzar URL + login rompe la conversación. |
| **B** (Device Code) | ❌ NO viable | Aunque Ana podría abrir URL y teclear `user_code` mientras habla, fricción alta (sacar móvil, abrir navegador, escribir código, aprobar). Pensado para TVs/CLIs/CI, no voicebots. |
| **C** (Voz + Push) | ✅ Viable | Canal de voz para Ana (su canal natural). Solo un toque + biometría en el móvil (que ya tiene en la mano). Agente autenticado vía JWT firmado. **El único flujo que respeta el canal de entrada y la seguridad esperada**. |

**C en detalle** (10 pasos animados):
1. Ana marca al voicebot (PSTN/SIP/Teams).
2. Agente IA la identifica (voz + nº + voiceprint contra enrollment).
3. Agente **firma JWT assertion** con su `client_secret`: `sub=ana`, `acr=phone-voice`, `voiceprint_score=0.94`, `caller_phone=...`.
4. IdP valida firma del agente + estado de Ana.
5. **Push al móvil** de Ana: "¿Autorizas al agente a leer tu calendario?".
6. **FaceID/huella + tap Approve** en el móvil.
7. Móvil responde challenge firmado al IdP.
8. IdP emite `access_token` con `sub=ana` + `act=agente-ia`.
9. Agente llama a la API con Bearer token.
10. API responde con los datos. Log AUDIT: `voice-verified + push-approved`.

No es un fichero de texto ni una imagen estática: la **definición del flujo vive en JavaScript** y se anima paso a paso en SVG.

---

## 🚀 Cómo se ve

Cada flujo es un *sequence diagram* animado con:

- **6 actores** por flujo (Humano, Cliente, Agente IA, client-mock, Keycloak/B2C, Spring Boot API), coloreados y con lifelines verticales discontinuas.
- **11 mensajes por flujo** (peticiones y respuestas) que aparecen secuencialmente.
- **Panel lateral** con la descripción detallada del paso activo (qué hace cada actor, por qué, qué tokens se firman).
- **Pestaña de código** por paso con `curl`, `HTTP`, `JSON`, `python` y `HTML`.
- **JWT Claims** en formato JSON para los pasos donde se emite un token (visibles en los pasos 7-A, 6-B y 4-C).
- **Controles**: Play/Pause, Step (paso a paso), Reset, y slider de velocidad ×0.25 – ×3.
- **Progress bar** sincronizada con el paso actual.

## ▶️ Cómo se usa

Hay 3 opciones (en orden de preferencia):

### 1) **Doble clic en `flowstudio.html`** (lo más fácil)

Un único fichero autocontenido con CSS + JS inline. **Abre directamente en el navegador sin servidor**. Ideal para compartir, abrir desde Explorador de Windows, etc.

```bash
# Solo doble clic sobre:
agent-oauth-poc/docs/html/flowstudio.html
```

> Si modificas los `.js`/`.css` en `static/`, regenera con `python3 build_standalone.py`.

### 2) Servidor local (versión modular)

La versión canónica: ES modules separados en `static/`. Útil durante desarrollo porque puedes editar `flows.js` y recargar.

```bash
cd agent-oauth-poc/docs/html
python3 -m http.server 8765
# Abre http://localhost:8765
```

### 3) VS Code "Live Server" o GitHub Pages

Abrir `index.html` con un servidor estático cualquiera. Es 100% client-side.

---

## ⚠️ Sobre el error CORS de `file://`

Los navegadores modernos **bloquean módulos ES6 desde `file://`** (el origen es `null` y CORS lo rechaza), por eso la opción 1 (versión modular) requiere servidor. Para evitarlo:

- **`flowstudio.html`** está construido con CSS + JS inline → **funciona desde `file://`** sin servidor.
- Generado por `build_standalone.py` desde las mismas fuentes.

## 🕹️ Controles

| Botón | Acción |
|---|---|
| ▶ Play / ⏸ Pause | Arranca / pausa la animación. Speed ×1 por defecto ≈ 1.7s por paso. |
| ⏭ Step | Avanza 1 paso. Útil para leer con calma. |
| ↻ Reset | Vuelve al estado inicial (ningún paso activo). |
| 🎚 Velocidad | 0.25× → 3×. Por defecto 1×. Afecta solo a la próxima animación. |
| Tabs A/B/C | Cambia de flujo. El progreso se reinicia al cambiar. |

## 🧠 Arquitectura

```
docs/html/
├── index.html                       # estructura + tabs + cards de panel lateral
└── static/
    ├── styles.css                   # dark theme Linear-style
    ├── flows.js                     # spec declarativo de los 3 flujos (data)
    ├── render.js                    # SVG renderer (sequence diagram dinámico)
    └── app.js                       # orquestador: estado, controles, tabs
```

### `flows.js` — datos

Exporta `flowA`, `flowB`, `flowC` y un objeto `FLOWS`. Cada flujo tiene:

- `actors[]`: `{id, name, role, color}` para dibujar cabeceras y lifelines.
- `steps[]`: array ordenado de `{from, to, kind, label, desc, code, claims?, actor?}`.

Modificar `flows.js` cambia la animación sin tocar el renderer.

### `render.js` — SVG

- Layout adaptativo: si el contenedor es estrecho y hay muchos actores (>4), reduce el ancho por actor para evitar scroll horizontal.
- `viewBox` y `preserveAspectRatio` automáticos.
- Mensajes con marcadores SVG (`marker-end`), distinguir petición (`#c9c9d2`) y respuesta (`#6ee7b7`).
- `data-actor` y `data-step` en cada nodo permiten `applyState()` para resaltado dinámico sin re-render.

### `app.js` — estado y controles

- Estado: `flowId`, `step`, `playing`, `timer`, `speed`.
- Sin dependencias externas, ES modules.
- `ResizeObserver` para adaptar el SVG al cambio de tamaño del navegador.

## 🎨 Sistema de colores por flujo

| Flujo | Color | Significado |
|---|---|---|
| A | `#7e83ff` violeta | Login interactivo con navegador + MFA |
| B | `#5eead4` teal | Headless: el humano hace approve en otro dispositivo |
| C | `#f472b6` rosa | Refinamiento de tokens, sin UX humana |

Cada color se aplica a la pestaña activa, a la barra de progreso y al badge del flujo.

## 📋 Cobertura del código por paso

Cada paso define `code: {bash?, python?, http?, json?, html?, note?}`. Si están varios lenguajes, se renderizan como tabs en el panel lateral; si solo hay uno, se muestra directamente.

## ⚠️ Limitaciones conocidas

- **No hay captura final / export a PNG**. La spec no lo pidió.
- **No hay diff side-by-side** entre KC y B2C. Si más adelante se quiere añadir, es trivial — los specs están en `flows.js`.
- **Mensajes demasiado largos**: si un paso tiene label > 70 chars, se renderiza con tamaño 10.5px para caber. El texto sigue legible pero el step es denso.

## 🧪 Tests manuales a hacer

1. Abrir flujo A → Play → ¿avanzan 11 pasos y termina? ¿el botón vuelve a "Play"?
2. Cambiar velocidad a 0.25× durante reproducción → ¿el próximo paso debe ser lento?
3. Click en `bash` / `python` / `json` tabs → ¿cambia el código?
4. Cambiar a flujo B → ¿se re-dibuja con 5 actores (sin client-mock/webapp)?
5. Cambiar a flujo C → ¿aparece `JWT Claims` en el paso donde se emiten tokens?
6. Cambiar tamaño de ventana → ¿se re-renderiza sin scroll horizontal? (con 1280×800 entra todo; en <1000px aparece scroll).
