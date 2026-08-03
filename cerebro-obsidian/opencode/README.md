# OpenCode Skills

Prompts y flujos para gestión de información con opencode CLI.

## Estructura

```
opencode/
├── tareas/          # Skills para gestión de tareas
├── personas/        # Skills para gestión de personas
└── temas/          # Skills para gestión de temas
```

## Tags que entiende el sistema

### Tareas
| Tag | Significado |
|-----|-------------|
| `#tarea` | Tarea pendiente |
| `#tarea/en-progreso` | En curso |
| `#tarea/completada` | Hecha |
| `#tarea/bloqueada` | Bloqueada |
| `#tarea/urgente` | Prioridad alta |

### Personas
| Tag | Significado |
|-----|-------------|
| `#persona` | Ficha de persona |
| `#contacto` | Contacto profesional |
| `#equipo` | Miembro del equipo |

### Temas
| Tag | Significado |
|-----|-------------|
| `#tema` | Tema principal |
| `#nota` | Nota informativa |
| `#referencia` | Referencia |
| `#idea` | Idea |

## Comandos

```bash
# Buscar tareas pendientes
opencode search "#tarea"

# Buscar tareas de un proyecto
opencode search "#tarea #synchealth"

# Buscar notas de un tema
opencode search "#tema kubernetes"
```
