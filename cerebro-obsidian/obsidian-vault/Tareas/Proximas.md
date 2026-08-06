---
tipo: indice
tags: [meta/indice]
---

# Tareas Próximas

## Esta semana

```dataview
TABLE
  file.link as "Tarea",
  prioridad as "Prioridad",
  proyecto as "Proyecto"
FROM "Tareas"
WHERE contains(tags, "#tarea/pendiente")
SORT fecha_limite ASC
LIMIT 10
```

## Próxima semana

(En desarrollo — pendiente definir ventana de tiempo)

## Sin fecha asignada

```dataview
LIST
FROM "Tareas"
WHERE contains(tags, "#tarea/pendiente") AND (fecha_limite = null OR fecha_limite = "")
SORT fecha_creada DESC
```
