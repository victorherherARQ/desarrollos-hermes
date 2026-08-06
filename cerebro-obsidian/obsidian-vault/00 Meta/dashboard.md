---
tags: [meta/dashboard]
---

# Dashboard

## Tareas pendientes por prioridad

```dataview
TABLE
  file.link as "Tarea",
  prioridad as "Prioridad",
  date(fecha_creada) as "Creada"
FROM "Tareas"
WHERE contains(tags, "#tarea/pendiente")
SORT prioridad ASC, fecha_creada DESC
```

## Tareas en progreso

```dataview
LIST
FROM "Tareas"
WHERE contains(tags, "#tarea/en-progreso")
```

## Tareas por persona

```dataview
TABLE
  length(rows) as "Total"
FROM "Tareas"
WHERE contains(tags, "#tarea/pendiente")
GROUP BY persona
```

## Proyectos activos

```dataview
LIST
FROM "Proyectos"
WHERE contains(tags, "#proyecto/activo")
```

## Personas registradas

```dataview
TABLE
  rol as "Rol",
  empresa as "Empresa",
  email as "Email"
FROM "Personas"
SORT file.name ASC
```

## Temas recientes

```dataview
LIST
FROM "Temas"
WHERE contains(tags, "#tema/investigacion")
SORT file.ctime DESC
LIMIT 10
```

## Últimas actuaciones

```dataview
LIST
FROM "actuaciones"
WHERE contains(tags, "#actuacion/diaria")
SORT fecha DESC
LIMIT 5
```
