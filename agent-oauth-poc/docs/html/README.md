# A+B+C Flow Studio

Diagrama de actores **dinámico e interactivo** (JavaScript puro, sin frameworks) de los 3 flujos OAuth/OIDC que implementa la PoC `agent-oauth-poc` en su versión v2:

- **A** — Authorization Code + PKCE (RFC 6749 §4.1 + RFC 7636)
- **B** — Device Code (RFC 8628)
- **C** — On-Behalf-Of (RFC 7523)

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

Hay 3 opciones:

### 1) Servidor local (recomendado)

```bash
cd agent-oauth-poc/docs/html
python3 -m http.server 8765
# Abre http://localhost:8765
```

Módulo ES6 necesita un servidor (no funciona con `file://`).

### 2) VS Code "Live Server" o similar

Abrir `index.html` directamente con un servidor estático.

### 3) GitHub Pages o similar

Montar `docs/html/` como sitio estático. Es 100% client-side, sin build.

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
