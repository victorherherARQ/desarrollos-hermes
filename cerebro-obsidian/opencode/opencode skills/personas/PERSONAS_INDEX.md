# openCode — Personas Skills

Colección de prompts y flujos para gestión de personas con opencode CLI.

## Estructura

```
opencode skills/personas/
├── PERSONAS_INDEX.md       ← Este archivo
├── buscar.md              # Buscar persona por nombre/tag
├── crear.md               # Crear ficha de persona
├── actualizar.md          # Actualizar datos de persona
└── contacto.md            # Generar ficha de contacto
```

## Tags de persona

| Tag | Significado |
|-----|-------------|
| `#persona` | Ficha de persona |
| `#contacto` | Contacto profesional |
| `#equipo` | Miembro del equipo |
| `#cliente` | Cliente |

## Comandos útiles

```bash
# Buscar persona
opencode search "#persona nombre"

# Ver equipo
opencode search "#persona #equipo"
```
