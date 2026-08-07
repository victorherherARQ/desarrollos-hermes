---
name: oauth-flow-html
description: Generate a single-file interactive HTML with an animated sequence diagram of OAuth/OIDC flows from a JSON spec. Use when the user asks to visualize, document, or explain an OAuth/OIDC flow (Authorization Code, Client Credentials, JWT Authorization Grant, Token Exchange, CIBA, SAML, OIDC, etc.). Outputs a self-contained .html with dark theme, timeline animation, payload inspector, and clickable steps. Triggered by requests like "make an OAuth flow diagram", "visualiza el flujo", "genera el HTML del flujo", "diagram the JWT bearer grant", "CIBA flow diagram".
license: MIT
compatibility: opencode, hermes
metadata:
  category: documentation
  language: en
  project: agent-oauth-poc
  generalized: 2026-08-07
  original: "cerebro-obsidian/opencode/opencode skills/oauth-flow-html/"
  locations:
    - "~/.hermes/skills/oauth-flow-html/"
    - "/home/vhdez/desarrollos-hermes/.hermes/skills/oauth-flow-html/"
---

# oauth-flow-html

Generate a single-file interactive HTML page that visualizes an OAuth 2.0 / OIDC flow as an animated sequence diagram.

## When to use

The user wants to:
- Visualize an OAuth/OIDC flow (Authorization Code, Client Credentials, JWT Authorization Grant, Token Exchange, SAML, OIDC, etc.)
- Document a protocol step by step with payload inspection
- Share a flow diagram that runs in any browser without a server

Do NOT use this skill for:
- Generic UML diagrams (use a different tool)
- Non-OAuth protocol flows (gRPC, AMQP, etc.) unless the user explicitly asks for OAuth framing

## Inputs

The user typically provides one of:
1. A JSON file with the flow spec (see schema below) — easiest path
2. A free-form description of the flow in natural language — generate the JSON first, then render
3. A reference to an existing flow (e.g., "the Authorization Code flow from RFC 6749")

## Flow spec schema

```json
{
  "title": "Flow name (shown in header)",
  "actors": [
    { "id": "user",        "label": "User/Resource Owner", "type": "external" },
    { "id": "client",      "label": "Client App",          "type": "external" },
    { "id": "agent",       "label": "AI Agent",            "type": "internal" },
    { "id": "idp",         "label": "Keycloak (IdP)",      "type": "internal" },
    { "id": "api",         "label": "Resource API",        "type": "internal" }
  ],
  "steps": [
    {
      "n": 1,
      "from": "client",
      "to": "idp",
      "label": "Authorization request",
      "detail": "GET /authorize?response_type=code&client_id=...&redirect_uri=...&scope=...",
      "payload": { "method": "GET", "url": "/authorize", "params": { "response_type": "code", "client_id": "agente-ia" } },
      "duration_ms": 1200
    }
  ]
}
```

- `actors`: 2-6 actors. Order = left-to-right layout. `type` only changes the icon, not behavior.
- `steps`: ordered list. `from` and `to` must match an `actor.id`. `payload` is optional (shown in inspector panel).
- `duration_ms`: how long the animation of this step takes (default 1200).

## Output

A single HTML file (~80-150 KB) with:
- **Self-contained**: all CSS/JS inlined, no external CDN, no build step
- **Dark theme** matching the agent-oauth-poc visual style
- **Animated sequence diagram**: arrows travel from `from` to `to`, top-to-bottom timeline
- **Payload inspector**: click any step to see headers, body, JWT claims (decoded if recognizable)
- **Controls**: play/pause, step-by-step, reset, speed slider
- **Responsive**: works on mobile (stacked actors) and desktop (side-by-side)

## JavaScript libraries

This skill ships a **zero-dependency** template: vanilla JS + browser-native SVG, no npm, no CDN, no bundler. That choice is deliberate — flow diagrams are small enough that any library is overkill.

If you need to extend it and want to add libraries, here is the recommended split by layer (pick what you actually need, never all of them):

### Layout / UI shell
- **None needed.** The template uses native CSS Grid + Flexbox. For more advanced layouts (resizable panes, dock views) consider [Split.js](https://split.js.org/) (~2 KB, zero-dep) or [Golden Layout](https://golden-layout.github.io/golden-layout/) (heavier, full IDE-like).

### Sequence diagram rendering (SVG layer)
- **None needed.** The template draws lifelines, arrows, and labels directly with `<svg>` primitives (~150 LOC). Easy to debug, easy to tweak.
- Alternative if you want a battle-tested lib: **[Mermaid.js](https://mermaid.js.org/) sequenceDiagram** (~600 KB). Pros: declarative syntax, exports SVG. Cons: heavy, harder to animate step-by-step, theming is awkward.
- Heavier option: **[JointJS](https://www.jointjs.com/)** or **[GoJS](https://gojs.net/)** for full interactive graph editors. **Avoid for OAuth flows** — overkill and they pull jQuery / TypeScript runtime.

### JWT decoding (in the payload inspector)
- **None needed.** The template's inspector shows raw text. To auto-decode JWT segments into header/payload, use:
  - **[jwt-decode](https://github.com/auth0/jwt-decode)** (1 KB, zero-dep, MIT) — does NOT verify signatures, only decodes. Ideal for inspectors.
  - Avoid `jsonwebtoken` and `jose` on the client side — they imply signature verification and bring crypto APIs that bloat the bundle.

### Animation
- **None needed.** The template uses CSS transitions (`transition: opacity .3s`) and a single CSS `@keyframes` pulse. No animation library required.
- If you need sequenced multi-step choreography: **[anime.js](https://animejs.com/)** (~17 KB) or **[GSAP](https://gsap.com/)** (~70 KB free tier). Skip unless the user explicitly asks for cinematic motion.

### Syntax highlighting in the inspector (optional)
- **[highlight.js](https://highlightjs.org/)** (~50 KB core, lazy-load languages) — auto-detects JSON / HTTP / JWT.
- **[Prism.js](https://prismjs.com/)** (~2 KB core) — lighter, manual language declaration.

### Decision rule

> **If the user does not ask for a library, do not add one.** The default template is ~14 KB total and works offline. Mention the library options above only when the user says "I want a more polished look", "add JWT decoding", or "use Mermaid syntax".

### Adding a library to the template

If a library is genuinely needed:
1. Download the minified bundle (`.min.js`) once.
2. Save it under `assets/vendor/<lib>.min.js`.
3. Add `<script src="./vendor/<lib>.min.js"></script>` to `assets/index.template.html`.
4. The `build_standalone.py --embed` flag will inline it into the final `.html`.
5. Update the SPEC.md `## JavaScript libraries` section with what you added and why.

## Reference HTML (canonical visual style)

The canonical reference for **visual style, dark theme palette, and UX** is the hand-built HTML at:

```
agent-oauth-poc/docs/html/flowstudio.html  (1728 LOC total: index.html + 4 static files)
```

This is the **only** pre-existing flow diagram in the workspace and was built manually in early July 2026 to document the A/B/C flows of the agent-oauth-poc project. It uses:

- Pure SVG for the sequence canvas (no library)
- Linear-inspired dark palette: `--bg: #0a0a0b`, `--fg: #e6edf3`, `--accent: #58a6ff`, `--line: #30363d`
- Tabs to switch between the 3 flows (A=Auth Code+PKCE, B=Device Code, C=JWT Authorization Grant)
- Per-step payload inspector that decodes JWTs

**When generating a new flow with this skill:**
- Reuse the color tokens from `styles.template.css` (already aligned with the reference).
- If the user says "make it look like the Flow Studio one", copy the `--bg`/`--fg`/`--accent` variables and the topbar layout from `agent-oauth-poc/docs/html/static/styles.css`.
- **Do not** try to parse or extend `flowstudio.html` programmatically — it is static. Use it as a **visual reference only**.

## How to use this skill

### Step 1 — Locate assets

The skill ships with these templates in `assets/`:
- `index.template.html` — page shell with `__FLOWS_PLACEHOLDER__` and `__TITLE__` markers
- `render.template.js` — SVG sequence-diagram renderer. Reads `window.__FLOWS__` and exposes `window.__flowRender`.
- `app.template.js` — controls (play/pause/reset, speed, prev/next, click-to-jump)
- `styles.template.css` — dark theme tokens
- `build_standalone.py` — Python script: injects a JSON spec into the templates and emits a single (or multi-file) .html

### Step 2 — Generate or receive the spec

If the user gives free-form text, draft the JSON spec first. If they give a JSON file path, read it directly.

### Step 3 — Run the build script

```bash
python3 "<skill-dir>/build_standalone.py" \
  --spec /path/to/flow.json \
  --output /path/to/flow.html
```

The script replaces the `__FLOWS_PLACEHOLDER__` in `flows.template.js` with the user's spec (JSON-encoded) and concatenates everything into a single .html.

### Step 4 — Verify

- Open the resulting .html in a browser (or use `xdg-open`, `open`, or send as a Telegram attachment).
- Confirm: title renders, all actors appear, all steps animate, payload inspector opens on click.

### Step 5 — Report

Tell the user the output path and offer to:
- Adjust colors, timing, or layout
- Add/remove actors or steps
- Generate a different flow using the same template
- Save the spec to `examples/<name>.json` for future reuse

## Example

```bash
# User asks: "make an HTML diagram of the Authorization Code flow with PKCE"
# 1. Draft spec -> examples/auth-code-pkce.json
# 2. Render -> ./auth-code-pkce.html
python3 "opencode skills/oauth-flow-html/build_standalone.py" \
  --spec "opencode skills/oauth-flow-html/examples/auth-code-pkce.json" \
  --output ./auth-code-pkce.html
```

## Pitfalls

- **JSON validity**: spec must be valid JSON. Use `python3 -m json.tool < spec.json` to validate before rendering.
- **Actor references**: every `from`/`to` in `steps` must match an `actor.id` exactly. Typos produce silent missing arrows.
- **Large flows**: >12 steps becomes hard to read. Suggest splitting into multiple HTMLs or adding sub-phases.
- **JWT decoding**: the inspector recognizes `eyJ...` JWTs and decodes header/payload if the segments are base64url-valid. It does NOT verify signatures.
- **Encoding**: keep all source files UTF-8. The build script embeds the spec as a JS literal using `json.dumps(ensure_ascii=False)`.

## Provenance

This skill was first created to document the `agent-oauth-poc` flows (A, B, C, D) from the OAuth PoC project. The original hand-coded HTML lives at `agent-oauth-poc/docs/html/flowstudio.html` and is the canonical reference for visual style.