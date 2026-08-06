---
estado: {{estado}}
fecha_inicio: {{fecha_inicio}}
personas: {{personas}}
tags: {{tags}}
---

# {{nombre}}

**Estado:** {{estado}}
**Inicio:** {{fecha_inicio}}
**Personas:** {{personas}}

## Objetivo

## Alcance

## Estado actual

## Próximos pasos

- [ ] {{paso 1}}
- [ ] {{paso 2}}

## Tareas asociadas

```dataview
TABLE
  prioridad as "Prioridad",
  date(fecha_creada) as "Creada"
FROM "Tareas"
WHERE contains(proyecto, this.file.name)
```
