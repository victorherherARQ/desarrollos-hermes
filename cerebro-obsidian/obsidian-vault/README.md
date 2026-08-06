---
tags: [meta/indice]
---

# Obsidian Vault — Second Brain de Victor

Vault de Obsidian para gestión de tareas, personas, temas y proyectos. **Gestionado por Hermes directamente.**

## Estructura

```
obsidian-vault/
├── 00 Meta/              # Dashboard, plantillas, INDICE, tags
├── Personas/             # Fichas de personas
├── Proyectos/            # Proyectos activos
├── Tareas/               # Tareas pendientes y completadas
├── Temas/                # Investigación
├── actuaciones/          # Log cronológico (cron 9 AM diario)
└── opencode/             # Skills y configuración opencode
```

## Sistema de tags

19 tags jerárquicos. Ver `00 Meta/tags.md`.

Categorías:
- `#persona/contacto`
- `#proyecto/activo`, `#proyecto/bloqueado`, `#proyecto/cerrado`
- `#tarea/pendiente`, `#tarea/en-progreso`, `#tarea/hecha`
- `#tema/investigacion`
- `#prioridad/alta`, `#prioridad/media`, `#prioridad/baja`
- `#area/trabajo`, `#area/casa`, `#area/personal`

## Gestión

**Casa (este vault)**: gestionado por **Hermes** (yo). Le dices "alta tarea X" y la creo con plantilla + frontmatter YAML.

**Trabajo** (`sistema-trabajo-sync`): vault read-only, gestionado por opencode + Copilot 365.

## Dashboard

Ver `00 Meta/dashboard.md` para vista Dataview de tareas pendientes, proyectos activos, personas.

## Plantillas

6 plantillas con frontmatter YAML en `00 Meta/Plantillas/`:
- persona, proyecto, tarea, tema, reunion, diario

## Proyectos

- [[Proyectos/agentgateway-poc]]
- [[Proyectos/minipc-docs]]
- [[Proyectos/synchealth]]
- [[Proyectos/quiniela-analyzer]] (bloqueado)

## Índice general

- [[00 Meta/INDICE|Índice completo]]
- [[00 Meta/dashboard|Dashboard Dataview]]
- [[00 Meta/tags|Sistema de tags]]
- [[00 Meta/uso-dataview|Uso de Dataview]]
- [[Tareas/Pendientes|Tareas pendientes]]
- [[Personas/Victor|Ficha Victor]]
- [[Temas/Index|Temas]]
