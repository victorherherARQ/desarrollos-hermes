# openCode — Tareas Skills

Colección de prompts y flujos para gestión de tareas con opencode CLI.

## Estructura

```
opencode skills/tareas/
├── TAREAS_INDEX.md       ← Este archivo
├── buscar.md             # Buscar tareas por estado/proyecto
├── crear.md              # Crear nueva tarea
├── completar.md          # Marcar como completada
├── archivar.md           # Archivar tarea
└── reporte.md            # Generar reporte de tareas
```

## Tags de tarea

| Tag | Significado |
|-----|-------------|
| `#tarea/pendiente` | Tarea por hacer |
| `#tarea/en-progreso` | Tarea en curso |
| `#tarea/completada` | Tarea hecha |
| `#tarea/bloqueada` | Tarea bloqueada por dependencia |
| `#tarea/urgente` | Prioridad alta |

## Comandos útiles

```bash
# Buscar tareas pendientes
opencode search "#tarea/pendiente"

# Ver tareas de un proyecto
opencode search "#tarea #minipc"

# Buscar tareas asignadas a Victor
opencode search "#asignado victor"
```
