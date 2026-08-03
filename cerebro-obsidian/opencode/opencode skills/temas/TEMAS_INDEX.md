# openCode — Temas Skills

Colección de prompts y flujos para investigación y organización de temas con opencode CLI.

## Estructura

```
opencode skills/temas/
├── TEMAS_INDEX.md       ← Este archivo
├── investigar.md        # Investigar un tema nuevo
├── resumir.md           # Resumir notas de un tema
├── relacionar.md        # Encontrar conexiones entre temas
└── buscar.md            # Buscar por tema
```

## Tags de tema

| Tag | Significado |
|-----|-------------|
| `#tema` | Tema principal |
| `#nota` | Nota informativa |
| `#referencia` | Información de referencia |
| `#idea` | Idea o pensamiento |
| `#pregunta` | Pregunta abierta |

## Comandos útiles

```bash
# Investigar tema
opencode "Investiga sobre Kubernetes k3s y dame un resumen"

# Buscar notas de un tema
opencode search "#tema kubernetes"

# Encontrar conexiones
opencode "Qué temas están relacionados con OAuth2?"
```
