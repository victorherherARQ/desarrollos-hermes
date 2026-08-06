---
rol: {{rol}}
empresa: {{empresa}}
email: {{email}}
telefono: {{telefono}}
fecha_alta: {{fecha_alta}}
tags: {{tags}}
---

# {{nombre}}

**Rol:** {{rol}}
**Empresa:** {{empresa}}
**Email:** {{email}}
**Última interacción:** {{fecha}}

## Contexto

## Notas

## Tareas abiertas

```dataview
TABLE
  prioridad as "Prioridad",
  date(fecha_creada) as "Creada"
FROM "Tareas"
WHERE contains(tags, "#tarea/pendiente")
  AND contains(persona, this.file.name)
SORT prioridad ASC
```

## Proyectos compartidos

```dataview
LIST
FROM "Proyectos"
WHERE contains(personas, this.file.name)
```
