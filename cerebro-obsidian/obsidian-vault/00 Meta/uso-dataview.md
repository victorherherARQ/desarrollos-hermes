# Uso de Dataview

Dataview es **nativo en Obsidian** (no requiere plugins extra).

## Activar

1. Abrir una nota con frontmatter YAML
2. Insertar bloque ` ```dataview ... ``` `
3. Ver resultado en la nota

## Ejemplos

### Listar todos los proyectos activos

```dataview
LIST
FROM "Proyectos"
WHERE contains(tags, "#proyecto/activo")
```

### Tareas pendientes con prioridad

```dataview
TABLE
  prioridad as "Prioridad",
  date(fecha_creada) as "Creada"
FROM "Tareas"
WHERE contains(tags, "#tarea/pendiente")
SORT prioridad ASC
```

### Personas

```dataview
TABLE
  rol as "Rol",
  email as "Email"
FROM "Personas"
SORT file.name ASC
```

## Frontmatter YAML

Las notas deben tener frontmatter YAML para que Dataview las indexe:

```yaml
---
prioridad: alta
fecha_creada: 2026-08-05
tags: [tarea/pendiente]
persona: juan-perez
proyecto: proyecto-x
---
```

## Más info

https://blacksmithgu.github.io/obsidian-dataview/
