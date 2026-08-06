---
tipo: indice
tags: [meta/indice, tarea/pendiente]
---

# Tareas Pendientes

## Alta prioridad

```dataview
TABLE
  file.link as "Tarea",
  proyecto as "Proyecto",
  date(fecha_creada) as "Creada"
FROM "Tareas"
WHERE contains(tags, "#tarea/pendiente") AND contains(tags, "#prioridad/alta")
SORT fecha_creada DESC
```

## Media prioridad

```dataview
TABLE
  file.link as "Tarea",
  proyecto as "Proyecto",
  date(fecha_creada) as "Creada"
FROM "Tareas"
WHERE contains(tags, "#tarea/pendiente") AND contains(tags, "#prioridad/media")
SORT fecha_creada DESC
```

## Baja prioridad

```dataview
TABLE
  file.link as "Tarea",
  proyecto as "Proyecto",
  date(fecha_creada) as "Creada"
FROM "Tareas"
WHERE contains(tags, "#tarea/pendiente") AND contains(tags, "#prioridad/baja")
SORT fecha_creada DESC
```

## Tareas por proyecto

```dataview
TABLE
  length(rows) as "Total"
FROM "Tareas"
WHERE contains(tags, "#tarea/pendiente")
GROUP BY proyecto
```
