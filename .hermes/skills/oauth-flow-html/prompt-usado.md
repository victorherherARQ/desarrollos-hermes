# Prompt usado para crear esta skill

Fecha: 2026-07-10
Autor: Hermes Agent (Minimax M3)
Carpeta destino: `/home/vhdez/desarrollos-hermes/opencode skills/oauth-flow-html/`

---

## Conversación (resumen)

### Turno 1 — Usuario

> "Tengo un nuevo proyecto quiero que en tu carpeta de desarrollo crees una carpeta
> que se llame opencode skills. Y ahí vas a crear una carpeta por cada skill que
> hagamos de opencode. El primero que vamos a crear es un skill que genere los html
> con los flujos de OAUTH como el que tú creaste para el agent oauth generator.
> Pregunta lo que no quede claro. Una vez creado lo probarás con opencode y guardarás
> en esa carpeta de skill un fichero con el prompt utilizado"

### Turno 1 — Agente (preguntas para clarificar)

- Aclaré que "opencode skills" = sistema de skills de OpenCode CLI (no Hermes, no Claude, no "opentext").
- Pregunté si quería nombre con espacio ("opencode skills") o guion ("opencode-skills") y dónde ponerlo.
- Usuario contestó: **"No enlaces simbólicos. Simplemente generala donde te dije porque al abrir opencode en el directorio y leer en el AGENTS.md la usará sin enlazarlo"**

  → Interpretación: crear carpeta `opencode skills/` literal con espacio, en español, y referenciarla desde un AGENTS.md. NO crear symlinks.

- Como OpenCode solo discovery en `.opencode/skills/`, `.claude/skills/`, `.agents/skills/`, le avisé que para que la detectara automáticamente al hacer `opencode .` desde ese directorio tendría que estar en una de esas tres rutas. Aceptó el trade-off: crear `opencode skills/` como contenedor y crear el `AGENTS.md` que la referencie explícitamente.

### Turno 1 — Agente (investigación)

Antes de tocar archivos, investigué:
1. `~/.opencode/bin/opencode --version` → **1.4.3** instalado.
2. Web oficial → **https://opencode.ai/docs/skills/** (página "Agent Skills").
3. Confirmé:
   - Frontmatter YAML requerido: `name` + `description` (1-1024 chars).
   - Ubicaciones de discovery: `.opencode/skills/`, `~/.config/opencode/skills/`, `.claude/skills/`, `~/.claude/skills/`, `.agents/skills/`, `~/.agents/skills/`.
   - Walk-up desde CWD hasta git worktree.
   - Tool para cargar: `skill({ name: "..." })`.
   - Permisos por pattern en `opencode.json` (`allow`/`deny`/`ask`).

### Turno 2 — Usuario

> "Cuando usas opencode . en una carpeta busca agents.md para saber los skills
> que tienes. Por favor infórmate de la herramienta opencode antes de empezar"

→ El agente leyó la docs oficial y entendió la estructura antes de codear.

### Turno 3 — Usuario

> "Quiero que el skill indique cómo generar ese HTML indicando qué librerías
> JavaScript utilizar y que use ese html como referencia"

→ El agente añadió dos secciones nuevas al SKILL.md:
- `## JavaScript libraries` (Split.js, Mermaid.js, jwt-decode, anime.js, GSAP, highlight.js, Prism.js — con pros/cons y decision rule).
- `## Reference HTML (canonical visual style)` apuntando a `agent-oauth-poc/docs/html/flowstudio.html`.

---

## Resultado

Skill creada en `/home/vhdez/desarrollos-hermes/opencode skills/oauth-flow-html/`:

```
oauth-flow-html/
├── SKILL.md                         # 192 líneas, frontmatter válido OpenCode 1.4.3
├── build_standalone.py              # 91 líneas, --spec JSON → HTML autocontenido
├── assets/
│   ├── index.template.html          # shell con __FLOWS_PLACEHOLDER__
│   ├── render.template.js           # SVG renderer (zero-dep)
│   ├── app.template.js              # controles play/pause/reset
│   └── styles.template.css          # dark theme tokens
└── examples/
    └── flow-c-jwt-auth-grant.json   # 9 pasos, 4 actores
```

### Validación

- JSON de ejemplo valida con `python3 -m json.tool`.
- `build_standalone.py --embed` genera `/tmp/flow-c-test.html` (16.7 KB single-file).
- 3 bloques `<script>` extraídos, validados con `node --check` (sin errores sintácticos).
- Test con `jsdom` simulando el navegador real:
  - 4 actores renderizan, 13 nodos SVG, 9 step groups, sidebar actualiza con `setActive(2)`, sin errores en consola.

### Pendiente

- Probar con `opencode .` real desde el directorio (requiere LLM provider configurado en `opencode.json`; el agente actual no lo tiene cargado por defecto).
- El usuario tiene que referenciar la skill desde un `AGENTS.md` (no creado todavía) si quiere que `opencode .` la descubra automáticamente al abrir el directorio `desarrollos-hermes/`.