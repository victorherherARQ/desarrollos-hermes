---
tipo: indice
tags: [meta/indice, tarea/hecha]
---

# Tareas Completadas

## Histórico

```dataview
TABLE
  file.link as "Tarea",
  proyecto as "Proyecto",
  date(fecha_creada) as "Creada"
FROM "Tareas"
WHERE contains(tags, "#tarea/hecha")
SORT fecha_creada DESC
```

## Archivo

Las tareas completadas se mueven automáticamente a esta vista cuando cambias su tag de `#tarea/pendiente` a `#tarea/hecha`.
