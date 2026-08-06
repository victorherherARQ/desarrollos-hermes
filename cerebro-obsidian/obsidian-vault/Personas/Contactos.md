---
tipo: indice
tags: [persona/contacto, meta/indice]
---

# Personas — Directorio

## Equipo
- [[Victor]]

## Contactos

## Tareas abiertas por persona

```dataview
TABLE
  length(rows) as "Total"
FROM "Tareas"
WHERE contains(tags, "#tarea/pendiente")
GROUP BY persona
```
